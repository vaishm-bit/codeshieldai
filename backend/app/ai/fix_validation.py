"""Checks on AI-generated fixes. Code is parsed, never executed or imported."""

import ast
from dataclasses import dataclass

from app.ai.redaction import PLACEHOLDER_PREFIX
from app.ai.types import FixStatus

PYTHON_NAMES = {"python", "py", "python3"}


@dataclass(frozen=True)
class FixValidation:
    status: FixStatus
    message: str


def _normalise(code: str) -> str:
    return "\n".join(line.rstrip() for line in code.replace("\r\n", "\n").strip().split("\n"))


def validate_fix(
    *, original: str, fixed: str, language: str, is_full_file: bool
) -> FixValidation:
    """Run the cheap, safe checks that exist. Never reports a fix as 'secure'."""
    if not fixed.strip() or _normalise(fixed) == _normalise(original):
        return FixValidation(FixStatus.NO_CHANGE, "The AI did not change the code.")

    if PLACEHOLDER_PREFIX in fixed:
        return FixValidation(
            FixStatus.UNRESOLVED_PLACEHOLDER,
            "The fix still contains a redaction placeholder. Review it by hand before using it.",
        )

    if is_full_file and len(original) >= 200 and len(fixed) < len(original) * 0.5:
        return FixValidation(
            FixStatus.INCOMPLETE,
            "The fixed code is much shorter than the original and may be missing code.",
        )

    if is_full_file and language.lower() in PYTHON_NAMES:
        try:
            ast.parse(fixed)
        except (SyntaxError, ValueError, RecursionError) as exc:
            line = getattr(exc, "lineno", None)
            where = f" (line {line})" if line else ""
            reason = getattr(exc, "msg", None) or str(exc)
            return FixValidation(
                FixStatus.SYNTAX_INVALID, f"The fixed code is not valid Python{where}: {reason}."
            )
        return FixValidation(
            FixStatus.SYNTAX_VALID,
            "Parses as valid Python. This is a syntax check only: it does not prove the "
            "vulnerability is gone. Re-scan the fixed code to confirm.",
        )

    return FixValidation(
        FixStatus.NOT_CHECKED,
        "No automatic check is available for this code. Review the change manually.",
    )
