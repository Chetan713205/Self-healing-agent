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
This server is the verification layer for a FastAPI repository.
Cursor Agent decides what to inspect and how to edit code. These tools
return evidence from the running API, Git, the import graph, and pytest.
The agent does not decide whether a patch passed. verify_repair and
submit_fix_report run the checks and set accepted from those results.

GET routes are discovered from the FastAPI app. A file in contracts/ is
applied when its title matches a response schema; otherwise the OpenAPI
schema is the contract. Restore behavior so responses match that schema.

Tools, in the order you should use them:
1. check_api_health — call discovered GET routes and compare them with their schemas.
2. get_contract_violations — missing fields, unexpected fields, wrong types, schema mismatches.
3. get_recent_changes — recent commits and the latest diff.
4. analyze_impact — affected endpoints and tests from imports and route handlers.
5. run_targeted_tests — run the node ids analyze_impact recommended.
6. run_full_tests — run the unit and integration suites.
7. get_failure_evidence — failing tests, contract violations, and the latest change.
8. verify_repair — contract probes, targeted tests, then the full suite. This sets accepted.
9. submit_fix_report — save the diagnosis and patch summary. Status comes from verify_repair.

Impact analysis prioritizes tests. It does not prove unrelated code is safe.
pending_approval means the checks passed and a human must approve.
verification_failed means use the returned failures for another attempt.
Do not treat your own reasoning as a passing test.
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
