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


def contracts_dir(root: Path | None = None) -> Path:
    """Directory of optional JSON schemas whose titles match response models.

    An explicit root always wins, so a probe of a temporary project does not
    pick up another repository's contracts. GUARDIAN_CONTRACTS_DIR overrides
    the default `<repo>/contracts` location.
    """
    if root is not None:
        return root / "contracts"
    override = os.environ.get("GUARDIAN_CONTRACTS_DIR")
    if override:
        return Path(override).resolve()
    return repo_root() / "contracts"


def test_suite_targets(root: Path | None = None) -> list[str]:
    """Pytest paths for this repository.

    GUARDIAN_TEST_PATHS, when set, is an `os.pathsep`-separated list relative
    to the repository. Otherwise unit and integration directories are used
    when they exist, then `tests/` or `test/`, then top-level test modules.
    An empty list means the repository has no suite.
    """
    if root is None:
        override = os.environ.get("GUARDIAN_TEST_PATHS")
        if override is not None:
            return [part.strip().replace("\\", "/") for part in override.split(os.pathsep) if part.strip()]
        project = repo_root()
    else:
        project = root

    found = [
        relative
        for relative in ("tests/unit", "tests/integration")
        if (project / relative).is_dir()
    ]
    if found:
        return found
    for relative in ("tests", "test"):
        if (project / relative).is_dir():
            return [relative]
    has_modules = any(project.glob("test_*.py")) or any(project.glob("*_test.py"))
    if has_modules:
        return ["."]
    return []


def truncate(text: str, limit: int = DIFF_CHAR_LIMIT) -> str:
    if len(text) <= limit:
        return text
    omitted = len(text) - limit
    return f"{text[:limit]}\n... truncated {omitted} characters"
