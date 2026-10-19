"""Bounded repair attempts and Git rollback of an unaccepted patch."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from mcp_server.dependencies import reports_dir, repo_root
from mcp_server.fingerprint import source_token

MAX_ATTEMPTS = 3
_SESSION_NAME = "repair-session.json"


def escalated_lock() -> dict | None:
    """Return the open escalation when the tree is still the restored tree."""
    session = _load()
    if not session or session.get("status") != "escalated":
        return None
    if session.get("locked_token") != source_token():
        return None
    return session


def note_verification(accepted: bool) -> dict:
    """Count one verification of the current tree.

    A previous accepted or escalated session starts over once the sources
    change. The third failed attempt restores unaccepted Git changes.
    """
    session = _load()
    token = source_token()
    if session and session.get("status") == "escalated" and session.get("locked_token") == token:
        return session
    if session is None or session.get("status") in {"escalated", "pending_approval"}:
        session = {"attempts": 0, "status": "in_progress"}

    session["attempts"] = int(session.get("attempts") or 0) + 1
    session["token"] = token
    if accepted:
        session["status"] = "pending_approval"
        session.pop("rollback", None)
        session.pop("escalation_report", None)
        _save(session)
        return session

    if session["attempts"] >= MAX_ATTEMPTS:
        restored = restore_unaccepted_changes(repo_root())
        session["status"] = "escalated"
        session["rollback"] = restored
        session["locked_token"] = source_token()
        session["escalation_report"] = write_escalation_report(session)
        _save(session)
        return session

    session["status"] = "in_progress"
    _save(session)
    return session


def remember(result: dict) -> None:
    session = _load()
    if session is None:
        return
    session["last_result"] = result
    _save(session)


def restore_unaccepted_changes(root: Path) -> dict:
    """Discard uncommitted work at `root` and leave the last commit in place.

    Reports, the virtualenv, and Cursor project settings are left on disk.
    """
    import git

    try:
        repo = git.Repo(root)
    except git.InvalidGitRepositoryError:
        return {
            "ok": False,
            "restored_to": None,
            "error": f"{root} is not a Git repository; unaccepted changes were left in place.",
        }
    try:
        head = repo.head.commit.hexsha
    except ValueError:
        return {
            "ok": False,
            "restored_to": None,
            "error": "The repository has no commits, so there is nothing to restore.",
        }
    try:
        repo.git.reset("--hard", "HEAD")
        repo.git.clean("-fd", "-e", "reports", "-e", ".venv", "-e", ".cursor")
    except git.GitCommandError as exc:
        return {"ok": False, "restored_to": head, "error": str(exc)}
    return {"ok": True, "restored_to": head, "error": None}


def write_escalation_report(session: dict) -> dict:
    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    directory = reports_dir()
    stem = _unique_stem(directory, generated_at)
    payload = {
        "status": "escalated",
        "accepted": False,
        "generated_at": generated_at,
        "attempts": session.get("attempts"),
        "max_attempts": MAX_ATTEMPTS,
        "rollback": session.get("rollback"),
        "summary": (
            f"Verification failed {session.get('attempts')} times. "
            "Unaccepted changes were restored with Git."
        ),
    }
    json_path = directory / f"{stem}.json"
    markdown_path = directory / f"{stem}.md"
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    rollback = payload["rollback"] or {}
    markdown_path.write_text(
        "\n".join(
            [
                "# Escalation report",
                "",
                "- Status: escalated",
                f"- Attempts: {payload['attempts']} of {MAX_ATTEMPTS}",
                f"- Generated: {generated_at}",
                f"- Rollback ok: {rollback.get('ok')}",
                f"- Restored to: {rollback.get('restored_to')}",
                f"- Rollback error: {rollback.get('error')}",
                "",
                payload["summary"],
                "",
                "Stop editing. A person needs to inspect this failure.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return {"json_report": str(json_path), "markdown_report": str(markdown_path)}


def _session_path() -> Path:
    return reports_dir() / _SESSION_NAME


def _load() -> dict | None:
    path = _session_path()
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _save(session: dict) -> None:
    _session_path().write_text(json.dumps(session, indent=2) + "\n", encoding="utf-8")


def _unique_stem(directory: Path, generated_at: str) -> str:
    stamp = generated_at.replace(":", "").replace("-", "").replace("+", "p")
    stem = f"escalation-report-{stamp}"
    candidate = stem
    counter = 2
    while (directory / f"{candidate}.json").exists() or (directory / f"{candidate}.md").exists():
        candidate = f"{stem}-{counter}"
        counter += 1
    return candidate
