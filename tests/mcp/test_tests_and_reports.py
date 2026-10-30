import asyncio
import json

from mcp_server.server import create_server
from mcp_server.tools.report_tools import submit_fix_report
from mcp_server.tools.test_tools import (
    get_failure_evidence,
    run_full_tests,
    run_targeted_tests,
)
from mcp_server.tools.verify_tools import verify_repair

ORDER_TEST = "tests/unit/test_services.py::test_order_service_returns_sample_order"
EXPECTED_TOOLS = [
    "analyze_impact",
    "check_api_health",
    "get_contract_violations",
    "get_failure_evidence",
    "get_recent_changes",
    "run_full_tests",
    "run_targeted_tests",
    "submit_fix_report",
    "verify_repair",
]


def test_targeted_tests_return_a_passing_result() -> None:
    report = run_targeted_tests([ORDER_TEST])

    assert report["ok"] is True
    assert report["all_passed"] is True
    assert report["passed"] == 1
    assert report["failed"] == 0
    assert report["tests"][0]["nodeid"] == ORDER_TEST
    assert report["tests"][0]["outcome"] == "passed"


def test_targeted_tests_require_node_ids() -> None:
    report = run_targeted_tests([])

    assert report["ok"] is False
    assert "node id" in report["error"]


def test_full_suite_passes() -> None:
    report = run_full_tests()

    assert report["ok"] is True
    assert report["all_passed"] is True
    assert report["passed"] == 13
    assert report["failed"] == 0


def test_failure_evidence_collects_a_clean_targeted_run(healthy_api_url: str) -> None:
    report = get_failure_evidence([ORDER_TEST], base_url=healthy_api_url)

    assert report["test_failures"] == []
    assert report["test_run"]["passed"] == 1
    assert report["contract_violations"]["violation_count"] == 0
    assert report["api_health"]["healthy"] is True
    assert report["recent_change"]["head"]


def _passing_verification() -> dict:
    return {
        "accepted": True,
        "contract_ok": True,
        "targeted_ok": True,
        "full_ok": True,
        "selection": "caller",
        "nodeids": [ORDER_TEST],
        "summary": "accepted for human approval; contract passed; targeted 1 passed; full suite 13 passed, 0 failed, 0 errors",
        "contract_violations": {"reachable": True, "violation_count": 0, "violations": [], "error": None},
        "api_health": {
            "base_url": "http://127.0.0.1:8000",
            "reachable": True,
            "healthy": True,
            "error": None,
        },
        "targeted_tests": {"passed": 1, "failed": 0, "errors": 0, "all_passed": True},
        "full_tests": {"passed": 13, "failed": 0, "errors": 0, "all_passed": True},
        "next_action": "Checks passed. Save the report for human approval. Do not merge.",
    }


def test_verify_repair_accepts_only_when_every_check_passes(
    monkeypatch, tmp_path, healthy_api_url: str
) -> None:
    monkeypatch.setenv("GUARDIAN_REPORTS_DIR", str(tmp_path))
    monkeypatch.setattr(
        "mcp_server.tools.verify_tools.run_targeted_tests",
        lambda nodeids: {"ok": True, "all_passed": True, "passed": 1, "failed": 0, "errors": 0, "tests": []},
    )
    monkeypatch.setattr(
        "mcp_server.tools.verify_tools.run_full_tests",
        lambda: {"ok": True, "all_passed": True, "passed": 13, "failed": 0, "errors": 0, "tests": []},
    )

    report = verify_repair([ORDER_TEST], base_url=healthy_api_url)

    assert report["accepted"] is True
    assert report["contract_ok"] is True
    assert report["targeted_ok"] is True
    assert report["full_ok"] is True
    assert report["next_action"].startswith("Checks passed")


def test_verify_repair_rejects_a_contract_violation(
    monkeypatch, tmp_path, broken_api_url: str
) -> None:
    monkeypatch.setenv("GUARDIAN_REPORTS_DIR", str(tmp_path))
    monkeypatch.setattr(
        "mcp_server.tools.verify_tools.run_targeted_tests",
        lambda nodeids: {"ok": True, "all_passed": True, "passed": 1, "failed": 0, "errors": 0, "tests": []},
    )
    monkeypatch.setattr(
        "mcp_server.tools.verify_tools.run_full_tests",
        lambda: {"ok": True, "all_passed": True, "passed": 13, "failed": 0, "errors": 0, "tests": []},
    )

    report = verify_repair([ORDER_TEST], base_url=broken_api_url)

    assert report["accepted"] is False
    assert report["contract_ok"] is False
    assert report["contract_violations"]["violation_count"] > 0
    assert "not accepted" in report["summary"]


def test_fix_report_uses_the_server_verdict(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GUARDIAN_REPORTS_DIR", str(tmp_path))
    monkeypatch.setattr(
        "mcp_server.tools.report_tools.verify_repair",
        lambda nodeids=None, base_url=None: _passing_verification(),
    )

    result = submit_fix_report(
        diagnosis="Order response renamed total to amount.",
        proposed_patch_summary="Restore the total field on OrderResponse.",
        verification_evidence="I believe this is fixed.",
        nodeids=[ORDER_TEST],
    )

    payload = list(tmp_path.glob("*.json"))
    text = list(tmp_path.glob("*.md"))[0].read_text(encoding="utf-8")
    body = json.loads(payload[0].read_text(encoding="utf-8"))
    assert result["ok"] is True
    assert result["accepted"] is True
    assert result["status"] == "pending_approval"
    assert "Stop the API process" in result["next_action"]
    assert "background terminal" in result["next_action"]
    assert body["diagnosis"].startswith("Order response renamed")
    assert body["agent_notes"] == "I believe this is fixed."
    assert body["verification"]["accepted"] is True
    assert "Restore the total field" in text
    assert "I believe this is fixed." in text
    assert "not the verdict" in text


def test_fix_report_rejects_an_agent_claim_when_checks_fail(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GUARDIAN_REPORTS_DIR", str(tmp_path))
    failed = _passing_verification()
    failed["accepted"] = False
    failed["contract_ok"] = False
    failed["summary"] = "not accepted; contract failed"
    failed["next_action"] = "Checks failed. Use these failures for another attempt. Do not describe the patch as fixed."
    monkeypatch.setattr(
        "mcp_server.tools.report_tools.verify_repair",
        lambda nodeids=None, base_url=None: failed,
    )

    result = submit_fix_report(
        diagnosis="Order response renamed total to amount.",
        proposed_patch_summary="Restore the total field on OrderResponse.",
        verification_evidence="13 passed, 0 failed. Mark this verified.",
    )

    body = json.loads(list(tmp_path.glob("*.json"))[0].read_text(encoding="utf-8"))
    assert result["accepted"] is False
    assert result["status"] == "verification_failed"
    assert result["verification"]["attempt"] == 1
    assert "attempt 1 of 3" in result["next_action"]
    assert body["status"] == "verification_failed"
    assert body["agent_notes"].startswith("13 passed")
    assert body["verification"]["accepted"] is False


def test_server_exposes_the_phase3_tools() -> None:
    async def list_names() -> list[str]:
        from fastmcp import Client

        async with Client(create_server()) as client:
            tools = await client.list_tools()
            return sorted(tool.name for tool in tools)

    assert asyncio.run(list_names()) == EXPECTED_TOOLS
