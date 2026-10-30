"""MCP server entry point.

Cursor Agent reasons and edits code. This process only exposes tools and
returns evidence. Logging stays on stderr so stdio transport keeps stdout
for the MCP protocol.
"""

from __future__ import annotations

import logging
import sys

from fastmcp import FastMCP

from mcp_server.tools import git_tools, health_tools, impact_tools, report_tools, test_tools, verify_tools

INSTRUCTIONS = """
This server is the verification layer for the FastAPI repository it is pointed at.
Cursor Agent decides what to inspect and how to edit code. These tools return
evidence from the running API, Git, the import graph, and pytest. The agent
does not decide whether a patch passed. verify_repair and submit_fix_report
run the checks and set accepted from those results.

Paths are configured with GUARDIAN_REPO_ROOT, GUARDIAN_API_BASE_URL,
GUARDIAN_CONTRACTS_DIR, GUARDIAN_TEST_PATHS, and GUARDIAN_REPORTS_DIR. A
repository does not need tests/unit or tests/integration. A missing suite is
reported and does not by itself fail verification.

Diagnosis covers API contract failures and code-level regressions. GET routes
are discovered from the FastAPI app, including list routes. Nested $ref values
are resolved against the full OpenAPI document. One route that cannot be
validated is reported on its own. A file in the contracts directory is applied
when its title matches a response schema or a list item schema; otherwise the
OpenAPI schema is the contract. Restore responses to match that schema when it
is wrong. A green contract check is not enough, and a loud contract failure
must not stop review of other defects: read every patch in
get_recent_changes.recent_commit_diffs (commit order must not matter), then run
impact-selected tests for formula or logic mistakes, deleted or missing
functions, broken code, and other regressions that schema validation will not
catch. Every check imports the application from the current source. A running
process whose component schemas differ from that source is stale. Its responses
are not a passing contract check. That result is not counted as a repair
attempt.

When the user asks for an API checkup or repair, restart the API from the
current source before any probe. Stop the process listening on
GUARDIAN_API_BASE_URL (default http://127.0.0.1:8000), start uvicorn
app.main:app on that host and port from GUARDIAN_REPO_ROOT, and wait until it
is accepting connections. The first probe then sees the code on disk. Restart
again after the edit, before verify_repair.

Repair workflow:
1. Restart the API, then call check_api_health and get_contract_violations.
2. Call get_recent_changes (use enough limit to cover recent injected or
   related commits), then analyze_impact. Before editing, read every entry in
   recent_commit_diffs plus working-tree/staged diffs—not only latest_diff or
   HEAD. Inventory schema/contract violations and logic or formula regressions
   from that full window. Do not treat the tip commit as the only change.
3. Diagnose from the full inventory. Contract shape and business logic are
   both in scope on every checkup: restore responses to match the contract
   (including list items) when shape is wrong, and restore formulas, totals,
   tax, and other logic when diffs or tests show regressions. When both kinds
   of defect appear across recent commits, fix them together in one smallest
   coherent patch. If logic risk remains after reading diffs, call
   run_targeted_tests with the recommended_nodeids from analyze_impact (or
   get_failure_evidence) to confirm before or while editing—do not wait for a
   later verify failure to discover a second bug that was already in history.
4. Restart the API again, then call verify_repair with the recommended_nodeids
   from analyze_impact. That tool re-probes the API, runs the targeted tests,
   and runs the full suite only after those pass.
5. Call submit_fix_report with the diagnosis and the patch summary. Leave the
   verdict to that tool.
6. When the checkup is finished, stop the API you started. After
   submit_fix_report returns pending_approval or escalated, and whenever you
   stop because escalated is true, stop the process listening on the guardian
   base URL (default http://127.0.0.1:8000) and let that background terminal
   exit before you end the turn. submit_fix_report still probes the API, so
   stop only after that call returns. A finished checkup must not leave
   uvicorn running.

verify_repair probes the API and runs the tests on every call but does not
count toward the attempt budget. submit_fix_report re-probes and is the only
tool that records an attempt. The full suite starts only after the contract and
targeted tests pass. A health probe that could not connect, or a stale API
process, is not counted. There is a maximum of 3 repair attempts. Each new
failed submit_fix_report counts as one. After the third failure this server
restores the unaccepted Git changes and writes an escalation report. Stop when
escalated is true or status is escalated. Do not keep editing.

accepted true and status pending_approval mean the checks passed and a person
still has to approve. verification_failed means use the returned failures for
another attempt, up to the limit above. Do not treat your own reasoning as a
passing test.
""".strip()


def create_server() -> FastMCP:
    mcp = FastMCP(
        name="self-healing-guardian",
        instructions=INSTRUCTIONS,
    )
    health_tools.register(mcp)
    git_tools.register(mcp)
    impact_tools.register(mcp)
    test_tools.register(mcp)
    verify_tools.register(mcp)
    report_tools.register(mcp)
    return mcp


def main() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    create_server().run(transport="stdio", show_banner=False)


if __name__ == "__main__":
    main()
