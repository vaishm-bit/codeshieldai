"""Choosing which part of a file is sent to the AI, and preparing it safely."""

import re
from dataclasses import dataclass
from pathlib import PurePosixPath


@dataclass(frozen=True)
class CodeContext:
    start_line: int
    end_line: int
    total_lines: int
    is_full_file: bool
    code: str  # the selected lines, without line numbers
    numbered: str  # the same lines prefixed with line numbers, for prompts


def split_lines(content: str) -> list[str]:
    """Split like an editor does: \\n, \\r\\n and \\r end a line; a trailing newline adds none."""
    lines = content.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def slice_lines(content: str, start: int, end: int) -> str:
    """Lines start..end (1-based, inclusive) of content."""
    return "\n".join(split_lines(content)[max(start, 1) - 1 : end])


def _size(lines: list[str], start: int, end: int) -> int:
    return sum(len(line) + 1 for line in lines[start - 1 : end])


def build_context(
    content: str,
    line_start: int = 1,
    line_end: int | None = None,
    *,
    max_chars: int = 24000,
    radius: int = 40,
) -> CodeContext:
    """The whole file if it fits, otherwise a window around the reported lines."""
    lines = split_lines(content)
    total = len(lines)
    if total == 0:
        return CodeContext(1, 1, 0, True, "", "")

    if len(content) <= max_chars:
        start, end = 1, total
    else:
        first = min(max(line_start, 1), total)
        last = min(max(line_end or first, first), total)
        while True:
            start, end = max(1, first - radius), min(total, last + radius)
            if _size(lines, start, end) <= max_chars or radius == 0:
                break
            radius //= 2

    selected = lines[start - 1 : end]
    code = "\n".join(selected)
    if len(code) > max_chars:  # a single enormous line: hard cut
        code = code[:max_chars]
        selected = code.split("\n")
        end = start + len(selected) - 1

    width = len(str(end))
    numbered = "\n".join(f"{n:>{width}} | {text}" for n, text in enumerate(selected, start=start))
    return CodeContext(start, end, total, start == 1 and end == total, code, numbered)


_TAG = re.compile(r"<(/?)\s*code_under_review", re.IGNORECASE)


def escape_for_prompt(code: str) -> str:
    """Stop code from closing or reopening our <code_under_review> wrapper."""
    return _TAG.sub(r"<\1 code_under_review", code)


def safe_filename(name: str) -> str:
    """Base name only: directory names can reveal paths on the user's machine."""
    return PurePosixPath(name.replace("\\", "/")).name or "file"
