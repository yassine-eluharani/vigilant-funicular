"""Unit tests for applypilot.scoring.tailor.extract_json.

Pure unit tests: no DB, no app, no LLM. Imports only the function under test.
"""
from __future__ import annotations

import pytest

from applypilot.scoring.tailor import extract_json


def test_extract_json_bare():
    """Plain JSON object with no decoration parses directly."""
    raw = '{"title": "Engineer", "summary": "Builds things."}'
    out = extract_json(raw)
    assert out == {"title": "Engineer", "summary": "Builds things."}


def test_extract_json_fenced_with_language():
    """```json fenced block extracts and parses."""
    raw = (
        "```json\n"
        '{"title": "Engineer", "skills": {"lang": "Python"}}\n'
        "```"
    )
    out = extract_json(raw)
    assert out == {"title": "Engineer", "skills": {"lang": "Python"}}


def test_extract_json_fenced_no_language():
    """``` fenced block with no language tag still parses."""
    raw = (
        "```\n"
        '{"title": "Dev", "summary": "Short."}\n'
        "```"
    )
    out = extract_json(raw)
    assert out == {"title": "Dev", "summary": "Short."}


def test_extract_json_with_preamble_and_trailing_prose():
    """Preamble + JSON + trailing prose: outermost { ... } is recovered."""
    raw = (
        "Sure! Here is the JSON you asked for:\n\n"
        '{"title": "Engineer", "skills": {"lang": "Python"}}\n\n'
        "Let me know if you need anything else."
    )
    out = extract_json(raw)
    assert out == {"title": "Engineer", "skills": {"lang": "Python"}}


def test_extract_json_malformed_raises_value_error():
    """Anything that has no recoverable JSON object raises ValueError."""
    raw = "I'm sorry, I cannot produce JSON for this request."
    with pytest.raises(ValueError):
        extract_json(raw)
