"""Save a repair report. The tool records evidence; it does not apply a patch."""

from __future__ import annotations

import json
from datetime import datetime

from fastmcp import FastMCP

from mcp_server.dependencies import reports_dir
from mcp_server.tools.git_tools import get_recent_changes
from mcp_server.tools.verify_tools import verify_repair


def submit_fix_report(
    diagnosis: str,
    proposed_patch_summary: str,
    verification_evidence: str = "",
    nodeids: list[str] | None = None,
    base_url: str | None = None,
) -> dict:
    """Save the diagnosis and patch summary after this server re-runs verification.

    `verification_evidence` is stored as the agent's notes. It is not the
    pass/fail verdict. This tool calls `verify_repair`, which probes the API
    and runs the tests again. Status is `pending_approval` only
    when those checks pass. Status is `escalated` when three attempts have
    failed and unaccepted changes were restored. Otherwise the report is
    `verification_failed`.
    """
    verification = verify_repair(nodeids, base_url)
    if verification.get("escalated"):
        status = "escalated"
    elif verification["accepted"]:
        status = "pending_approval"
    else:
        status = "verification_failed"
    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    changes = get_recent_changes(limit=1)
    latest = (changes.get("recent_commits") or [None])[0]
    notes = verification_evidence.strip()

    payload = {
        "status": status,
        "accepted": verification["accepted"],
        "generated_at": generated_at,
        "diagnosis": diagnosis.strip(),
        "proposed_patch_summary": proposed_patch_summary.strip(),
        "agent_notes": notes,
        "verification": verification,
        "git": {
            "branch": changes.get("branch"),
            "head": changes.get("head"),
            "working_tree_dirty": changes.get("working_tree_dirty"),
            "latest_commit": latest,
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
        "accepted": verification["accepted"],
        "status": status,
        "summary": verification["summary"],
        "next_action": verification["next_action"],
        "json_report": str(json_path),
        "markdown_report": str(markdown_path),
        "verification": verification,
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
    verification = payload["verification"]
    health = verification["api_health"]
    full = verification["full_tests"] or {}
    targeted = verification["targeted_tests"] or {}
    notes = payload["agent_notes"] or "(none provided)"
    files = ", ".join(latest.get("files") or []) or "(none)"
    return f"""# Fix report

- Status: {payload["status"]}
- Accepted by MCP verification: {payload["accepted"]}
- Generated: {payload["generated_at"]}
- Branch: {git_info.get("branch")}
- HEAD: {git_info.get("head")}
- Working tree dirty: {git_info.get("working_tree_dirty")}

## Diagnosis

{payload["diagnosis"] or "(none provided)"}

## Proposed patch

{payload["proposed_patch_summary"] or "(none provided)"}

## Server verification

{verification["summary"]}

- Contract ok: {verification["contract_ok"]}
- Targeted ok: {verification["targeted_ok"]} ({targeted.get("passed", 0)} passed, {targeted.get("failed", 0)} failed)
- Full suite ok: {verification["full_ok"]} ({full.get("passed", 0)} passed, {full.get("failed", 0)} failed)
- Next action: {verification["next_action"]}

## Agent notes

{notes}

These notes are not the verdict. Accept a repair only when the server verification above says it was accepted, then wait for human approval.

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
