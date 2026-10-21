"""Ashby Job Postings API: https://developers.ashbyhq.com/docs/public-job-posting-api"""

from __future__ import annotations

import httpx

from job_radar.models import Job
from job_radar.sources import get_json, html_to_text

URL = "https://api.ashbyhq.com/posting-api/job-board/{slug}"


def parse(data: dict, company: str) -> list[Job]:
    jobs = []
    for item in data.get("jobs", []):
        if item.get("isListed") is False:
            continue
        location = item.get("location", "")
        if item.get("isRemote") and "remote" not in location.lower():
            location = f"Remote ({location})" if location else "Remote"
        compensation = item.get("compensation") or {}
        jobs.append(
            Job(
                source="ashby",
                external_id=item.get("id") or item.get("jobUrl", ""),
                company=company,
                title=item.get("title", ""),
                location=location,
                url=item.get("jobUrl") or item.get("applyUrl", ""),
                description=item.get("descriptionPlain") or html_to_text(item.get("descriptionHtml")),
                posted_at=item.get("publishedAt"),
                salary_hint=compensation.get("compensationTierSummary"),
            )
        )
    return jobs


def fetch(client: httpx.Client, slug: str, company: str) -> list[Job]:
    data = get_json(client, URL.format(slug=slug), includeCompensation="true")
    return parse(data, company) if isinstance(data, dict) else []
