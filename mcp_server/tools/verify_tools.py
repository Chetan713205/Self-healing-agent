"""Independent verification. The agent does not get to set the pass/fail verdict."""

from __future__ import annotations

from fastmcp import FastMCP

from mcp_server.dependencies import api_base_url, repo_root
from mcp_server.fingerprint import source_token
from mcp_server.repair import MAX_ATTEMPTS, escalated_lock, note_verification, remember
from mcp_server.results_cache import get as cache_get
from mcp_server.results_cache import put as cache_put
from mcp_server.tools.health_tools import get_contract_violations
from mcp_server.tools.impact_tools import analyze_impact
from mcp_server.tools.test_tools import run_full_tests, run_targeted_tests


def verify_repair(nodeids: list[str] | None = None, base_url: str | None = None) -> dict:
    """Run contract probes, then targeted tests, then the full suite if those pass.

    When `nodeids` is omitted, the node ids come from `analyze_impact`.
    `accepted` is true only when the contract checks pass and every selected
    test run passes. The full suite is not started after an earlier check has
    already failed. A repeat call for the same tree, base URL, and node ids
    reuses the previous result.

    Three failed verifications restore unaccepted Git changes and set
    `escalated`. A narrative from the agent is not a result.
    """
    locked = escalated_lock()
    if locked is not None:
        previous = locked.get("last_result")
        if isinstance(previous, dict):
            return dict(previous)
        return _with_session(
            {
                "accepted": False,
                "contract_ok": False,
                "targeted_ok": False,
                "full_ok": False,
                "selection": "escalated",
                "nodeids": [],
                "summary": "escalated after 3 attempts",
                "contract_violations": {
                    "reachable": False,
                    "violation_count": 0,
                    "violations": [],
                    "error": "Repair is already escalated.",
                },
                "api_health": {
                    "base_url": (base_url or api_base_url()).rstrip("/"),
                    "reachable": False,
                    "healthy": False,
                    "error": "Repair is already escalated.",
                },
                "targeted_tests": None,
                "full_tests": None,
                "next_action": _STOP_TEXT,
            },
            locked,
        )

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

    url = (base_url or api_base_url()).rstrip("/")
    key = ("verify", str(repo_root()), url, tuple(selected), source_token())
    cached = cache_get(key)
    if isinstance(cached, dict):
        return cached

    result = _verify(selected, selection, url)
    session = note_verification(bool(result["accepted"]))
    result = _with_session(result, session)
    remember(result)
    if not result.get("escalated"):
        cache_put(key, result)
    return result


def register(mcp: FastMCP) -> None:
    mcp.tool(verify_repair)


_STOP_TEXT = (
    "Repair stopped after 3 failed attempts. "
    "Unaccepted changes were restored with Git. Do not edit the code again."
)


def _verify(selected: list[str], selection: str, base_url: str) -> dict:
    violations = get_contract_violations(base_url)
    contract_ok = bool(
        violations.get("reachable")
        and violations.get("healthy")
        and violations.get("violation_count", 0) == 0
    )
    targeted = run_targeted_tests(selected) if selected else None
    targeted_ok = targeted is None or bool(targeted.get("ok") and targeted.get("all_passed"))

    if contract_ok and targeted_ok:
        full = run_full_tests()
        full_ok = bool(full.get("ok") and full.get("all_passed"))
    else:
        full = {
            "ok": True,
            "skipped": True,
            "all_passed": False,
            "passed": 0,
            "failed": 0,
            "errors": 0,
            "tests": [],
            "error": None,
            "message": "Full suite skipped because an earlier check failed.",
        }
        full_ok = False

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
            "base_url": violations.get("base_url"),
            "reachable": violations.get("reachable"),
            "healthy": violations.get("healthy"),
            "error": violations.get("error"),
        },
        "targeted_tests": _test_snapshot(targeted),
        "full_tests": _test_snapshot(full),
        "next_action": (
            "Checks passed. Save the report for human approval. Do not merge."
            if accepted
            else "Checks failed. Use these failures for another attempt. Do not describe the patch as fixed."
        ),
    }


def _with_session(result: dict, session: dict) -> dict:
    attempts = int(session.get("attempts") or 0)
    escalated = session.get("status") == "escalated"
    updated = dict(result)
    updated["attempt"] = attempts
    updated["max_attempts"] = MAX_ATTEMPTS
    updated["attempts_remaining"] = max(0, MAX_ATTEMPTS - attempts)
    updated["escalated"] = escalated
    updated["rollback"] = session.get("rollback")
    updated["escalation_report"] = session.get("escalation_report")
    if escalated:
        updated["accepted"] = False
        updated["next_action"] = _STOP_TEXT
        updated["summary"] = (
            f"escalated after {attempts} attempts; unaccepted changes restored; "
            f"{result.get('summary')}"
        )
    else:
        updated["summary"] = f"{result.get('summary')}; attempt {attempts} of {MAX_ATTEMPTS}"
        if not updated["accepted"]:
            updated["next_action"] = (
                f"Checks failed on attempt {attempts} of {MAX_ATTEMPTS}. "
                "Use these failures for another attempt. Do not describe the patch as fixed."
            )
    return updated


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
        "skipped": bool(run.get("skipped")),
        "message": run.get("message"),
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
    if full.get("skipped"):
        full_text = "full suite skipped"
    elif full.get("message") and full.get("passed", 0) == 0 and full.get("all_passed"):
        full_text = "no test suite"
    elif full.get("ok"):
        full_text = (
            f"full suite {full.get('passed', 0)} passed, "
            f"{full.get('failed', 0)} failed, "
            f"{full.get('errors', 0)} errors"
        )
    else:
        full_text = full.get("error") or "full suite failed"
    verdict = "accepted for human approval" if accepted else "not accepted"
    return f"{verdict}; {contract}; {targeted_text}; {full_text}"
