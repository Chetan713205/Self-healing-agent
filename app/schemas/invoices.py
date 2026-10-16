from pydantic import BaseModel, ConfigDict, Field


class InvoiceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(examples=["INV-101"])
    order_id: int = Field(examples=[101])
    amount: float = Field(ge=0, examples=[499.0])
    tax: float = Field(ge=0, examples=[49.9])
    total: float = Field(ge=0, examples=[548.9])
    status: str = Field(examples=["issued"])
