from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from api.routes import merchants, payments, fx_rates, reconciliation
from core.config import settings
from core.exceptions import (
    EximPeBaseException,
    MerchantNotFoundError,
    TransactionNotFoundError,
    FXRateUnavailableError,
    InvalidTransactionStateError,
)

app = FastAPI(
    title="EximPe — Cross-Border Payments for Foreign Merchants",
    version="1.0.0",
    description="Foreign merchants collect INR payments from Indian customers and settle in their preferred currency.",
)


@app.exception_handler(MerchantNotFoundError)
async def merchant_not_found_handler(request: Request, exc: MerchantNotFoundError):
    return JSONResponse(status_code=404, content={"error": "merchant_not_found", "detail": str(exc)})


@app.exception_handler(TransactionNotFoundError)
async def transaction_not_found_handler(request: Request, exc: TransactionNotFoundError):
    return JSONResponse(status_code=404, content={"error": "transaction_not_found", "detail": str(exc)})


@app.exception_handler(FXRateUnavailableError)
async def fx_rate_unavailable_handler(request: Request, exc: FXRateUnavailableError):
    return JSONResponse(status_code=502, content={"error": "fx_rate_unavailable", "detail": str(exc)})


@app.exception_handler(InvalidTransactionStateError)
async def invalid_state_handler(request: Request, exc: InvalidTransactionStateError):
    return JSONResponse(status_code=409, content={"error": "invalid_state_transition", "detail": str(exc)})


@app.exception_handler(EximPeBaseException)
async def base_handler(request: Request, exc: EximPeBaseException):
    return JSONResponse(status_code=400, content={"error": "payment_error", "detail": str(exc)})


app.include_router(merchants.router, prefix="/merchants", tags=["merchants"])
app.include_router(payments.router, prefix="/payments", tags=["payments"])
app.include_router(fx_rates.router, prefix="/fx-rates", tags=["fx-rates"])
app.include_router(reconciliation.router, prefix="/reconciliation", tags=["reconciliation"])


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok", "env": settings.APP_ENV}
