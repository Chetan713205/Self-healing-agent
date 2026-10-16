from fastapi import FastAPI

from app.api import invoices, orders, reports

app = FastAPI(
    title="Self-Healing Agent Sample API",
    description="A small API with linked order, invoice, and revenue-reporting services.",
    version="1.0.0",
)

app.include_router(orders.router)
app.include_router(invoices.router)
app.include_router(reports.router)


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}