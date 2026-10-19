"""Find Python files and the FastAPI application in whatever repo this server lives in."""

from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path

# Token recorded the last time modules for a repo were known to match disk.
_import_tokens: dict[str, str] = {}

SKIP_DIRS = {
    ".git",
    ".mypy_cache",
    ".nox",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    ".worktrees",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "reports",
    "venv",
}


def iter_python_files(root: Path):
    for path in root.rglob("*.py"):
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        yield path


def module_name(root: Path, path: Path) -> str:
    relative = path.relative_to(root).as_posix()
    if relative.endswith("/__init__.py"):
        relative = relative[: -len("/__init__.py")]
    elif relative.endswith(".py"):
        relative = relative[:-3]
    return relative.replace("/", ".")


def is_test_file(relative: str) -> bool:
    name = Path(relative).name
    return name.startswith("test_") or name.endswith("_test.py")


def load_fastapi_app(root: Path):
    """Import the FastAPI instance declared in this repository.

    Prefers `app` in `main.py`. Returns None when the repo has no FastAPI() assignment.
    Modules under the repository are imported again after those files change, so a
    later check does not keep validating the process's first copy of the code.
    """
    _refresh_repo_modules(root)
    candidates: list[tuple[Path, str]] = []
    for path in iter_python_files(root):
        try:
            source = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError):
            continue
        if "FastAPI" not in source:
            continue
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in tree.body:
            if not isinstance(node, ast.Assign) or not _is_call_named(node.value, "FastAPI"):
                continue
            for target in node.targets:
                if isinstance(target, ast.Name):
                    candidates.append((path, target.id))

    if not candidates:
        return None

    path, attribute = min(candidates, key=_candidate_rank)
    name = module_name(root, path)
    root_text = str(root.resolve())
    inserted = root_text not in sys.path
    if inserted:
        sys.path.insert(0, root_text)
    try:
        try:
            module = importlib.import_module(name)
        except Exception:
            _import_tokens.pop(root_text, None)
            _evict_repo_modules(root)
            raise
    finally:
        if inserted and sys.path and sys.path[0] == root_text:
            sys.path.pop(0)
    application = getattr(module, attribute, None)
    if application is None or not hasattr(application, "openapi"):
        return None
    return application


def _refresh_repo_modules(root: Path) -> None:
    from mcp_server.fingerprint import source_token

    key = str(root.resolve())
    token = source_token(root)
    previous = _import_tokens.get(key)
    if previous == token:
        return
    if previous is not None:
        _evict_repo_modules(root)
    _import_tokens[key] = token


def _evict_repo_modules(root: Path) -> None:
    """Drop cached imports of the target project, not this server or its environment."""
    resolved = root.resolve()
    doomed: list[str] = []
    for name, module in list(sys.modules.items()):
        if name == "mcp_server" or name.startswith("mcp_server."):
            continue
        module_path = _module_file(module)
        if module_path is None or not _is_project_file(module_path, resolved):
            continue
        doomed.append(name)
    for name in sorted(doomed, key=len, reverse=True):
        sys.modules.pop(name, None)


def _module_file(module: object) -> Path | None:
    file = getattr(module, "__file__", None)
    if isinstance(file, str) and file:
        return Path(file)
    paths = getattr(module, "__path__", None)
    if not paths:
        return None
    try:
        first = next(iter(paths))
    except StopIteration:
        return None
    return Path(first) if first else None


def _is_project_file(path: Path, root: Path) -> bool:
    try:
        relative = path.resolve().relative_to(root)
    except (OSError, ValueError):
        return False
    return not relative.parts or relative.parts[0] not in SKIP_DIRS


def _candidate_rank(candidate: tuple[Path, str]) -> tuple[int, int, str]:
    path, name = candidate
    score = len(path.parts)
    if path.name == "main.py":
        score -= 20
    elif path.name == "app.py":
        score -= 10
    if name == "app":
        score -= 5
    return (score, len(str(path)), name)


def _is_call_named(node: ast.AST, name: str) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == name
    if isinstance(func, ast.Attribute):
        return func.attr == name
    return False
