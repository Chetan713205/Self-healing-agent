from pydantic import BaseModel, ConfigDict, Field


class OrderCreateRequest(BaseModel):
    id: int = Field(gt=0, examples=[103])
    total: float = Field(ge=0, examples=[100.0])
    status: str = Field(examples=["pending"])


class OrderResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int = Field(examples=[101])
    total: float = Field(ge=0, examples=[499.0])
    status: str = Field(examples=["shipped"])
