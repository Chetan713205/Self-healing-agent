"""Paths and runtime settings for the MCP server.

Values are read when a tool runs so tests can point the same functions at a
temporary repo, report directory, or API port.
"""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_API_BASE_URL = "http://127.0.0.1:8000"
DIFF_CHAR_LIMIT = 12_000
FAILURE_TEXT_LIMIT = 2_000


def repo_root() -> Path:
    override = os.environ.get("GUARDIAN_REPO_ROOT")
    if override:
        return Path(override).resolve()
    return Path(__file__).resolve().parents[1]


def api_base_url() -> str:
    return os.environ.get("GUARDIAN_API_BASE_URL", DEFAULT_API_BASE_URL).rstrip("/")


def reports_dir() -> Path:
    override = os.environ.get("GUARDIAN_REPORTS_DIR")
    path = Path(override).resolve() if override else repo_root() / "reports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def truncate(text: str, limit: int = DIFF_CHAR_LIMIT) -> str:
    if len(text) <= limit:
        return text
    omitted = len(text) - limit
    return f"{text[:limit]}\n... truncated {omitted} characters"
