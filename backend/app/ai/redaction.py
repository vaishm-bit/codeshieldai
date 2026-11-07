"""Best-effort removal of secrets before code is sent to an external AI service.

- Line counts are preserved, so line numbers still match the user's file.
- Every secret becomes a numbered placeholder such as <REDACTED_1>.
- The mapping stays on this server, so a fix returned by the AI can be restored
  locally (restore) and the user's real values are never lost.

This is a safety net, not a guarantee: only literal strings and well-known token
formats are detected. Tell users that code is sent to the configured AI provider.
"""

import re
from dataclasses import dataclass, field

PLACEHOLDER_PREFIX = "<REDACTED_"

_PRIVATE_KEY = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----", re.DOTALL
)
_TOKEN_FORMATS = re.compile(
    "|".join(
        [
            r"\bAKIA[0-9A-Z]{16}\b",  # AWS access key id
            r"\bgh[pousr]_[A-Za-z0-9]{36,}",  # GitHub tokens
            r"\bxox[baprs]-[A-Za-z0-9-]{10,}",  # Slack tokens
            r"\b(?:sk|rk)_(?:live|test)_[0-9A-Za-z]{16,}",  # Stripe keys
            r"\bsk-[A-Za-z0-9_\-]{20,}",  # OpenAI / Anthropic style keys
            r"\bAIza[0-9A-Za-z_\-]{35}",  # Google API keys
            r"\beyJ[A-Za-z0-9_\-]{8,}\.eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}",  # JWTs
        ]
    )
)
_URL_CREDENTIALS = re.compile(
    r"""(?P<head>[A-Za-z][A-Za-z0-9+.\-]*://[^\s:/@"']+:)(?P<secret>[^\s@/"']+)(?P<tail>@)"""
)
_ASSIGNMENT = re.compile(
    r"""(?P<head>(?:password|passwd|pwd|secret|api[_-]?key|token|private[_-]?key|credential)"""
    r"""[\w.\-]*["']?\s*(?:==|=|:)\s*)(?P<quote>["'])(?P<secret>[^"'\r\n]{4,})(?P=quote)""",
    re.IGNORECASE,
)
_BEARER = re.compile(r"(?P<head>\bbearer\s+)(?P<secret>[A-Za-z0-9_\-.=]{16,})", re.IGNORECASE)


@dataclass
class RedactionResult:
    text: str
    mapping: dict[str, str] = field(default_factory=dict)

    @property
    def count(self) -> int:
        return len(self.mapping)

    def restore(self, text: str) -> str:
        """Put the original secrets back into text that came back from the AI."""
        for placeholder, original in reversed(list(self.mapping.items())):
            pattern = re.escape(placeholder)
            newlines = original.count("\n")
            if newlines:  # multi-line secrets keep their line count in redacted text
                pattern += r"(?:\n{%d})?" % newlines
            text = re.sub(pattern, lambda _m, value=original: value, text)
        return text


def redact_secrets(text: str) -> RedactionResult:
    mapping: dict[str, str] = {}

    def make(original: str) -> str:
        key = f"{PLACEHOLDER_PREFIX}{len(mapping) + 1}>"
        mapping[key] = original
        return key + "\n" * original.count("\n")

    def replace_secret(match: re.Match) -> str:
        secret = match.group("secret")
        if secret.startswith(PLACEHOLDER_PREFIX):
            return match.group(0)
        groups = match.groupdict()
        quote = groups.get("quote") or ""
        return groups["head"] + quote + make(secret) + quote + (groups.get("tail") or "")

    text = _PRIVATE_KEY.sub(lambda m: make(m.group(0)), text)
    text = _TOKEN_FORMATS.sub(lambda m: make(m.group(0)), text)
    text = _ASSIGNMENT.sub(replace_secret, text)
    text = _URL_CREDENTIALS.sub(replace_secret, text)
    text = _BEARER.sub(replace_secret, text)
    return RedactionResult(text=text, mapping=mapping)
