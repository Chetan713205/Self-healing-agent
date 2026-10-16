from app.schemas.reports import RevenueReportResponse
from app.services.invoices import list_invoices


def get_revenue_report() -> RevenueReportResponse:
    invoices = list_invoices()
    return RevenueReportResponse(
        invoice_count=len(invoices),
        total_revenue=round(sum(invoice.total for invoice in invoices), 2),
    )
