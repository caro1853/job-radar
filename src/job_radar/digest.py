"""Ranks analyzed jobs and writes the daily Markdown digest."""

from __future__ import annotations

from collections import Counter
from datetime import date

from job_radar.models import Job, JobAnalysis

HIREABLE = ("latam_ok", "worldwide")


def rank(
    rows: list[tuple[Job, JobAnalysis, str | None]],
    min_score: int = 60,
    include_unclear: bool = True,
) -> list[tuple[Job, JobAnalysis]]:
    """Jobs you can apply to from Colombia, best match first. Skips jobs already tracked."""
    regions = HIREABLE + (("unclear",) if include_unclear else ())
    picked = [
        (job, a)
        for job, a, status in rows
        if status is None and a.hiring_region in regions and a.match_score >= min_score
    ]
    # Confirmed-hireable jobs rank above "unclear" ones with the same score.
    return sorted(picked, key=lambda p: (p[1].match_score, p[1].hiring_region in HIREABLE), reverse=True)


def skill_gaps(ranked: list[tuple[Job, JobAnalysis]], top: int = 10) -> list[tuple[str, int]]:
    """The skills most often missing across the jobs that fit you: your study list."""
    counts = Counter(skill.strip().lower() for _, a in ranked for skill in a.missing_skills)
    return counts.most_common(top)


def _salary(a: JobAnalysis) -> str:
    if a.salary_min_usd_year and a.salary_max_usd_year:
        return f"${a.salary_min_usd_year // 1000}k-{a.salary_max_usd_year // 1000}k"
    if a.salary_min_usd_year or a.salary_max_usd_year:
        return f"${(a.salary_min_usd_year or a.salary_max_usd_year) // 1000}k"
    return "not stated"


REGION_LABEL = {"latam_ok": "LATAM OK", "worldwide": "Worldwide", "unclear": "Check location"}


def render(ranked: list[tuple[Job, JobAnalysis]], today: date | None = None) -> str:
    today = today or date.today()
    lines = [f"# Job Radar: {today.isoformat()}", ""]
    if not ranked:
        lines.append("No new jobs above your score threshold today.")
        return "\n".join(lines) + "\n"

    lines += [
        f"{len(ranked)} new jobs you can apply to from Colombia.",
        "",
        "| Score | Job | Company | Region | Salary | AI role |",
        "|---|---|---|---|---|---|",
    ]
    for job, a in ranked:
        lines.append(
            f"| {a.match_score} | [{job.title}]({job.url}) | {job.company} | "
            f"{REGION_LABEL.get(a.hiring_region, a.hiring_region)} | {_salary(a)} | "
            f"{'yes' if a.is_ai_integration_role else 'no'} |"
        )

    lines += ["", "## Details", ""]
    for job, a in ranked:
        lines += [
            f"### {a.match_score} · {job.title} at {job.company}",
            f"`{job.uid}` · {job.location or 'location not stated'} · {a.seniority} · {a.employment_type}",
            "",
            a.reasoning,
            "",
            f"- **You have:** {', '.join(a.matching_skills) or 'none listed'}",
            f"- **You're missing:** {', '.join(a.missing_skills) or 'nothing'}",
        ]
        if a.region_evidence:
            lines.append(f'- **Location evidence:** "{a.region_evidence}"')
        lines.append("")

    gaps = skill_gaps(ranked)
    if gaps:
        lines += ["## Skills to study next", "", "Missing most often in today's matches:", ""]
        lines += [f"- {skill} ({n} jobs)" for skill, n in gaps]
    return "\n".join(lines) + "\n"
