"""Job fit scoring: LLM-powered evaluation of candidate-job match quality."""

import json
import logging
import re
import time
from datetime import datetime, timezone

from applypilot.config import get_resume_text, load_profile, load_search_config
from applypilot.database import get_connection, get_jobs_by_stage, upsert_user_job
from applypilot.llm import get_client

log = logging.getLogger(__name__)


# ── Scoring Prompt ────────────────────────────────────────────────────────

_SCORE_PROMPT_TEMPLATE = """You are a job fit evaluator. Assess how well a candidate matches a job — skill fit AND geographic eligibility both matter.

CANDIDATE CONTEXT:
- Location: {candidate_location}
- Work authorization: {work_auth_summary}
- Target regions: {target_regions}

═══════════════════════════════════════════════════
SCORING RULES — APPLY IN ORDER:
═══════════════════════════════════════════════════

STEP 1 — GEOGRAPHIC ELIGIBILITY CHECK (apply first, can cap the score):
Look for any signals in the job title, location field, or description that indicate geographic restriction:

  HARD BLOCK (score 1-2, regardless of skill match):
  • Job requires authorization/right to work in a country the candidate cannot access
    (e.g. "authorized to work in the US", "right to work in the UK", "eligible to work in Canada")
  • Visa sponsorship explicitly declined: "no sponsorship", "will not sponsor", "unable to sponsor"
  • Job is remote-only within a single country the candidate is not in
    (e.g. "US remote only", "Remote – UK", "must reside in [country]")
  • Job location is in a non-target country with no remote option

  POSSIBLE BLOCK (cap score at 5):
  • Job is ambiguously "remote" with no country restriction stated, but is on a US-centric job board
    and shows no explicit worldwide/international availability
  • Job requires local presence for part of the time in a non-target region

  ACCESSIBLE (no cap — score on skill fit alone):
  • Explicitly worldwide remote / "work from anywhere" / no location restriction
  • Job is located in the candidate's target regions: {target_regions}
  • Job explicitly states it is open to international candidates or offers relocation

STEP 2 — SKILL & EXPERIENCE MATCH (only if geographic access confirmed/likely):
- 9-10: Perfect match — direct experience in nearly all required skills, seniority level fits
- 7-8: Strong match — most required skills present, minor gaps
- 5-6: Moderate match — relevant background but missing key requirements
- 3-4: Weak match — significant skill gaps
- 1-2: Wrong field or geographic block (see Step 1)

═══════════════════════════════════════════════════

RESPOND IN EXACTLY THIS FORMAT (no other text):
SCORE: [1-10]
KEYWORDS: [comma-separated ATS keywords from the job that match the candidate]
REASONING: [2-3 sentences — lead with geographic eligibility assessment, then skill fit]"""


def _build_score_prompt(profile: dict, search_cfg: dict) -> str:
    personal = profile.get("personal", {})
    wa = profile.get("work_authorization", {})

    city = personal.get("city", "Unknown")
    country = personal.get("country", "Unknown")
    candidate_location = f"{city}, {country}"

    authorized = wa.get("legally_authorized_to_work", False)
    needs_sponsorship = wa.get("require_sponsorship", True)
    permit = wa.get("work_permit_type", "")

    if authorized and not needs_sponsorship:
        work_auth_summary = f"Legally authorized to work, no sponsorship needed. Permit: {permit or 'N/A'}"
    elif needs_sponsorship:
        work_auth_summary = (
            f"NOT locally authorized — requires visa sponsorship to work abroad. "
            f"Permit type: {permit or 'none'}. "
            f"Jobs that explicitly refuse sponsorship are INACCESSIBLE."
        )
    else:
        work_auth_summary = f"Authorization status unclear. Permit: {permit or 'N/A'}"

    accept = search_cfg.get("location_accept", [])
    if accept:
        target_regions = ", ".join(a.title() for a in accept[:15])
    else:
        target_regions = "Worldwide remote, GCC/MENA region"

    return _SCORE_PROMPT_TEMPLATE.format(
        candidate_location=candidate_location,
        work_auth_summary=work_auth_summary,
        target_regions=target_regions,
    )


def _parse_score_response(response: str) -> dict:
    score = 0
    keywords = ""
    reasoning = response

    for line in response.split("\n"):
        line = line.strip()
        if line.startswith("SCORE:"):
            try:
                score = int(re.search(r"\d+", line).group())
                score = max(1, min(10, score))
            except (AttributeError, ValueError):
                score = 0
        elif line.startswith("KEYWORDS:"):
            keywords = line.replace("KEYWORDS:", "").strip()
        elif line.startswith("REASONING:"):
            reasoning = line.replace("REASONING:", "").strip()

    return {"score": score, "keywords": keywords, "reasoning": reasoning}


def score_job(resume_text: str, job: dict, score_prompt: str) -> dict:
    job_text = (
        f"TITLE: {job['title']}\n"
        f"COMPANY: {job.get('site', 'Unknown')}\n"
        f"LOCATION: {job.get('location', 'Not specified')}\n\n"
        f"DESCRIPTION:\n{(job.get('full_description') or '')[:6000]}"
    )

    messages = [
        {"role": "system", "content": score_prompt},
        {"role": "user", "content": f"RESUME:\n{resume_text}\n\n---\n\nJOB POSTING:\n{job_text}"},
    ]

    try:
        client = get_client()
        response = client.chat(messages, max_tokens=512, temperature=0.2)
        return _parse_score_response(response)
    except Exception as e:
        log.error("LLM error scoring job '%s': %s", job.get("title", "?"), e)
        return {"score": 0, "keywords": "", "reasoning": f"LLM error: {e}"}


def run_scoring(user_id: int | None = None, limit: int = 0, rescore: bool = False) -> dict:
    """Score unscored jobs that have full descriptions.

    Args:
        user_id: If provided, reads profile/resume from DB and writes scores
                 to user_jobs. If None, falls back to filesystem (legacy).
        limit: Maximum number of jobs to score in this run.
        rescore: If True, re-score all jobs (not just unscored ones).
    """
    resume_text = get_resume_text(user_id)
    profile = load_profile(user_id)
    search_cfg = load_search_config(user_id)
    score_prompt = _build_score_prompt(profile, search_cfg)
    conn = get_connection()

    if user_id is not None:
        if rescore:
            query = (
                "SELECT j.* FROM jobs j WHERE j.full_description IS NOT NULL"
            )
            if limit > 0:
                query += f" LIMIT {limit}"
            rows = conn.execute(query).fetchall()
            if rows:
                cols = rows[0].keys()
                jobs = [dict(zip(cols, r)) for r in rows]
            else:
                jobs = []
        else:
            jobs = get_jobs_by_stage(conn=conn, stage="pending_score", limit=limit, user_id=user_id)
    else:
        if rescore:
            query = "SELECT * FROM jobs WHERE full_description IS NOT NULL"
            if limit > 0:
                query += f" LIMIT {limit}"
            rows = conn.execute(query).fetchall()
            if rows:
                cols = rows[0].keys()
                jobs = [dict(zip(cols, r)) for r in rows]
            else:
                jobs = []
        else:
            jobs = get_jobs_by_stage(conn=conn, stage="pending_score", limit=limit)

    if not jobs:
        log.info("No unscored jobs with descriptions found.")
        return {"scored": 0, "errors": 0, "elapsed": 0.0, "distribution": []}

    if jobs and not isinstance(jobs[0], dict):
        columns = jobs[0].keys()
        jobs = [dict(zip(columns, row)) for row in jobs]

    log.info("Scoring %d jobs — location: %s, sponsorship needed: %s",
             len(jobs),
             profile.get("personal", {}).get("country", "?"),
             profile.get("work_authorization", {}).get("require_sponsorship", "?"))

    t0 = time.time()
    completed = 0
    errors = 0
    results: list[dict] = []

    for job in jobs:
        result = score_job(resume_text, job, score_prompt)
        result["url"] = job["url"]
        completed += 1

        if result["score"] == 0:
            errors += 1

        results.append(result)

        log.info(
            "[%d/%d] score=%d  %s",
            completed, len(jobs), result["score"], job.get("title", "?")[:60],
        )

    # Write scores to user_jobs (or legacy jobs table)
    now = datetime.now(timezone.utc).isoformat()
    for r in results:
        if user_id is not None:
            upsert_user_job(
                conn, user_id, r["url"],
                fit_score=r["score"],
                score_reasoning=f"{r['keywords']}\n{r['reasoning']}",
                scored_at=now,
            )
        else:
            conn.execute(
                "UPDATE jobs SET fit_score = ?, score_reasoning = ?, scored_at = ? WHERE url = ?",
                (r["score"], f"{r['keywords']}\n{r['reasoning']}", now, r["url"]),
            )
    if user_id is None:
        conn.commit()

    elapsed = time.time() - t0
    log.info("Done: %d scored in %.1fs (%.1f jobs/sec)", len(results), elapsed, len(results) / elapsed if elapsed > 0 else 0)

    if user_id is not None:
        dist = conn.execute(
            "SELECT fit_score, COUNT(*) FROM user_jobs "
            "WHERE user_id = ? AND fit_score IS NOT NULL "
            "GROUP BY fit_score ORDER BY fit_score DESC",
            (user_id,),
        ).fetchall()
    else:
        dist = conn.execute(
            "SELECT fit_score, COUNT(*) FROM jobs "
            "WHERE fit_score IS NOT NULL "
            "GROUP BY fit_score ORDER BY fit_score DESC"
        ).fetchall()
    distribution = [(row[0], row[1]) for row in dist]

    return {
        "scored": len(results),
        "errors": errors,
        "elapsed": elapsed,
        "distribution": distribution,
    }
