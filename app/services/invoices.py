from app.schemas.invoices import InvoiceResponse
from app.services.orders import list_orders

_TAX_RATE = 0.10


def list_invoices() -> list[InvoiceResponse]:
    invoices = []
    for order in list_orders():
        tax = round(order.total * _TAX_RATE, 2)
        invoices.append(
            InvoiceResponse(
                id=f"INV-{order.id}",
                order_id=order.id,
                amount=order.total,
                tax=tax,
                total=round(order.total + tax, 2),
                status="issued",
            )
        )
    return invoices


def get_invoice(invoice_id: str) -> InvoiceResponse | None:
    return next(
        (invoice for invoice in list_invoices() if invoice.id == invoice_id),
        None,
    )
