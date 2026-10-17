import asyncio
import json

from mcp_server.server import create_server
from mcp_server.tools.report_tools import submit_fix_report
from mcp_server.tools.test_tools import (
    get_failure_evidence,
    run_full_tests,
    run_targeted_tests,
)

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


def test_fix_report_is_saved(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GUARDIAN_REPORTS_DIR", str(tmp_path))
    monkeypatch.setenv("GUARDIAN_API_BASE_URL", "http://127.0.0.1:59999")

    result = submit_fix_report(
        diagnosis="Order response renamed total to amount.",
        proposed_patch_summary="Restore the total field on OrderResponse.",
        verification_evidence="13 passed, 0 failed.",
        status="pending_approval",
    )

    markdown = list(tmp_path.glob("*.md"))
    payload = list(tmp_path.glob("*.json"))
    assert result["ok"] is True
    assert len(markdown) == 1
    assert len(payload) == 1
    body = json.loads(payload[0].read_text(encoding="utf-8"))
    text = markdown[0].read_text(encoding="utf-8")
    assert body["status"] == "pending_approval"
    assert body["diagnosis"].startswith("Order response renamed")
    assert "Restore the total field" in text
    assert "13 passed, 0 failed." in text


def test_server_exposes_the_phase3_tools() -> None:
    async def list_names() -> list[str]:
        from fastmcp import Client

        async with Client(create_server()) as client:
            tools = await client.list_tools()
            return sorted(tool.name for tool in tools)

    assert asyncio.run(list_names()) == EXPECTED_TOOLS
