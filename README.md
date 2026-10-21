# Job Radar

Job Radar finds remote AI Integration jobs that a person living in Colombia can actually get. It scores how well each job fits your CV, lists the skills you are missing, and drafts a tailored CV and cover letter. **You** apply on the company's site. Nothing is submitted automatically.

## How it works

1. **Fetch:** it downloads jobs from the official public APIs of Greenhouse, Lever and Ashby (for the companies in `companies.yaml`) and from Remotive. It doesn't scrape any site, and it doesn't use LinkedIn or Indeed, whose terms forbid bots.
2. **Prefilter:** a free rule drops jobs whose title doesn't match or whose location is on-site.
3. **Analyze:** Claude reads each remaining job and returns structured data: whether someone in LATAM can be hired, seniority, salary in USD, required skills, and a 0-100 match score against your profile.
4. **Digest:** a daily Markdown report ranks the jobs you can apply to and lists the skills missing most often.
5. **Tailor:** for a job you like, Claude drafts CV bullets, a cover letter, and likely interview questions, using only facts from your CV.
6. **Track:** you record each application's status and see your whole pipeline.

## Setup

```bash
uv sync                                   # installs dependencies into .venv
cp profile.example.yaml profile.yaml      # then paste your CV and skills into it
export ANTHROPIC_API_KEY=sk-ant-...       # from console.anthropic.com
```

## Daily use

```bash
uv run job-radar -v run --limit 50       # fetch + analyze up to 50 new jobs + write digests/<today>.md
uv run job-radar tailor ashby:<id>        # draft an application (the id is in the digest)
uv run job-radar status ashby:<id> applied
uv run job-radar pipeline
```

To add a job you found on LinkedIn or anywhere else, paste its description:

```bash
uv run job-radar add --url <job url> --title "AI Engineer" --company "Acme" --location "Remote" < job.txt
```

To run it every morning, add a cron job (Linux/macOS) or a Task Scheduler task (Windows):

```
0 7 * * 1-5  cd /path/to/job-radar && uv run job-radar run --limit 50
```

## Cost

`analyze` uses `claude-opus-5-5` at low effort. The profile and CV are prompt-cached, so each job costs roughly two to three US cents (an estimate, not measured yet). `--limit` caps how many jobs each run analyzes. Set `JOB_RADAR_MODEL` to use a different model.

## Tests

```bash
uv run pytest
```

The source tests use sample responses written to match each API's documentation. The slugs in `companies.yaml` haven't been checked against the live boards yet; `fetch -v` logs any slug that fails.

## Next steps

- More sources: Get on Board, Himalayas, the Hacker News "Who is hiring" thread, and LinkedIn job alert emails.
- PostgreSQL + pgvector, and embedding-based matching.
- A small web UI (FastAPI + Streamlit) on top of the same store.
