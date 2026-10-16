from fastapi import APIRouter

from app.schemas.reports import RevenueReportResponse
from app.services.reports import get_revenue_report

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/revenue", response_model=RevenueReportResponse)
def read_revenue_report() -> RevenueReportResponse:
    return get_revenue_report()