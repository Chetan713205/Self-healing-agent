import socket
import threading
import time

import httpx
import pytest
import uvicorn
from fastapi import FastAPI

from app.main import app as sample_app


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class _QuietServer(uvicorn.Server):
    def install_signal_handlers(self) -> None:
        return None


def serve(application):
    port = _free_port()
    config = uvicorn.Config(
        application,
        host="127.0.0.1",
        port=port,
        log_level="warning",
    )
    server = _QuietServer(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            if httpx.get(f"{base_url}/health", timeout=0.5).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.05)
    else:
        server.should_exit = True
        thread.join(timeout=5)
        raise RuntimeError("Test API did not start")

    yield base_url
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(scope="module")
def healthy_api_url():
    yield from serve(sample_app)


def broken_order_app() -> FastAPI:
    application = FastAPI()

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/orders/101")
    def order() -> dict:
        return {"id": 101, "amount": 499.0, "status": "shipped"}

    @application.get("/invoices/INV-101")
    def invoice() -> dict:
        return {
            "id": "INV-101",
            "order_id": 101,
            "amount": 499.0,
            "tax": 49.9,
            "total": 548.9,
            "status": "issued",
        }

    @application.get("/reports/revenue")
    def revenue() -> dict:
        return {"invoice_count": 2, "total_revenue": 823.9}

    return application


@pytest.fixture(scope="module")
def broken_api_url():
    yield from serve(broken_order_app())
