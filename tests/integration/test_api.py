import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jsonschema import validate

from app.main import app
from app.schemas.orders import OrderResponse
from app.services import orders as orders_service

client = TestClient(app)
CONTRACTS_DIR = Path(__file__).resolve().parents[2] / "contracts"


def load_contract(name: str) -> dict:
    with (CONTRACTS_DIR / name).open(encoding="utf-8") as contract_file:
        return json.load(contract_file)


@pytest.mark.parametrize(
    ("path", "contract_file"),
    [
        ("/orders/101", "order.json"),
        ("/invoices/INV-101", "invoices.json"),
        ("/reports/revenue", "reports.json"),
    ],
)
def test_api_responses_match_contracts(path: str, contract_file: str) -> None:
    response = client.get(path)

    assert response.status_code == 200
    validate(instance=response.json(), schema=load_contract(contract_file))


def test_order_invoice_and_report_share_consistent_totals() -> None:
    order = client.get("/orders/101").json()
    invoice = client.get("/invoices/INV-101").json()
    report = client.get("/reports/revenue").json()

    assert invoice["amount"] == order["total"]
    assert report["total_revenue"] == pytest.approx(823.9)


def test_create_order_updates_invoice_and_revenue_services(monkeypatch) -> None:
    monkeypatch.setattr(
        orders_service,
        "_ORDERS",
        {101: OrderResponse(id=101, total=499.0, status="shipped")},
    )

    response = client.post(
        "/orders",
        json={"id": 103, "total": 100.0, "status": "pending"},
    )

    assert response.status_code == 201
    assert response.json() == {"id": 103, "total": 100.0, "status": "pending"}
    assert client.get("/invoices/INV-103").json()["total"] == 110.0
    assert client.get("/reports/revenue").json() == {
        "invoice_count": 2,
        "total_revenue": 658.9,
    }


@pytest.mark.parametrize(
    ("path", "message"),
    [("/orders/999", "Order not found"), ("/invoices/INV-999", "Invoice not found")],
)
def test_missing_resources_return_404(path: str, message: str) -> None:
    response = client.get(path)

    assert response.status_code == 404
    assert response.json() == {"detail": message}


def test_openapi_describes_all_business_endpoints() -> None:
    paths = app.openapi()["paths"]

    assert "post" in paths["/orders"]
    assert "/orders/{order_id}" in paths
    assert "/invoices/{invoice_id}" in paths
    assert "/reports/revenue" in paths
