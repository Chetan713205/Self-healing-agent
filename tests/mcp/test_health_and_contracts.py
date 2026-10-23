import json
import threading

import httpx

from mcp_server.contracts import compare_with_contract, discover_probes, load_contract
from mcp_server.tools import health_tools
from mcp_server.tools.health_tools import check_api_health, get_contract_violations, schema_drift


def test_health_check_accepts_the_running_api(healthy_api_url: str) -> None:
    report = check_api_health(healthy_api_url)

    assert report["reachable"] is True
    assert report["healthy"] is True
    assert report["error"] is None
    assert {check["path"] for check in report["checks"]} == {
        "/health",
        "/orders",
        "/orders/101",
        "/invoices",
        "/invoices/INV-101",
        "/reports/revenue",
    }
    assert report["skipped"] == []
    assert all(check["valid"] for check in report["checks"])
    order = next(check for check in report["checks"] if check["path"] == "/orders/101")
    assert order["contract"] == "order.json"
    order_list = next(check for check in report["checks"] if check["path"] == "/orders")
    assert order_list["contract"] == "order.json"


def test_contract_probe_detects_renamed_order_field(broken_api_url: str) -> None:
    report = get_contract_violations(broken_api_url)

    assert report["reachable"] is True
    found = {(item["kind"], item["field"]) for item in report["violations"]}
    assert ("missing_field", "total") in found
    assert ("unexpected_field", "amount") in found
    assert {item["path"] for item in report["violations"]} == {"/orders", "/orders/101"}


def test_stale_process_is_not_a_passing_contract(healthy_api_url: str, monkeypatch) -> None:
    """A server still publishing `amount` must not pass after disk renames it to `amt`."""

    def drifted(root=None):
        discovered = discover_probes(root)
        spec = json.loads(json.dumps(discovered["openapi"]))
        schema = spec["components"]["schemas"]["InvoiceResponse"]
        schema["properties"]["amt"] = schema["properties"].pop("amount")
        schema["required"] = [
            "amt" if name == "amount" else name for name in schema["required"]
        ]
        return {**discovered, "openapi": spec}

    monkeypatch.setattr("mcp_server.tools.health_tools.discover_probes", drifted)

    report = check_api_health(healthy_api_url)

    assert report["reachable"] is True
    assert report["healthy"] is False
    assert report["stale"] is True
    assert report["checks"][0]["violations"][0]["kind"] == "stale_process"
    assert "server has amount" in report["error"]
    assert "source has amt" in report["error"]
    violations = get_contract_violations(healthy_api_url)
    assert violations["stale"] is True
    assert violations["violation_count"] == 1
    assert violations["healthy"] is False


def test_schema_drift_ignores_a_server_without_shared_models() -> None:
    disk = {
        "components": {
            "schemas": {
                "InvoiceResponse": {
                    "type": "object",
                    "required": ["amount"],
                    "properties": {"amount": {"type": "number"}},
                }
            }
        }
    }
    assert schema_drift(disk, {"components": {"schemas": {}}}) == []


def test_schema_drift_reports_a_type_change_when_names_match() -> None:
    disk = {
        "components": {
            "schemas": {
                "InvoiceResponse": {
                    "type": "object",
                    "required": ["amount"],
                    "properties": {"amount": {"type": "number"}},
                }
            }
        }
    }
    live = {
        "components": {
            "schemas": {
                "InvoiceResponse": {
                    "type": "object",
                    "required": ["amount"],
                    "properties": {"amount": {"type": "string"}},
                }
            }
        }
    }
    drifted = schema_drift(disk, live)
    assert drifted[0]["schema"] == "InvoiceResponse"
    assert drifted[0]["source_properties"] == ["amount"]
    assert drifted[0]["server_properties"] == ["amount"]


def test_health_reports_an_unreachable_api() -> None:
    report = check_api_health("http://127.0.0.1:59999")

    assert report["reachable"] is False
    assert report["healthy"] is False
    assert "Could not connect" in report["error"]


def test_each_health_check_probes_again_after_a_failure(monkeypatch) -> None:
    calls = {"n": 0}

    def probe(url: str) -> dict:
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "base_url": url,
                "reachable": False,
                "healthy": False,
                "checks": [],
                "skipped": [],
                "error": "Could not connect",
            }
        return {
            "base_url": url,
            "reachable": True,
            "healthy": True,
            "checks": [],
            "skipped": [],
            "error": None,
        }

    monkeypatch.setattr("mcp_server.tools.health_tools._probe", probe)

    first = check_api_health("http://127.0.0.1:9")
    second = check_api_health("http://127.0.0.1:9")

    assert first["reachable"] is False
    assert second["reachable"] is True
    assert calls["n"] == 2


def test_each_reachable_health_check_probes_again(monkeypatch) -> None:
    calls = {"n": 0}

    def probe(url: str) -> dict:
        calls["n"] += 1
        return {
            "base_url": url,
            "reachable": True,
            "healthy": True,
            "checks": [],
            "skipped": [],
            "error": None,
        }

    monkeypatch.setattr("mcp_server.tools.health_tools._probe", probe)

    first = check_api_health("http://127.0.0.1:9")
    second = check_api_health("http://127.0.0.1:9")

    assert first["reachable"] is True
    assert second["reachable"] is True
    assert calls["n"] == 2


def test_parallel_health_checks_each_probe_the_api(monkeypatch) -> None:
    calls = {"n": 0}

    def probe(url: str) -> dict:
        calls["n"] += 1
        return {
            "base_url": url,
            "reachable": True,
            "healthy": True,
            "checks": [],
            "skipped": [],
            "error": None,
        }

    monkeypatch.setattr("mcp_server.tools.health_tools._probe", probe)
    results: list[dict] = []

    def run() -> None:
        results.append(check_api_health("http://127.0.0.1:9"))

    threads = [threading.Thread(target=run) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert calls["n"] == 4
    assert len(results) == 4
    assert all(result["reachable"] for result in results)


def test_connect_timeout_waits_past_the_windows_refusal_delay() -> None:
    assert health_tools._TIMEOUT.connect is not None
    assert health_tools._TIMEOUT.connect >= 5.0


def test_connect_timeout_is_retried(monkeypatch) -> None:
    calls = {"n": 0}

    class _Response:
        status_code = 200

        def json(self) -> dict[str, str]:
            return {"status": "ok"}

    class _Client:
        def __init__(self, *args, **kwargs) -> None:
            return None

        def __enter__(self) -> "_Client":
            return self

        def __exit__(self, *args) -> bool:
            return False

        def get(self, url: str) -> _Response:
            calls["n"] += 1
            if calls["n"] == 1:
                raise httpx.ConnectTimeout("timed out")
            return _Response()

    monkeypatch.setattr(health_tools.httpx, "Client", _Client)
    monkeypatch.setattr(health_tools.time, "sleep", lambda _seconds: None)

    response = health_tools._get_with_retry("http://127.0.0.1:8000/health")

    assert response.status_code == 200
    assert calls["n"] == 2


def test_compare_with_contract_reports_incorrect_types() -> None:
    violations = compare_with_contract(
        {"id": "101", "total": 499.0, "status": "shipped"},
        load_contract("order.json"),
        path="/orders/101",
        contract_name="order.json",
    )

    assert violations[0]["kind"] == "incorrect_type"
    assert violations[0]["field"] == "id"
