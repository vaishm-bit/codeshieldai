import json

import pytest

from app.ai.errors import AIResponseError
from app.ai.parsing import (
    extract_json,
    parse_explanation,
    parse_fix,
    parse_review,
    valid_line,
)
from app.ai.types import Confidence, ObservationCategory


def test_extract_json_handles_fences_prose_and_raw_newlines():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Sure! Here it is: {"a": 1} Hope that helps.') == {"a": 1}
    assert extract_json('{"code": "line1\nline2"}') == {"code": "line1\nline2"}


def test_extract_json_rejects_garbage():
    for text in ("no json here", "[1, 2]", "{broken"):
        with pytest.raises(AIResponseError):
            extract_json(text)


def test_parse_explanation():
    reply = json.dumps(
        {
            "meaning": " Shell injection. ",
            "why_vulnerable": "User input reaches the shell.",
            "vulnerable_code": "Line 2: subprocess.call(cmd, shell=True)",
            "risks": "Remote code execution",
            "prevention": ["Avoid shell=True", "", "Validate input"],
        }
    )
    result = parse_explanation(reply)
    assert result.meaning == "Shell injection."
    assert result.risks == ["Remote code execution"]
    assert result.prevention == ["Avoid shell=True", "Validate input"]


def test_parse_explanation_requires_core_fields():
    with pytest.raises(AIResponseError):
        parse_explanation('{"meaning": "x"}')


def test_parse_fix_strips_fences_and_flags_unfixable():
    fixed = parse_fix(
        json.dumps({"fixable": True, "fixed_code": "```python\nx = 1\n```", "explanation": "ok", "changes": ["a"]})
    )
    assert fixed.fixable and fixed.fixed_code == "x = 1" and fixed.changes == ["a"]

    cannot = parse_fix(json.dumps({"fixable": "false", "fixed_code": "x", "explanation": "needs context"}))
    assert not cannot.fixable and cannot.fixed_code == ""

    empty = parse_fix(json.dumps({"fixable": True, "fixed_code": "  ", "explanation": "?"}))
    assert not empty.fixable

    with pytest.raises(AIResponseError):
        parse_fix('{"fixed_code": "x = 1"}')


def test_parse_review_is_tolerant_per_item():
    items = [
        {"category": "Error Handling", "title": "Bare except", "description": "Hides errors", "line": "12", "confidence": "HIGH"},
        {"category": "nonsense", "title": "Odd", "description": "d", "line": True, "confidence": "certain"},
        {"title": "", "description": "no title"},
        "not an object",
    ]
    result = parse_review(json.dumps({"observations": items}))
    assert len(result) == 2
    assert result[0].category is ObservationCategory.ERROR_HANDLING
    assert result[0].line == 12 and result[0].confidence is Confidence.HIGH
    assert result[1].category is ObservationCategory.BEST_PRACTICE
    assert result[1].line is None and result[1].confidence is Confidence.LOW


def test_parse_review_caps_results_and_requires_list():
    many = [{"title": f"t{i}", "description": "d"} for i in range(25)]
    assert len(parse_review(json.dumps({"observations": many}))) == 10
    assert parse_review('{"observations": []}') == []
    with pytest.raises(AIResponseError):
        parse_review('{"observations": "none"}')


def test_valid_line():
    assert valid_line(5, 10) == 5
    assert valid_line(0, 10) is None and valid_line(11, 10) is None and valid_line(None, 10) is None
