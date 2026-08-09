"""Tests for backend/tools/secret_tools.py — pure local regex scanning, no
network involved at all."""
from backend.tools.secret_tools import scan_secrets

_KNOWN_SECRETS = {
    "github_token": "ghp_0123456789abcdefghijklmnopqrstuvwxyz",
    "openai_key": "sk-ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890",
    "aws_access_key": "AKIAABCDEFGHIJKLMNOP",
    "google_api_key": "AIzaA1B2C3D4E5A1B2C3D4E5A1B2C3D4E5A1B2C",
}


def test_scan_secrets_detects_all_four_known_formats():
    code_files = {
        "config.py": "\n".join(
            f'{kind.upper()} = "{value}"' for kind, value in _KNOWN_SECRETS.items()
        )
    }

    findings = scan_secrets(code_files)
    found_by_kind = {f["kind"]: f for f in findings}

    assert set(found_by_kind) == set(_KNOWN_SECRETS)
    assert len(findings) == 4
    for finding in findings:
        assert finding["file"] == "config.py"


def test_scan_secrets_masks_the_secret_value():
    for kind, value in _KNOWN_SECRETS.items():
        findings = scan_secrets({"f.py": f'X = "{value}"'})
        assert len(findings) == 1
        snippet = findings[0]["snippet"]
        assert value not in snippet  # full secret never shown
        assert value[:4] in snippet
        assert value[-4:] in snippet
        assert "*" in snippet


def test_scan_secrets_generic_pattern_for_password_and_api_key():
    code_files = {
        "settings.py": (
            'password = "SuperSecretPassword123"\n'
            'api_key = "abcdef1234567890"\n'
        )
    }
    findings = scan_secrets(code_files)
    kinds = {f["kind"] for f in findings}
    assert kinds == {"hardcoded_password", "hardcoded_api_key"}


def test_scan_secrets_no_false_positive_on_plain_mention():
    code_files = {
        "app.py": 'print("set GITHUB_TOKEN as an environment variable, never hardcode it")\n'
    }
    assert scan_secrets(code_files) == []


def test_scan_secrets_no_false_positive_on_clean_code():
    code_files = {"app.py": "def add(a, b):\n    return a + b\n"}
    assert scan_secrets(code_files) == []


def test_scan_secrets_line_numbers_are_one_indexed():
    code_files = {"app.py": 'x = 1\ny = 2\napi_key = "abcdef1234567890"\n'}
    findings = scan_secrets(code_files)
    assert len(findings) == 1
    assert findings[0]["line"] == 3


def test_scan_secrets_handles_empty_input():
    assert scan_secrets({}) == []
