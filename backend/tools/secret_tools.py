"""Secret-scanning tool for the Repo Health Agent.

scan_secrets() looks for well-known secret formats plus generic
"password = ..." / "api_key = ..." style assignments, and never returns
the raw secret value — only a partially masked snippet.
"""
import re

# Specific formats are checked before the generic assignment pattern so a
# known token isn't also reported a second time as a generic match.
_PATTERNS = [
    ("github_token", re.compile(r"(?P<secret>ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{20,255})")),
    ("openai_key", re.compile(r"(?P<secret>sk-[A-Za-z0-9]{20,})")),
    ("aws_access_key", re.compile(r"(?P<secret>AKIA[0-9A-Z]{16})")),
    ("google_api_key", re.compile(r"(?P<secret>AIza[0-9A-Za-z_\-]{35})")),
    (
        "generic_secret",
        re.compile(
            r'(?i)(?P<key>password|api[_-]?key|secret|token)\s*[:=]\s*'
            r'["\'](?P<secret>[^"\']{6,})["\']'
        ),
    ),
]


def _mask(secret: str) -> str:
    """Keep only the first 4 and last 4 characters of the secret."""
    if len(secret) <= 8:
        return "*" * len(secret)
    return f"{secret[:4]}{'*' * (len(secret) - 8)}{secret[-4:]}"


def _scan_line(line: str) -> list[tuple[str, str]]:
    """Return [(kind, secret_value), ...] for one line, skipping overlapping
    matches so a token already caught by a specific pattern isn't reported
    again by the generic one."""
    found = []
    covered_spans: list[tuple[int, int]] = []

    for pattern_name, pattern in _PATTERNS:
        for match in pattern.finditer(line):
            start, end = match.span("secret")
            if any(start < e and s < end for s, e in covered_spans):
                continue
            covered_spans.append((start, end))

            if pattern_name == "generic_secret":
                key = match.group("key").lower().replace("-", "_")
                kind = f"hardcoded_{key}"
            else:
                kind = pattern_name

            found.append((kind, match.group("secret")))

    return found


def scan_secrets(code_files: dict[str, str]) -> list[dict]:
    """Scan file contents for known secret patterns.

    Returns a list of {"file", "line", "kind", "snippet"}; snippet is the
    source line with the secret value masked (first 4 / last 4 chars only),
    never the full secret.
    """
    findings = []
    for file_path, content in (code_files or {}).items():
        for line_no, line in enumerate(content.splitlines(), start=1):
            for kind, secret in _scan_line(line):
                snippet = line.replace(secret, _mask(secret), 1).strip()
                findings.append(
                    {
                        "file": file_path,
                        "line": line_no,
                        "kind": kind,
                        "snippet": snippet,
                    }
                )
    return findings
