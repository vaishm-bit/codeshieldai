from app.ai.fix_validation import validate_fix
from app.ai.types import FixStatus

ORIGINAL = "def f():\n    return eval(input())\n"
FIXED = "def f():\n    return int(input())\n"


def check(original=ORIGINAL, fixed=FIXED, language="python", is_full_file=True):
    return validate_fix(original=original, fixed=fixed, language=language, is_full_file=is_full_file)


def test_valid_python_is_only_syntax_checked():
    result = check()
    assert result.status is FixStatus.SYNTAX_VALID
    assert "does not prove" in result.message


def test_invalid_python_is_flagged_with_line():
    result = check(fixed="def f(:\n    pass\n")
    assert result.status is FixStatus.SYNTAX_INVALID
    assert "line" in result.message


def test_unchanged_or_empty_fix():
    assert check(fixed=ORIGINAL + "\n\n").status is FixStatus.NO_CHANGE
    assert check(fixed="   ").status is FixStatus.NO_CHANGE


def test_leftover_placeholder_is_unresolved():
    assert check(fixed='k = "<REDACTED_1>"\n').status is FixStatus.UNRESOLVED_PLACEHOLDER


def test_suspiciously_short_fix_is_incomplete():
    original = "x = 1\n" * 100
    assert check(original=original, fixed="x = 1\n").status is FixStatus.INCOMPLETE


def test_excerpts_and_other_languages_are_not_checked():
    assert check(is_full_file=False).status is FixStatus.NOT_CHECKED
    assert check(language="javascript").status is FixStatus.NOT_CHECKED


def test_no_status_claims_a_fix_is_verified():
    assert not any("verified" in status.value for status in FixStatus)
