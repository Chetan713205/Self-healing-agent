from mcp_server.tools.git_tools import get_recent_changes
from mcp_server.tools.impact_tools import analyze_impact


def test_recent_changes_include_head_and_a_diff() -> None:
    report = get_recent_changes(limit=3)

    assert report["ok"] is True
    assert report["head"]
    assert report["branch"]
    assert report["recent_commits"]
    assert report["recent_commits"][0]["sha"] == report["head"]
    assert "diff --git" in report["latest_diff"]


def test_order_change_reaches_invoices_and_revenue() -> None:
    report = analyze_impact(
        ["app/schemas/orders.py", "app/services/orders.py"]
    )

    assert report["directly_changed_services"] == ["orders"]
    assert report["affected_services"] == ["invoices", "orders", "reports"]
    endpoints = {item["endpoint"] for item in report["affected_endpoints"]}
    assert "GET /orders/{order_id}" in endpoints
    assert "GET /invoices/{invoice_id}" in endpoints
    assert "GET /reports/revenue" in endpoints

    by_node = {item["nodeid"]: item["priority"] for item in report["relevant_tests"]}
    assert by_node[
        "tests/unit/test_services.py::test_order_service_returns_sample_order"
    ] == 1
    assert by_node[
        "tests/unit/test_services.py::test_invoice_service_calculates_from_order_total"
    ] == 2
    assert by_node[
        "tests/unit/test_services.py::test_revenue_report_aggregates_invoice_totals"
    ] == 2
    assert report["run_full_suite_still_required"] is True


def test_invoice_change_does_not_select_order_unit_tests() -> None:
    report = analyze_impact([r"app\services\invoices.py"])

    nodeids = {item["nodeid"] for item in report["relevant_tests"]}
    assert "tests/unit/test_services.py::test_invoice_service_calculates_from_order_total" in nodeids
    assert (
        "tests/integration/test_api.py::test_api_responses_match_contracts"
        "[/reports/revenue-reports.json]"
    ) in nodeids
    assert "tests/unit/test_services.py::test_order_service_returns_sample_order" not in nodeids
    assert report["directly_changed_services"] == ["invoices"]
    assert "reports" in report["affected_services"]
    assert "orders" not in report["affected_services"]


def test_unknown_file_is_reported_instead_of_guessed() -> None:
    report = analyze_impact(["README.md"])

    assert report["unmapped_files"] == ["README.md"]
    assert report["affected_services"] == []
    assert report["recommended_nodeids"] == []
