"""Data models shared by every part of the pipeline."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Job(BaseModel):
    """A job posting, normalized from any source."""

    source: str  # "greenhouse", "lever", "ashby", "remotive", "manual"
    external_id: str
    company: str
    title: str
    location: str = ""
    url: str
    description: str = ""  # plain text
    posted_at: str | None = None  # ISO 8601 when the source gives it
    salary_hint: str | None = None  # raw salary text from the source, if any

    @property
    def uid(self) -> str:
        return f"{self.source}:{self.external_id}"


class Profile(BaseModel):
    """Who is looking for a job. Loaded from profile.yaml."""

    name: str
    based_in: str = "Colombia"
    headline: str
    years_experience: int
    skills: list[str]
    learning: list[str] = Field(default_factory=list)
    target_titles: list[str]
    min_salary_usd_year: int | None = None
    title_keywords: list[str] = Field(
        default_factory=lambda: ["engineer", "developer", "architect"]
    )
    exclude_title_keywords: list[str] = Field(
        default_factory=lambda: ["intern", "sales", "recruiter", "designer", "director"]
    )
    cv_text: str


HiringRegion = Literal["latam_ok", "worldwide", "us_only", "other_region", "unclear"]


class JobAnalysis(BaseModel):
    """What the LLM extracts from one posting, scored against the profile."""

    hiring_region: HiringRegion = Field(
        description=(
            "Can someone living in Latin America (Colombia) be hired? "
            "latam_ok: LATAM/Americas/Colombia named, or contractors/EOR accepted from there. "
            "worldwide: open to anywhere. us_only: must live in or be authorized to work in the US. "
            "other_region: restricted to another region (EU, India...). unclear: not stated."
        )
    )
    region_evidence: str = Field(description="Short quote from the posting that supports hiring_region, or '' if none.")
    seniority: Literal["junior", "mid", "senior", "staff_plus", "unknown"]
    is_ai_integration_role: bool = Field(
        description="True if the core of the job is building products or systems on top of LLMs/AI APIs (RAG, agents, tool use, evals, AI platform)."
    )
    employment_type: Literal["full_time", "contract", "unknown"]
    salary_min_usd_year: int | None = Field(description="Lower bound in USD per year if stated, else null.")
    salary_max_usd_year: int | None = Field(description="Upper bound in USD per year if stated, else null.")
    required_skills: list[str]
    nice_to_have_skills: list[str]
    matching_skills: list[str] = Field(description="Required or nice-to-have skills the candidate already has.")
    missing_skills: list[str] = Field(description="Required skills the candidate does not show yet.")
    match_score: int = Field(description="0-100: how strong this candidate is for this job, ignoring location.")
    reasoning: str = Field(description="Two sentences: why this score, and the biggest risk.")


class Tailored(BaseModel):
    """Application material drafted for one job."""

    cv_summary: str = Field(description="A 3-4 sentence professional summary tailored to the job.")
    cv_bullets: list[str] = Field(description="5-7 achievement bullets rewritten from the CV to fit the job. Never invent facts.")
    cover_letter: str = Field(description="A short cover letter, under 250 words.")
    questions_to_prepare: list[str] = Field(description="3-5 interview questions this job will likely ask.")
