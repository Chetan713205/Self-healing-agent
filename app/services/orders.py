from app.schemas.orders import OrderCreateRequest, OrderResponse

_ORDERS = {
    101: OrderResponse(id=101, total=499.0, status="shipped"),
    102: OrderResponse(id=102, total=250.0, status="paid"),
}


def create_order(order_data: OrderCreateRequest) -> OrderResponse | None:
    if order_data.id in _ORDERS:
        return None
    order = OrderResponse(**order_data.model_dump())
    _ORDERS[order.id] = order
    return order


def get_order(order_id: int) -> OrderResponse | None:
    return _ORDERS.get(order_id)


def list_orders() -> list[OrderResponse]:
    return list(_ORDERS.values())
