from mcp_server.contracts import compare_with_contract, load_contract
from mcp_server.tools.health_tools import check_api_health, get_contract_violations


def test_health_check_accepts_the_running_api(healthy_api_url: str) -> None:
    report = check_api_health(healthy_api_url)

    assert report["reachable"] is True
    assert report["healthy"] is True
    assert report["error"] is None
    assert {check["path"] for check in report["checks"]} == {
        "/health",
        "/orders/101",
        "/invoices/INV-101",
        "/reports/revenue",
    }
    assert report["skipped"] == []
    assert all(check["valid"] for check in report["checks"])
    order = next(check for check in report["checks"] if check["path"] == "/orders/101")
    assert order["contract"] == "order.json"


def test_contract_probe_detects_renamed_order_field(broken_api_url: str) -> None:
    report = get_contract_violations(broken_api_url)

    assert report["reachable"] is True
    found = {(item["kind"], item["field"]) for item in report["violations"]}
    assert ("missing_field", "total") in found
    assert ("unexpected_field", "amount") in found
    assert {item["path"] for item in report["violations"]} == {"/orders/101"}


def test_health_reports_an_unreachable_api() -> None:
    report = check_api_health("http://127.0.0.1:59999")

    assert report["reachable"] is False
    assert report["healthy"] is False
    assert "Could not connect" in report["error"]


def test_compare_with_contract_reports_incorrect_types() -> None:
    violations = compare_with_contract(
        {"id": "101", "total": 499.0, "status": "shipped"},
        load_contract("order.json"),
        path="/orders/101",
        contract_name="order.json",
    )

    assert violations[0]["kind"] == "incorrect_type"
    assert violations[0]["field"] == "id"
