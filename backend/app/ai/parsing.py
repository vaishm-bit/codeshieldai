"""Turning raw model text into validated, typed results. Bad output raises AIResponseError."""

import json
import re
from dataclasses import dataclass, field

from app.ai.errors import AIResponseError
from app.ai.types import Confidence, ObservationCategory

MAX_OBSERVATIONS = 10
MAX_LIST_ITEMS = 8


def extract_json(text: str) -> dict:
    """Find the JSON object in a model reply, tolerating code fences and extra prose."""
    cleaned = text.strip()
    cleaned = re.sub(r"^```[A-Za-z0-9_-]*[ \t]*\n", "", cleaned)
    cleaned = re.sub(r"\n?```\s*$", "", cleaned)
    first, last = cleaned.find("{"), cleaned.rfind("}")
    candidates = [cleaned] + ([cleaned[first : last + 1]] if 0 <= first < last else [])
    for candidate in candidates:
        try:
            data = json.loads(candidate, strict=False)  # strict=False allows raw newlines in strings
        except ValueError:
            continue
        if isinstance(data, dict):
            return data
    raise AIResponseError("The AI response was not valid JSON.")


def _text(value: object, *, required: bool = False, limit: int | None = None) -> str:
    if value is None:
        value = ""
    if not isinstance(value, str):
        value = str(value)
    value = value.strip()
    if required and not value:
        raise AIResponseError("The AI response was missing a required field.")
    return value[:limit] if limit else value


def _text_list(value: object) -> list[str]:
    if value is None:
        return []
    items = [value] if isinstance(value, str) else value if isinstance(value, list) else [value]
    cleaned = [_text(item) for item in items]
    return [item for item in cleaned if item][:MAX_LIST_ITEMS]


def _strip_fences(code: str) -> str:
    code = re.sub(r"^```[A-Za-z0-9_-]*[ \t]*\n", "", code.strip("\n"))
    return re.sub(r"\n```\s*$", "", code)


# ----------------------------------------------------------------- explanation
@dataclass(frozen=True)
class ExplanationPayload:
    meaning: str
    why_vulnerable: str
    vulnerable_code: str = ""
    risks: list[str] = field(default_factory=list)
    prevention: list[str] = field(default_factory=list)


def parse_explanation(text: str) -> ExplanationPayload:
    data = extract_json(text)
    return ExplanationPayload(
        meaning=_text(data.get("meaning"), required=True),
        why_vulnerable=_text(data.get("why_vulnerable"), required=True),
        vulnerable_code=_text(data.get("vulnerable_code")),
        risks=_text_list(data.get("risks")),
        prevention=_text_list(data.get("prevention")),
    )


# ------------------------------------------------------------------------- fix
@dataclass(frozen=True)
class FixPayload:
    fixable: bool
    fixed_code: str
    explanation: str
    changes: list[str] = field(default_factory=list)


def parse_fix(text: str) -> FixPayload:
    data = extract_json(text)
    fixable = data.get("fixable", True)
    fixable = fixable if isinstance(fixable, bool) else str(fixable).strip().lower() != "false"
    fixed_code = _strip_fences(_text(data.get("fixed_code"))) if fixable else ""
    return FixPayload(
        fixable=fixable and bool(fixed_code.strip()),
        fixed_code=fixed_code,
        explanation=_text(data.get("explanation"), required=True),
        changes=_text_list(data.get("changes")),
    )


# ---------------------------------------------------------------- AI observations
@dataclass(frozen=True)
class ObservationPayload:
    category: ObservationCategory
    title: str
    description: str
    suggestion: str
    line: int | None
    confidence: Confidence


def _category(value: object) -> ObservationCategory:
    key = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    try:
        return ObservationCategory(key)
    except ValueError:
        return ObservationCategory.BEST_PRACTICE


def _confidence(value: object) -> Confidence:
    try:
        return Confidence(str(value or "").strip().lower())
    except ValueError:
        return Confidence.LOW


def _line(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def parse_review(text: str) -> list[ObservationPayload]:
    """Valid observations only. A malformed item is dropped, not fatal."""
    items = extract_json(text).get("observations")
    if not isinstance(items, list):
        raise AIResponseError("The AI response did not contain an observations list.")
    result: list[ObservationPayload] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            result.append(
                ObservationPayload(
                    category=_category(item.get("category")),
                    title=_text(item.get("title"), required=True, limit=160),
                    description=_text(item.get("description"), required=True),
                    suggestion=_text(item.get("suggestion")),
                    line=_line(item.get("line")),
                    confidence=_confidence(item.get("confidence")),
                )
            )
        except AIResponseError:
            continue
    return result[:MAX_OBSERVATIONS]


def valid_line(line: int | None, total_lines: int) -> int | None:
    """Keep a line number only if it exists in the file."""
    return line if line is not None and 1 <= line <= total_lines else None
