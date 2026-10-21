"""Lever Postings API: https://github.com/lever/postings-api"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

from job_radar.models import Job
from job_radar.sources import get_json, html_to_text

URL = "https://api.lever.co/v0/postings/{slug}"


def _description(item: dict) -> str:
    parts = [item.get("descriptionPlain") or html_to_text(item.get("description"))]
    for section in item.get("lists", []):
        parts.append(f"{section.get('text', '')}\n{html_to_text(section.get('content'))}")
    parts.append(item.get("additionalPlain") or "")
    return "\n\n".join(p for p in parts if p).strip()


def parse(data: list, company: str) -> list[Job]:
    jobs = []
    for item in data:
        categories = item.get("categories") or {}
        created = item.get("createdAt")
        location = categories.get("location", "")
        if item.get("workplaceType") == "remote" and "remote" not in location.lower():
            location = f"Remote ({location})" if location else "Remote"
        salary = item.get("salaryRange") or {}
        jobs.append(
            Job(
                source="lever",
                external_id=item["id"],
                company=company,
                title=item.get("text", ""),
                location=location,
                url=item.get("hostedUrl", ""),
                description=_description(item),
                posted_at=datetime.fromtimestamp(created / 1000, timezone.utc).isoformat() if created else None,
                salary_hint=(
                    f"{salary.get('min')}-{salary.get('max')} {salary.get('currency', '')} {salary.get('interval', '')}".strip()
                    if salary
                    else None
                ),
            )
        )
    return jobs


def fetch(client: httpx.Client, slug: str, company: str) -> list[Job]:
    data = get_json(client, URL.format(slug=slug), mode="json")
    return parse(data, company) if isinstance(data, list) else []
