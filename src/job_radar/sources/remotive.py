"""Remotive public API: https://github.com/remotive-com/remote-jobs-api

Remotive asks clients to call it at most a few times a day and to link back to
the posting, which the digest does.
"""

from __future__ import annotations

import httpx

from job_radar.models import Job
from job_radar.sources import get_json, html_to_text

URL = "https://remotive.com/api/remote-jobs"


def parse(data: dict) -> list[Job]:
    return [
        Job(
            source="remotive",
            external_id=str(item["id"]),
            company=item.get("company_name", ""),
            title=item.get("title", ""),
            location=f"Remote ({item.get('candidate_required_location') or 'unspecified'})",
            url=item.get("url", ""),
            description=html_to_text(item.get("description")),
            posted_at=item.get("publication_date"),
            salary_hint=item.get("salary") or None,
        )
        for item in data.get("jobs", [])
    ]


def fetch(client: httpx.Client, category: str = "software-dev") -> list[Job]:
    data = get_json(client, URL, category=category)
    return parse(data) if isinstance(data, dict) else []
