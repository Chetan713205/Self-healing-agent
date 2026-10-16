from fastapi import APIRouter, HTTPException, status

from app.schemas.orders import OrderCreateRequest, OrderResponse
from app.services.orders import create_order, get_order, list_orders

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("", response_model=list[OrderResponse])
def read_orders() -> list[OrderResponse]:
    return list_orders()


@router.post("", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
def add_order(order_data: OrderCreateRequest) -> OrderResponse:
    order = create_order(order_data)
    if order is None:
        raise HTTPException(status_code=409, detail="Order already exists")
    return order


@router.get("/{order_id}", response_model=OrderResponse)
def read_order(order_id: int) -> OrderResponse:
    order = get_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return order