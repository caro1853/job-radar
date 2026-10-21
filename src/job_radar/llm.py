"""Claude calls: analyze a posting against the profile, and draft an application.

Both calls use structured outputs (`messages.parse` with a Pydantic model), so
the response is a validated object, never free text to parse by hand.
"""

from __future__ import annotations

import logging
import os
from typing import TypeVar

import anthropic
from pydantic import BaseModel

from job_radar.models import Job, JobAnalysis, Profile, Tailored

log = logging.getLogger(__name__)

MODEL = os.environ.get("JOB_RADAR_MODEL", "claude-opus-5-5")
# Extraction is a simple task, so low effort keeps it fast and cheap.
# Drafting an application deserves more care.
ANALYZE_EFFORT = os.environ.get("JOB_RADAR_ANALYZE_EFFORT", "low")
TAILOR_EFFORT = os.environ.get("JOB_RADAR_TAILOR_EFFORT", "high")

T = TypeVar("T", bound=BaseModel)


class Refused(Exception):
    """Claude declined the request (stop_reason == "refusal")."""


def _profile_block(profile: Profile) -> str:
    return (
        f"<candidate>\n"
        f"Name: {profile.name}\nBased in: {profile.based_in}\n"
        f"Headline: {profile.headline}\nYears of experience: {profile.years_experience}\n"
        f"Skills: {', '.join(profile.skills)}\n"
        f"Currently learning: {', '.join(profile.learning) or 'none'}\n"
        f"Target titles: {', '.join(profile.target_titles)}\n"
        f"Minimum salary (USD/year): {profile.min_salary_usd_year or 'not set'}\n\n"
        f"CV:\n{profile.cv_text}\n"
        f"</candidate>"
    )


def _job_block(job: Job) -> str:
    salary = f"\nSalary info from the job board: {job.salary_hint}" if job.salary_hint else ""
    return (
        f"<job>\nCompany: {job.company}\nTitle: {job.title}\nLocation: {job.location}{salary}\n\n"
        f"{job.description}\n</job>"
    )


ANALYZE_SYSTEM = """You screen job postings for one candidate who lives in Colombia and wants a remote role at a US company.

For each posting, extract the facts and score the fit. Be strict and honest:
- hiring_region decides whether the candidate can even apply. "US only" includes phrases like "must be located in the US", "US work authorization required", or a list of US states. A posting that only says "Remote" with no restriction is "unclear", not "worldwide".
- Convert salaries to USD per year. Leave them null when the posting gives none; never guess.
- match_score measures skills and seniority fit only. Treat strong backend experience in another language as partly transferable, but count missing must-have skills against the score.

{profile}"""


TAILOR_SYSTEM = """You help one candidate apply to a specific job. Rewrite their real experience so it speaks to what this job needs.

Rules:
- Use only facts that appear in the CV. Never invent employers, numbers, or skills.
- Frame C#/.NET backend work in terms the job values (APIs, distributed systems, reliability, integrations) when it is relevant.
- Write in clear, natural US English.

{profile}"""


def _parse(client: anthropic.Anthropic, system: str, user: str, output: type[T], effort: str) -> T:
    response = client.beta.messages.parse(
        model=MODEL,
        max_tokens=16000,
        # The system prompt (profile + CV) is identical across jobs, so cache it.
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user}],
        output_format=output,
        output_config={"effort": effort},
        # If a safety classifier declines, the API retries on a fallback model.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    if response.stop_reason == "refusal":
        raise Refused(getattr(response.stop_details, "explanation", None) or "refused")
    if response.parsed_output is None:
        raise ValueError(f"no structured output (stop_reason={response.stop_reason})")
    return response.parsed_output


def analyze(client: anthropic.Anthropic, job: Job, profile: Profile) -> JobAnalysis:
    analysis = _parse(
        client,
        ANALYZE_SYSTEM.format(profile=_profile_block(profile)),
        _job_block(job),
        JobAnalysis,
        ANALYZE_EFFORT,
    )
    analysis.match_score = max(0, min(100, analysis.match_score))
    return analysis


def tailor(client: anthropic.Anthropic, job: Job, profile: Profile) -> Tailored:
    return _parse(
        client,
        TAILOR_SYSTEM.format(profile=_profile_block(profile)),
        f"Draft my application for this job.\n\n{_job_block(job)}",
        Tailored,
        TAILOR_EFFORT,
    )
