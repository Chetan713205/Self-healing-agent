from fastapi import APIRouter, HTTPException

from app.schemas.invoices import InvoiceResponse
from app.services.invoices import get_invoice, list_invoices

router = APIRouter(prefix="/invoices", tags=["invoices"])


@router.get("", response_model=list[InvoiceResponse])
def read_invoices() -> list[InvoiceResponse]:
    return list_invoices()


@router.get("/{invoice_id}", response_model=InvoiceResponse)
def read_invoice(invoice_id: str) -> InvoiceResponse:
    invoice = get_invoice(invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice