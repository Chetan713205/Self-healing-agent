"""Save a repair report. The tool records evidence; it does not apply a patch."""

from __future__ import annotations

import json
from datetime import datetime

from fastmcp import FastMCP

from mcp_server.dependencies import reports_dir
from mcp_server.tools.git_tools import get_recent_changes
from mcp_server.tools.health_tools import check_api_health

_STATUSES = {"pending_approval", "verified", "escalated"}


def submit_fix_report(
    diagnosis: str,
    proposed_patch_summary: str,
    verification_evidence: str,
    status: str = "pending_approval",
) -> dict:
    """Save the diagnosis, proposed patch summary, and verification evidence.

    Writes a Markdown report and a JSON copy under reports/. Git HEAD and the
    current API health snapshot are collected by this tool. The verification
    narrative is stored as supplied; run run_full_tests and paste that result
    before marking a report verified.
    """
    normalized = status.strip() or "pending_approval"
    warning = None
    if normalized not in _STATUSES:
        warning = (
            "Unexpected status. Use pending_approval, verified, or escalated."
        )

    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    changes = get_recent_changes(limit=1)
    health = check_api_health()
    latest = (changes.get("recent_commits") or [None])[0]

    payload = {
        "status": normalized,
        "status_warning": warning,
        "generated_at": generated_at,
        "diagnosis": diagnosis.strip(),
        "proposed_patch_summary": proposed_patch_summary.strip(),
        "verification_evidence": verification_evidence.strip(),
        "git": {
            "branch": changes.get("branch"),
            "head": changes.get("head"),
            "working_tree_dirty": changes.get("working_tree_dirty"),
            "latest_commit": latest,
        },
        "api_health": {
            "base_url": health.get("base_url"),
            "reachable": health.get("reachable"),
            "healthy": health.get("healthy"),
            "error": health.get("error"),
        },
    }

    directory = reports_dir()
    stem = _unique_stem(directory, generated_at)
    json_path = directory / f"{stem}.json"
    markdown_path = directory / f"{stem}.md"
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(_render_markdown(payload), encoding="utf-8")

    return {
        "ok": True,
        "status": normalized,
        "status_warning": warning,
        "json_report": str(json_path),
        "markdown_report": str(markdown_path),
        "api_healthy": health.get("healthy"),
        "head": changes.get("head"),
    }


def register(mcp: FastMCP) -> None:
    mcp.tool(submit_fix_report)


def _unique_stem(directory, generated_at: str) -> str:
    stamp = generated_at.replace(":", "").replace("-", "").replace("+", "p")
    stem = f"fix-report-{stamp}"
    candidate = stem
    counter = 2
    while (directory / f"{candidate}.json").exists() or (directory / f"{candidate}.md").exists():
        candidate = f"{stem}-{counter}"
        counter += 1
    return candidate


def _render_markdown(payload: dict) -> str:
    git_info = payload["git"]
    latest = git_info.get("latest_commit") or {}
    health = payload["api_health"]
    warning = payload["status_warning"]
    warning_line = f"\nStatus warning: {warning}\n" if warning else ""
    files = ", ".join(latest.get("files") or []) or "(none)"
    return f"""# Fix report

- Status: {payload["status"]}
- Generated: {payload["generated_at"]}
- Branch: {git_info.get("branch")}
- HEAD: {git_info.get("head")}
- Working tree dirty: {git_info.get("working_tree_dirty")}
{warning_line}
## Diagnosis

{payload["diagnosis"] or "(none provided)"}

## Proposed patch

{payload["proposed_patch_summary"] or "(none provided)"}

## Verification evidence

{payload["verification_evidence"] or "(none provided)"}

The verification section is the text supplied by the caller. Accept a repair only when run_full_tests and the contract probes both passed.

## API health snapshot

- Base URL: {health.get("base_url")}
- Reachable: {health.get("reachable")}
- Healthy: {health.get("healthy")}
- Error: {health.get("error")}

## Latest commit

- SHA: {latest.get("sha")}
- Subject: {latest.get("subject")}
- Files: {files}
"""
