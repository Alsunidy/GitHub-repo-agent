"""Tests for backend/tools/github_tools.py — no network: requests.get/post
are mocked at the module boundary."""
from unittest.mock import Mock, patch

import pytest

from backend.tools.github_tools import (
    MissingToken,
    RepoNotFound,
    fetch_repo_data,
    open_issue,
    parse_repo_url,
)


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://github.com/owner/repo", ("owner", "repo")),
        ("http://github.com/owner/repo", ("owner", "repo")),
        ("github.com/owner/repo", ("owner", "repo")),
        ("https://www.github.com/owner/repo", ("owner", "repo")),
        ("https://github.com/owner/repo.git", ("owner", "repo")),
        ("https://github.com/owner/repo/", ("owner", "repo")),
        ("https://github.com/owner/repo/tree/main", ("owner", "repo")),
        ("https://github.com/owner/repo/issues/12", ("owner", "repo")),
    ],
)
def test_parse_repo_url_accepts_valid_formats(url, expected):
    assert parse_repo_url(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "",
        None,
        "not a url at all",
        "https://gitlab.com/owner/repo",
        "https://github.com/owner",
        "https://github.com/",
    ],
)
def test_parse_repo_url_rejects_invalid_formats(url):
    assert parse_repo_url(url) is None


def test_fetch_repo_data_raises_repo_not_found_on_404():
    not_found_response = Mock(status_code=404)
    with patch("backend.tools.github_tools.requests.get", return_value=not_found_response):
        with pytest.raises(RepoNotFound):
            fetch_repo_data("owner", "does-not-exist")


def test_open_issue_raises_missing_token_without_env_var(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    with pytest.raises(MissingToken):
        open_issue("owner", "repo", "title", "body")


def test_open_issue_never_reaches_network_without_token(monkeypatch):
    """MissingToken must be raised before any HTTP call is attempted."""
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    with patch("backend.tools.github_tools.requests.post") as mock_post:
        with pytest.raises(MissingToken):
            open_issue("owner", "repo", "title", "body")
    mock_post.assert_not_called()
