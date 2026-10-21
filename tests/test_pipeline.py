"""Offline tests. Source fixtures follow each API's documented response shape;
they are not recordings of live responses."""

from types import SimpleNamespace

import pytest

from job_radar import db, digest, llm, prefilter
from job_radar.models import Job, JobAnalysis, Profile
from job_radar.sources import ashby, greenhouse, html_to_text, lever, remotive

PROFILE = Profile(
    name="Caro",
    headline="Senior backend engineer",
    years_experience=15,
    skills=["C#", ".NET"],
    target_titles=["AI Engineer"],
    cv_text="15 years of C# backend work.",
)


def job(**kw) -> Job:
    base = dict(source="greenhouse", external_id="1", company="Acme", title="Senior AI Engineer",
                location="Remote", url="https://example.com/1")
    return Job(**(base | kw))


def analysis(**kw) -> JobAnalysis:
    base = dict(hiring_region="latam_ok", region_evidence="", seniority="senior",
                is_ai_integration_role=True, employment_type="contract",
                salary_min_usd_year=None, salary_max_usd_year=None, required_skills=["Python"],
                nice_to_have_skills=[], matching_skills=["APIs"], missing_skills=["Python"],
                match_score=80, reasoning="Good fit.")
    return JobAnalysis(**(base | kw))


def test_html_to_text_handles_double_escaped_html():
    assert html_to_text("&lt;p&gt;Hello &amp;amp; welcome&lt;/p&gt;&lt;ul&gt;&lt;li&gt;Python&lt;/li&gt;&lt;/ul&gt;") == "Hello & welcome\nPython"


def test_greenhouse_parse():
    data = {"jobs": [{"id": 42, "title": "AI Engineer", "location": {"name": "Remote - Americas"},
                      "absolute_url": "https://boards.greenhouse.io/x/jobs/42",
                      "content": "&lt;p&gt;Build RAG&lt;/p&gt;", "updated_at": "2026-10-01T00:00:00Z"}]}
    [j] = greenhouse.parse(data, "X")
    assert (j.uid, j.location, j.description) == ("greenhouse:42", "Remote - Americas", "Build RAG")


def test_lever_parse_marks_remote_and_salary():
    data = [{"id": "abc", "text": "LLM Engineer", "hostedUrl": "https://jobs.lever.co/x/abc",
             "categories": {"location": "New York"}, "workplaceType": "remote",
             "descriptionPlain": "Agents.", "lists": [{"text": "Requirements", "content": "<li>Python</li>"}],
             "createdAt": 1760000000000, "salaryRange": {"min": 150000, "max": 200000, "currency": "USD", "interval": "per-year-salary"}}]
    [j] = lever.parse(data, "X")
    assert j.location == "Remote (New York)"
    assert "Requirements\nPython" in j.description
    assert j.salary_hint.startswith("150000-200000 USD")


def test_ashby_parse_skips_unlisted():
    data = {"jobs": [
        {"id": "a1", "title": "AI Engineer", "location": "", "isRemote": True, "jobUrl": "https://jobs.ashbyhq.com/x/a1",
         "descriptionPlain": "Tool use.", "compensation": {"compensationTierSummary": "$180K – $220K"}},
        {"id": "a2", "title": "Hidden", "isListed": False, "jobUrl": "u"},
    ]}
    [j] = ashby.parse(data, "X")
    assert (j.location, j.salary_hint) == ("Remote", "$180K – $220K")


def test_remotive_parse():
    data = {"jobs": [{"id": 7, "url": "https://remotive.com/7", "title": "AI Dev", "company_name": "Y",
                      "candidate_required_location": "LATAM", "description": "<p>Hi</p>", "salary": ""}]}
    [j] = remotive.parse(data)
    assert (j.company, j.location, j.salary_hint) == ("Y", "Remote (LATAM)", None)


@pytest.mark.parametrize("title,location,expected", [
    ("Senior AI Engineer", "Remote", True),
    ("Senior AI Engineer", "San Francisco, CA", False),
    ("Senior AI Engineer", "", True),
    ("AI Engineering Intern", "Remote", False),
    ("Account Executive", "Remote", False),
    ("Backend Developer", "Remote - LATAM", True),
])
def test_prefilter(title, location, expected):
    assert prefilter.keep(job(title=title, location=location), PROFILE) is expected


def test_rank_filters_region_score_and_tracked_jobs():
    rows = [
        (job(external_id="1"), analysis(match_score=90, hiring_region="us_only"), None),
        (job(external_id="2"), analysis(match_score=70, hiring_region="unclear"), None),
        (job(external_id="3"), analysis(match_score=70, hiring_region="worldwide"), None),
        (job(external_id="4"), analysis(match_score=50), None),
        (job(external_id="5"), analysis(match_score=95), "applied"),
    ]
    assert [j.external_id for j, _ in digest.rank(rows)] == ["3", "2"]
    assert [j.external_id for j, _ in digest.rank(rows, include_unclear=False)] == ["3"]


def test_render_lists_jobs_and_skill_gaps():
    ranked = [(job(), analysis(salary_min_usd_year=120000, salary_max_usd_year=160000))]
    text = digest.render(ranked)
    assert "| 80 | [Senior AI Engineer](https://example.com/1) | Acme | LATAM OK | $120k-160k | yes |" in text
    assert "- python (1 jobs)" in text


def test_store_roundtrip(tmp_path):
    store = db.Store(tmp_path / "t.db")
    assert store.add_jobs([job(), job()]) == 1
    assert [j.uid for j in store.unanalyzed()] == ["greenhouse:1"]
    store.save_analysis("greenhouse:1", analysis(), "m")
    assert store.unanalyzed() == []
    store.set_status("greenhouse:1", "applied")
    [(_, _, status)] = store.analyzed()
    assert status == "applied"
    with pytest.raises(ValueError):
        store.set_status("greenhouse:1", "maybe")


def test_analyzed_since_keeps_only_recent(tmp_path):
    store = db.Store(tmp_path / "t.db")
    store.add_jobs([job()])
    store.save_analysis("greenhouse:1", analysis(), "m")
    assert len(store.analyzed(since="2000-01-01T00:00:00+00:00")) == 1
    assert store.analyzed(since="2999-01-01T00:00:00+00:00") == []


class FakeMessages:
    def __init__(self, response):
        self.response, self.calls = response, []

    def parse(self, **kw):
        self.calls.append(kw)
        return self.response


def fake_client(response):
    messages = FakeMessages(response)
    return SimpleNamespace(beta=SimpleNamespace(messages=messages)), messages


def test_analyze_sends_cached_profile_and_clamps_score():
    client, messages = fake_client(SimpleNamespace(stop_reason="end_turn", parsed_output=analysis(match_score=140)))
    result = llm.analyze(client, job(), PROFILE)
    assert result.match_score == 100
    call = messages.calls[0]
    assert call["output_format"] is JobAnalysis
    assert call["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "15 years of C# backend work." in call["system"][0]["text"]


def test_analyze_raises_on_refusal():
    client, _ = fake_client(SimpleNamespace(stop_reason="refusal", parsed_output=None,
                                            stop_details=SimpleNamespace(explanation="no")))
    with pytest.raises(llm.Refused):
        llm.analyze(client, job(), PROFILE)
