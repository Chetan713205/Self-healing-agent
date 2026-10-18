"""Independent verification. The agent does not get to set the pass/fail verdict."""

from __future__ import annotations

from fastmcp import FastMCP

from mcp_server.tools.health_tools import check_api_health, get_contract_violations
from mcp_server.tools.impact_tools import analyze_impact
from mcp_server.tools.test_tools import run_full_tests, run_targeted_tests


def verify_repair(nodeids: list[str] | None = None, base_url: str | None = None) -> dict:
    """Run contract probes, targeted tests, then the full suite.

    When `nodeids` is omitted, the node ids come from `analyze_impact`.
    `accepted` is true only when the contract checks, the targeted run, and
    the full unit and integration suites all pass. A narrative from the agent
    is not a result.
    """
    if nodeids is None:
        impact = analyze_impact()
        selected = [
            str(nodeid)
            for nodeid in impact.get("recommended_nodeids") or []
            if nodeid
        ]
        selection = "analyze_impact"
    else:
        selected = [nodeid.strip() for nodeid in nodeids if nodeid and nodeid.strip()]
        selection = "caller"

    violations = get_contract_violations(base_url)
    health = check_api_health(base_url)
    targeted = run_targeted_tests(selected) if selected else None
    full = run_full_tests()

    contract_ok = bool(
        violations.get("reachable")
        and violations.get("violation_count", 0) == 0
        and health.get("healthy")
    )
    targeted_ok = targeted is None or bool(targeted.get("ok") and targeted.get("all_passed"))
    full_ok = bool(full.get("ok") and full.get("all_passed"))
    accepted = contract_ok and targeted_ok and full_ok

    return {
        "accepted": accepted,
        "contract_ok": contract_ok,
        "targeted_ok": targeted_ok,
        "full_ok": full_ok,
        "selection": selection,
        "nodeids": selected,
        "summary": _summary(contract_ok, targeted, full, accepted),
        "contract_violations": {
            "reachable": violations.get("reachable"),
            "violation_count": violations.get("violation_count", 0),
            "violations": violations.get("violations") or [],
            "error": violations.get("error"),
        },
        "api_health": {
            "base_url": health.get("base_url"),
            "reachable": health.get("reachable"),
            "healthy": health.get("healthy"),
            "error": health.get("error"),
        },
        "targeted_tests": _test_snapshot(targeted),
        "full_tests": _test_snapshot(full),
        "next_action": (
            "Checks passed. Save the report for human approval. Do not merge."
            if accepted
            else "Checks failed. Use these failures for another attempt. Do not describe the patch as fixed."
        ),
    }


def register(mcp: FastMCP) -> None:
    mcp.tool(verify_repair)


def _test_snapshot(run: dict | None) -> dict | None:
    if run is None:
        return None
    failures = [
        test
        for test in run.get("tests") or []
        if test.get("outcome") != "passed"
    ]
    return {
        "ok": run.get("ok"),
        "all_passed": run.get("all_passed"),
        "passed": run.get("passed", 0),
        "failed": run.get("failed", 0),
        "errors": run.get("errors", 0),
        "exit_code": run.get("exit_code"),
        "error": run.get("error"),
        "failures": failures,
    }


def _summary(contract_ok: bool, targeted: dict | None, full: dict, accepted: bool) -> str:
    contract = "contract passed" if contract_ok else "contract failed"
    if targeted is None:
        targeted_text = "no targeted tests selected"
    elif targeted.get("ok") and targeted.get("all_passed"):
        targeted_text = f"targeted {targeted.get('passed', 0)} passed"
    else:
        targeted_text = (
            f"targeted {targeted.get('failed', 0)} failed, "
            f"{targeted.get('errors', 0)} errors"
        )
    if full.get("ok"):
        full_text = (
            f"full suite {full.get('passed', 0)} passed, "
            f"{full.get('failed', 0)} failed, "
            f"{full.get('errors', 0)} errors"
        )
    else:
        full_text = full.get("error") or "full suite failed"
    verdict = "accepted for human approval" if accepted else "not accepted"
    return f"{verdict}; {contract}; {targeted_text}; {full_text}"
