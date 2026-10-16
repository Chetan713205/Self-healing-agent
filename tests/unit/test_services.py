import pytest

from app.services.invoices import get_invoice, list_invoices
from app.services.orders import get_order, list_orders
from app.services.reports import get_revenue_report


def test_order_service_returns_sample_order() -> None:
    order = get_order(101)

    assert order is not None
    assert order.model_dump() == {"id": 101, "total": 499.0, "status": "shipped"}


def test_order_service_returns_none_for_unknown_order() -> None:
    assert get_order(999) is None


def test_invoice_service_calculates_from_order_total() -> None:
    invoice = get_invoice("INV-101")

    assert invoice is not None
    assert invoice.amount == 499.0
    assert invoice.tax == 49.9
    assert invoice.total == 548.9


def test_invoice_service_has_one_invoice_per_order() -> None:
    assert len(list_invoices()) == len(list_orders())


def test_revenue_report_aggregates_invoice_totals() -> None:
    report = get_revenue_report()

    assert report.invoice_count == 2
    assert report.total_revenue == pytest.approx(823.9)
