from pydantic import BaseModel, ConfigDict, Field


class RevenueReportResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invoice_count: int = Field(ge=0, examples=[2])
    total_revenue: float = Field(ge=0, examples=[823.9])
