"""Unit tests for applypilot.scoring.validator.

Pure unit tests: no DB, no app, no env-var setup required. The validator is
profile-driven, so each test passes a minimal profile dict directly.

Locks behavior for:
  - banned-word word-boundary matching (whole word, not substring)
  - fabrication detection in skills block (substring match in watchlist)
  - LLM leak phrase detection (always errors regardless of mode)
  - mode matrix: strict (errors) / normal (warnings) / lenient (ignored)
  - em dash always errors
  - missing required section -> error
  - false-positive guard: 'certif' is fabrication-only (NOT in BANNED_WORDS)
  - cover letter must start with 'Dear'
  - cover letter word-count thresholds per mode
"""
from __future__ import annotations

from applypilot.scoring.validator import (
    BANNED_WORDS,
    FABRICATION_WATCHLIST,
    validate_cover_letter,
    validate_json_fields,
    validate_tailored_resume,
)


def _base_profile() -> dict:
    """Minimal valid profile with no preserved companies/school so we can
    exercise field-level checks without false negatives."""
    return {
        "personal": {
            "full_name": "Jane Doe",
            "email": "jane@example.com",
            "phone": "555-1234",
        },
        "skills_boundary": {
            "languages": ["python", "javascript"],
            "frameworks": ["fastapi", "react"],
        },
        "resume_facts": {
            "preserved_companies": [],
            "preserved_projects": [],
            "preserved_school": "",
            "real_metrics": [],
        },
    }


def _ok_data(summary: str = "Engineer who ships software.") -> dict:
    """A baseline well-formed JSON resume that the validator should accept."""
    return {
        "title": "Software Engineer",
        "summary": summary,
        "skills": {"Languages": "Python, JavaScript", "Frameworks": "FastAPI, React"},
        "experience": [
            {
                "header": "Engineer at Acme",
                "subtitle": "Python | 2020-2024",
                "bullets": ["Built things that worked.", "Shipped to production."],
            }
        ],
        "projects": [
            {
                "header": "Side Project",
                "subtitle": "Python | 2023",
                "bullets": ["Wrote a tool."],
            }
        ],
        "education": "BS Computer Science",
    }


# ── 1. Banned-word word-boundary matching ────────────────────────────────

def test_banned_word_matched_whole_word_not_substring():
    """'synergy' as a standalone word is flagged. 'Synergyte' (made-up word
    containing 'synergy') is NOT flagged because matching uses \\b boundaries."""
    profile = _base_profile()

    # Whole-word case: should produce a warning in normal mode.
    data_match = _ok_data(summary="We had real synergy with the team.")
    res_match = validate_json_fields(data_match, profile, mode="normal")
    assert res_match["passed"] is True  # warnings, not errors
    assert any("synergy" in w.lower() for w in res_match["warnings"])

    # Substring case: 'Synergyte' is a single word, 'synergy' is not at a word
    # boundary. Validator must NOT flag it.
    data_no_match = _ok_data(summary="I worked on the Synergyte platform.")
    res_no_match = validate_json_fields(data_no_match, profile, mode="normal")
    # No banned-word warning at all
    banned_warnings = [w for w in res_no_match["warnings"] if "Banned words" in w]
    assert banned_warnings == []


# ── 2. Fabrication detection in skills block ─────────────────────────────

def test_fabrication_in_skills_block_errors():
    """Items from FABRICATION_WATCHLIST that appear in the skills dict produce
    a hard error (always enforced, regardless of mode)."""
    profile = _base_profile()
    data = _ok_data()
    # Inject a fabricated skill that's in the watchlist (substring match).
    data["skills"] = {"Languages": "Python, Rust, Go"}  # 'rust' is in watchlist
    res = validate_json_fields(data, profile, mode="lenient")
    assert res["passed"] is False
    assert any("Fabricated skill" in e and "rust" in e.lower() for e in res["errors"])


# ── 3. LLM leak phrase detection ─────────────────────────────────────────

def test_llm_leak_phrase_in_summary_errors():
    """LLM self-talk phrases are always errors regardless of mode."""
    profile = _base_profile()
    data = _ok_data(summary="As requested, here is the rewritten summary.")
    # 'as requested' and 'here is the' are both leak phrases.
    res = validate_json_fields(data, profile, mode="lenient")
    assert res["passed"] is False
    assert any("LLM self-talk" in e for e in res["errors"])


# ── 4. Mode matrix: strict / normal / lenient ────────────────────────────

def test_mode_matrix_banned_word_severity():
    """Same input — 'passionate' (a banned word) — should produce:
      - strict:  error (passed=False)
      - normal:  warning (passed=True)
      - lenient: nothing (passed=True, no warning)
    """
    profile = _base_profile()
    data = _ok_data(summary="I am a passionate engineer who builds tools.")

    strict = validate_json_fields(data, profile, mode="strict")
    assert strict["passed"] is False
    assert any("Banned words" in e for e in strict["errors"])

    normal = validate_json_fields(data, profile, mode="normal")
    assert normal["passed"] is True
    assert any("Banned words" in w for w in normal["warnings"])

    lenient = validate_json_fields(data, profile, mode="lenient")
    assert lenient["passed"] is True
    assert all("Banned words" not in w for w in lenient["warnings"])
    assert all("Banned words" not in e for e in lenient["errors"])


# ── 5. Em dash always errors (validate_tailored_resume / cover) ─────────

def test_em_dash_always_errors_in_resume_text():
    """Em dash in tailored resume text is always an error (sanitize should
    have caught it; the validator's job is the safety net)."""
    profile = _base_profile()
    text = (
        "Jane Doe\nSoftware Engineer\n\n"
        "SUMMARY\nEngineer \u2014 ships software.\n\n"
        "TECHNICAL SKILLS\nPython, JavaScript\n\n"
        "EXPERIENCE\nEngineer at Acme\n\n"
        "PROJECTS\nSide Project\n\n"
        "EDUCATION\nBS CS\n"
    )
    res = validate_tailored_resume(text, profile)
    assert res["passed"] is False
    assert any("em dash" in e.lower() for e in res["errors"])


def test_em_dash_always_errors_in_cover_letter():
    """Em dash always errors in cover letter regardless of mode."""
    text = "Dear Hiring Manager,\n\nI built the thing \u2014 it worked."
    res = validate_cover_letter(text, mode="lenient")
    assert res["passed"] is False
    assert any("em dash" in e.lower() for e in res["errors"])


# ── 6. Missing required section -> error ─────────────────────────────────

def test_missing_required_field_errors():
    """A missing top-level field on the JSON should be a hard error."""
    profile = _base_profile()
    data = _ok_data()
    del data["education"]  # required
    res = validate_json_fields(data, profile, mode="normal")
    assert res["passed"] is False
    assert any("education" in e.lower() for e in res["errors"])


def test_missing_required_section_in_resume_text():
    """Tailored resume text missing a required section header is an error."""
    profile = _base_profile()
    # Omit EXPERIENCE entirely.
    text = (
        "Jane Doe\nSoftware Engineer\n\n"
        "SUMMARY\nGood engineer.\n\n"
        "TECHNICAL SKILLS\nPython\n\n"
        "PROJECTS\nThing\n\n"
        "EDUCATION\nBS CS\n"
    )
    res = validate_tailored_resume(text, profile)
    assert res["passed"] is False
    assert any("EXPERIENCE" in e for e in res["errors"])


# ── 7. False-positive guard: 'certif' is fabrication, not banned ────────

def test_certif_not_in_banned_words_list():
    """'certif' lives in FABRICATION_WATCHLIST, not BANNED_WORDS. A summary
    containing 'certifications' should NOT trigger a banned-word match."""
    # Lock the listing itself.
    assert "certif" not in BANNED_WORDS
    assert "certif" in FABRICATION_WATCHLIST

    profile = _base_profile()
    # Use a benign summary that includes 'certifications' as a regular word.
    # Skills must NOT contain 'certif' or fabrication will fire.
    data = _ok_data(summary="Engineer who values certifications.")
    res = validate_json_fields(data, profile, mode="strict")
    # No banned-word error from 'certif'
    banned_errors = [e for e in res["errors"] if "Banned words" in e]
    assert banned_errors == []


# ── 8. Cover letter must start with 'Dear' ───────────────────────────────

def test_cover_letter_must_start_with_dear():
    text = "Hello team,\n\nI built the thing. Sincerely, Jane"
    res = validate_cover_letter(text, mode="normal")
    assert res["passed"] is False
    assert any("Dear" in e for e in res["errors"])


def test_cover_letter_starting_with_dear_passes_start_check():
    text = "Dear Hiring Manager,\n\nI built the thing. Sincerely, Jane"
    res = validate_cover_letter(text, mode="normal")
    # No 'Must start with' error
    assert all("Must start with" not in e for e in res["errors"])


# ── 9. Cover letter word-count threshold ─────────────────────────────────

def test_cover_letter_word_count_strict_vs_normal():
    """strict mode caps at 250; normal mode caps at 275 (warning)."""
    body = "word " * 260  # 260 words
    text = "Dear Hiring Manager, " + body
    # strict: > 250 -> error
    strict = validate_cover_letter(text, mode="strict")
    assert strict["passed"] is False
    assert any("Too long" in e for e in strict["errors"])

    # normal: 260 is between 250 and 275 -> no warning, no error from word count
    normal = validate_cover_letter(text, mode="normal")
    word_count_warnings = [w for w in normal["warnings"] if "Long" in w or "words" in w.lower()]
    word_count_errors = [e for e in normal["errors"] if "Too long" in e]
    assert word_count_errors == []
    # 260 is below normal's 275 threshold -> no Long warning either
    assert word_count_warnings == []

    # normal at 280 -> warning
    body_long = "word " * 280
    text_long = "Dear Hiring Manager, " + body_long
    normal_long = validate_cover_letter(text_long, mode="normal")
    assert any("Long" in w for w in normal_long["warnings"])
