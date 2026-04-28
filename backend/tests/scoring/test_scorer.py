"""Unit tests for applypilot.scoring.scorer._parse_score_response.

Pure unit tests: no DB, no LLM, no app. Imports only the parser.
"""
from __future__ import annotations

from applypilot.scoring.scorer import _parse_score_response


def test_parse_score_response_well_formed():
    """A well-formed response yields the integer score, keywords, reasoning."""
    raw = (
        "SCORE: 7\n"
        "KEYWORDS: python, fastapi, postgres\n"
        "REASONING: Strong match on backend stack, minor gap on frontend."
    )
    out = _parse_score_response(raw)
    assert out["score"] == 7
    assert out["keywords"] == "python, fastapi, postgres"
    assert "Strong match" in out["reasoning"]


def test_parse_score_response_missing_score_line_returns_zero():
    """No SCORE: line at all -> score defaults to 0 (current behavior)."""
    raw = (
        "KEYWORDS: python\n"
        "REASONING: Some reasoning text."
    )
    out = _parse_score_response(raw)
    assert out["score"] == 0
    assert out["keywords"] == "python"


def test_parse_score_response_clamps_above_ten():
    """SCORE: 11 should clamp to 10 (max)."""
    raw = (
        "SCORE: 11\n"
        "KEYWORDS: x\n"
        "REASONING: y"
    )
    out = _parse_score_response(raw)
    assert out["score"] == 10


def test_parse_score_response_non_numeric_score_returns_zero():
    """SCORE: abc -> regex finds no digits -> score=0."""
    raw = (
        "SCORE: abc\n"
        "KEYWORDS: x\n"
        "REASONING: y"
    )
    out = _parse_score_response(raw)
    assert out["score"] == 0
