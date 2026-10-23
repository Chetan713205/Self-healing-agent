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

GET routes are discovered from the FastAPI app, including list routes. Nested
$ref values are resolved against the full OpenAPI document. One route that
cannot be validated is reported on its own. A file in the contracts directory
is applied when its title matches a response schema or a list item schema;
otherwise the OpenAPI schema is the contract. Restore behavior so responses
match that schema. Every check imports the application from the current source.
A running process whose component schemas differ from that source is stale.
Its responses are not a passing contract check. Restart the API and probe again.
That result is not counted as a repair attempt.

Repair workflow:
1. Call check_api_health and get_contract_violations.
2. Call get_recent_changes, then analyze_impact.
3. Propose the smallest edit that restores the contract. The contract is the source of truth.
4. Call verify_repair with the recommended_nodeids from analyze_impact.
5. Call submit_fix_report with the diagnosis and the patch summary. Leave the verdict to that tool.

verify_repair probes the API and runs the tests on every call. The full suite
starts only after the contract and targeted tests pass. A health probe that
could not connect is not counted as a repair attempt. There is a maximum of 3
repair attempts. Each new failed verification counts as one attempt. After the
third failure this server restores the unaccepted Git changes and writes an
escalation report. Stop when escalated is true or status is escalated. Do not
keep editing.

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
