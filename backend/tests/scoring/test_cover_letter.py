"""Unit tests for applypilot.scoring.cover_letter._strip_preamble.

Pure unit tests: no DB, no LLM, no app. Imports only the helper.
"""
from __future__ import annotations

from applypilot.scoring.cover_letter import _strip_preamble


def test_strip_preamble_no_preamble_returns_unchanged():
    """A letter that already starts with 'Dear ...' is returned as-is."""
    text = "Dear Hiring Manager,\n\nI built the thing.\n\nBest,\nJane"
    assert _strip_preamble(text) == text


def test_strip_preamble_removes_meta_commentary_before_dear():
    """A letter with 'Here's your cover letter:' preamble before 'Dear ...'
    should return starting at 'Dear ...'."""
    raw = (
        "Here's your cover letter:\n\n"
        "Dear Hiring Manager,\n\n"
        "I built the thing."
    )
    out = _strip_preamble(raw)
    assert out.startswith("Dear Hiring Manager,")
    assert "Here's your cover letter" not in out


def test_strip_preamble_dear_in_body_no_preamble_not_stripped():
    """Regression: 'dear' appearing as a regular word later in the letter
    should NOT trigger stripping when the letter already starts with 'Dear'.

    The current implementation finds the FIRST 'dear' and only strips when
    its index > 0. If the letter starts with 'Dear', dear_idx == 0 and no
    stripping happens — body content is preserved verbatim.
    """
    text = (
        "Dear Hiring Manager,\n\n"
        "I'm a dear friend of the team and I want to help.\n\n"
        "Best,\nJane"
    )
    out = _strip_preamble(text)
    assert out == text
    assert "I'm a dear friend" in out
