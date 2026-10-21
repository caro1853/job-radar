"""Command line entry point: `job-radar <command>`."""

from __future__ import annotations

import argparse
import hashlib
import logging
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx
import yaml

from job_radar import db, digest, llm, prefilter
from job_radar.models import Job, Profile
from job_radar.sources import registry, remotive

log = logging.getLogger("job_radar")
USER_AGENT = "job-radar/0.1 (personal job search tool)"


def load_profile(path: str) -> Profile:
    if not Path(path).exists():
        sys.exit(f"{path} not found. Copy profile.example.yaml to profile.yaml and fill it in.")
    return Profile.model_validate(yaml.safe_load(Path(path).read_text(encoding="utf-8")))


def cmd_fetch(args, store: db.Store, profile: Profile) -> None:
    companies = yaml.safe_load(Path(args.companies).read_text(encoding="utf-8")) or {}
    fetchers = registry()
    jobs: list[Job] = []
    with httpx.Client(timeout=30, headers={"User-Agent": USER_AGENT}, follow_redirects=True) as client:
        for source, fetch in fetchers.items():
            for slug, company in (companies.get(source) or {}).items():
                found = fetch(client, slug, company)
                log.info("%s/%s: %d jobs", source, slug, len(found))
                jobs += found
        for category in (companies.get("remotive") or {}).get("categories", []):
            found = remotive.fetch(client, category)
            log.info("remotive/%s: %d jobs", category, len(found))
            jobs += found

    kept = [j for j in jobs if prefilter.keep(j, profile)]
    new = store.add_jobs(kept)
    print(f"Fetched {len(jobs)} jobs, {len(kept)} passed the title/location filter, {new} are new.")


def cmd_add(args, store: db.Store, profile: Profile) -> None:
    """Adds a job by hand, e.g. one you found on LinkedIn. The description comes from a file or stdin."""
    text = Path(args.file).read_text(encoding="utf-8") if args.file else sys.stdin.read()
    job = Job(
        source="manual",
        external_id=hashlib.sha1(args.url.encode()).hexdigest()[:12],
        company=args.company,
        title=args.title,
        location=args.location,
        url=args.url,
        description=text.strip(),
    )
    store.add_jobs([job])
    print(f"Added {job.uid}. Run `job-radar analyze` to score it.")


def cmd_analyze(args, store: db.Store, profile: Profile) -> None:
    import anthropic

    client = anthropic.Anthropic()
    pending = store.unanalyzed(limit=args.limit)
    print(f"Analyzing {len(pending)} jobs with {llm.MODEL}...")
    done = 0
    for job in pending:
        try:
            analysis = llm.analyze(client, job, profile)
        except llm.Refused as exc:
            log.warning("Refused %s: %s", job.uid, exc)
            continue
        except anthropic.RateLimitError:
            log.warning("Rate limited; stopping here. Run analyze again later to continue.")
            break
        except (anthropic.APIStatusError, anthropic.APIConnectionError, ValueError) as exc:
            log.warning("Failed %s: %s", job.uid, exc)
            continue
        store.save_analysis(job.uid, analysis, llm.MODEL)
        done += 1
        log.info("%3d  %-12s %s at %s", analysis.match_score, analysis.hiring_region, job.title, job.company)
    print(f"Analyzed {done} of {len(pending)} jobs.")


def cmd_digest(args, store: db.Store, profile: Profile) -> None:
    since = None
    if args.days:
        since = (datetime.now(timezone.utc) - timedelta(days=args.days)).isoformat(timespec="seconds")
    ranked = digest.rank(store.analyzed(since=since), min_score=args.min_score, include_unclear=not args.strict)
    out = Path(args.out_dir) / f"{date.today().isoformat()}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(digest.render(ranked), encoding="utf-8")
    print(f"{len(ranked)} jobs in the digest: {out}")


def cmd_run(args, store: db.Store, profile: Profile) -> None:
    cmd_fetch(args, store, profile)
    cmd_analyze(args, store, profile)
    cmd_digest(args, store, profile)


def cmd_tailor(args, store: db.Store, profile: Profile) -> None:
    import anthropic

    job = store.get_job(args.uid)
    if not job:
        sys.exit(f"Unknown job {args.uid}. Copy the id from the digest.")
    t = llm.tailor(anthropic.Anthropic(), job, profile)
    out = Path(args.out_dir) / f"{args.uid.replace(':', '_')}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        f"# {job.title} at {job.company}\n\n{job.url}\n\n## CV summary\n\n{t.cv_summary}\n\n"
        "## CV bullets\n\n" + "\n".join(f"- {b}" for b in t.cv_bullets) + "\n\n"
        f"## Cover letter\n\n{t.cover_letter}\n\n## Prepare for these questions\n\n"
        + "\n".join(f"- {q}" for q in t.questions_to_prepare) + "\n",
        encoding="utf-8",
    )
    store.set_status(args.uid, "interested")
    print(f"Draft written to {out}. Review it, apply on the company site, then run:\n"
          f"  job-radar status {args.uid} applied")


def cmd_status(args, store: db.Store, profile: Profile) -> None:
    store.set_status(args.uid, args.status, args.notes)
    print(f"{args.uid} is now '{args.status}'.")


def cmd_pipeline(args, store: db.Store, profile: Profile) -> None:
    rows = store.pipeline()
    if not rows:
        print("No tracked applications yet.")
    for uid, company, title, status, updated in rows:
        print(f"{status:<13} {updated[:10]}  {company}: {title}  ({uid})")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="job-radar", description=__doc__)
    p.add_argument("--db", default="job_radar.db")
    p.add_argument("--profile", default="profile.yaml")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)

    def with_fetch(sp):
        sp.add_argument("--companies", default="companies.yaml")

    def with_analyze(sp):
        sp.add_argument("--limit", type=int, default=None, help="analyze at most N jobs (controls cost)")

    def with_digest(sp):
        sp.add_argument("--min-score", type=int, default=60)
        sp.add_argument("--strict", action="store_true", help="leave out jobs whose location is unclear")
        sp.add_argument("--days", type=float, default=None, help="only jobs analyzed in the last N days")
        sp.add_argument("--out-dir", default="digests")

    sp = sub.add_parser("fetch", help="download new jobs from all sources")
    with_fetch(sp)
    sp.set_defaults(func=cmd_fetch)

    sp = sub.add_parser("add", help="add a job by hand (e.g. from LinkedIn); description from --file or stdin")
    sp.add_argument("--url", required=True)
    sp.add_argument("--title", required=True)
    sp.add_argument("--company", required=True)
    sp.add_argument("--location", default="")
    sp.add_argument("--file")
    sp.set_defaults(func=cmd_add)

    sp = sub.add_parser("analyze", help="score new jobs with Claude")
    with_analyze(sp)
    sp.set_defaults(func=cmd_analyze)

    sp = sub.add_parser("digest", help="write today's ranked digest")
    with_digest(sp)
    sp.set_defaults(func=cmd_digest)

    sp = sub.add_parser("run", help="fetch + analyze + digest (the daily job)")
    with_fetch(sp)
    with_analyze(sp)
    with_digest(sp)
    sp.set_defaults(func=cmd_run)

    sp = sub.add_parser("tailor", help="draft CV bullets and a cover letter for one job")
    sp.add_argument("uid")
    sp.add_argument("--out-dir", default="applications")
    sp.set_defaults(func=cmd_tailor)

    sp = sub.add_parser("status", help="update a job in your pipeline")
    sp.add_argument("uid")
    sp.add_argument("status", choices=db.STATUSES)
    sp.add_argument("--notes", default="")
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("pipeline", help="list your tracked applications")
    sp.set_defaults(func=cmd_pipeline)
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(message)s")
    needs_profile = args.command in ("fetch", "analyze", "run", "tailor")
    profile = load_profile(args.profile) if needs_profile else None
    args.func(args, db.Store(args.db), profile)


if __name__ == "__main__":
    main()
