"""Map changed files to affected routes and tests by reading the project."""

from __future__ import annotations

from pathlib import Path

from fastmcp import FastMCP

from mcp_server.dependencies import repo_root
from mcp_server.dependency_map import analyze
from mcp_server.tools.git_tools import changed_files_for_impact


def analyze_impact(changed_files: list[str] | None = None) -> dict:
    """Identify endpoints and tests affected by the given files.

    When `changed_files` is omitted, the working tree diff is used, and if
    that is clean the files from the latest commit are used. Relationships
    come from imports and route handlers in this repository. Impact selection
    does not replace the full suite.
    """
    if changed_files:
        source = "explicit_paths"
        paths = [_normalize(path) for path in changed_files if path and path.strip()]
    else:
        detected = changed_files_for_impact()
        source = detected["source"]
        paths = [_normalize(path) for path in detected["files"]]

    report = analyze(repo_root(), paths)
    report["source"] = source
    report["repo_root"] = str(repo_root())
    return report


def register(mcp: FastMCP) -> None:
    mcp.tool(analyze_impact)


def _normalize(path: str) -> str:
    raw = path.replace("\\", "/").strip()
    if raw.startswith("./"):
        raw = raw[2:]
    candidate = repo_root() / raw if not _is_absolute(raw) else Path(raw)
    try:
        relative = candidate.resolve().relative_to(repo_root())
    except (ValueError, OSError):
        return raw
    return relative.as_posix()


def _is_absolute(path: str) -> bool:
    return path.startswith("/") or (len(path) > 2 and path[1] == ":")
