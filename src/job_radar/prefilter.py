"""Cheap rules that run before the LLM, so we only pay to analyze plausible jobs."""

from __future__ import annotations

from job_radar.models import Job, Profile

# Location text that means "maybe hireable from Colombia". Anything else that
# names a place (e.g. "San Francisco, CA") is treated as on-site and dropped.
REMOTE_HINTS = ("remote", "anywhere", "worldwide", "global", "latam", "latin america", "americas", "colombia")


def title_ok(job: Job, profile: Profile) -> bool:
    title = job.title.lower()
    if any(word.lower() in title for word in profile.exclude_title_keywords):
        return False
    return any(word.lower() in title for word in profile.title_keywords)


def location_ok(job: Job) -> bool:
    location = job.location.lower().strip()
    return not location or any(hint in location for hint in REMOTE_HINTS)


def keep(job: Job, profile: Profile) -> bool:
    return title_ok(job, profile) and location_ok(job)
