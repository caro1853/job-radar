"""Greenhouse Job Board API: https://developers.greenhouse.io/job-board.html"""

from __future__ import annotations

import httpx

from job_radar.models import Job
from job_radar.sources import get_json, html_to_text

URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"


def parse(data: dict, company: str) -> list[Job]:
    return [
        Job(
            source="greenhouse",
            external_id=str(item["id"]),
            company=company,
            title=item.get("title", ""),
            location=(item.get("location") or {}).get("name", ""),
            url=item.get("absolute_url", ""),
            description=html_to_text(item.get("content")),
            posted_at=item.get("updated_at"),
        )
        for item in data.get("jobs", [])
    ]


def fetch(client: httpx.Client, slug: str, company: str) -> list[Job]:
    data = get_json(client, URL.format(slug=slug), content="true")
    return parse(data, company) if isinstance(data, dict) else []
