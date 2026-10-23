"""Fingerprint the files that can change a probe or a pytest result."""

from __future__ import annotations

import hashlib
from pathlib import Path

from mcp_server.dependencies import contracts_dir, repo_root
from mcp_server.discover import iter_python_files


def source_token(root: Path | None = None) -> str:
    """Change whenever application code or contract files change.

    Repair sessions use this to recognize the tree that was escalated.
    Probes and tests do not reuse an earlier result from it.
    """
    project = (root or repo_root()).resolve()
    rows: list[str] = []
    if project.is_dir():
        for path in iter_python_files(project):
            rows.append(_row("py", project, path))
        directory = contracts_dir(project) if root is not None else contracts_dir()
        if directory.is_dir():
            for path in sorted(directory.glob("*.json")):
                rows.append(_row("contract", project, path))
    rows.sort()
    digest = hashlib.sha256("\n".join(rows).encode()).hexdigest()
    return digest


def _row(kind: str, project: Path, path: Path) -> str:
    try:
        stat = path.stat()
        relative = path.resolve().relative_to(project).as_posix()
    except (OSError, ValueError):
        relative = path.name
        stat = None
    if stat is None:
        return f"{kind}:{relative}:missing"
    return f"{kind}:{relative}:{stat.st_mtime_ns}:{stat.st_size}"
