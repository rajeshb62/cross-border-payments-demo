from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from api.routes import merchants, payments, fx_rates, reconciliation
from core.config import settings
from core.exceptions import (
    CrossBorderAppBaseException,
    MerchantNotFoundError,
    MerchantNotApprovedError,
    TransactionNotFoundError,
    FXRateUnavailableError,
    InvalidTransactionStateError,
    OGPSPLimitExceededError,
)

app = FastAPI(
    title="CrossBorderApp — Cross-Border Payments for Foreign Merchants",
    version="2.0.0",
    description=(
        "Foreign merchants (RBI PA-CB / OPGSP licensed) collect INR payments from Indian customers "
        "and settle in their preferred currency (USD, SGD, AED, GBP, HKD)."
    ),
)


@app.exception_handler(MerchantNotFoundError)
async def merchant_not_found_handler(request: Request, exc: MerchantNotFoundError):
    return JSONResponse(status_code=404, content={"error": "merchant_not_found", "detail": str(exc)})


@app.exception_handler(MerchantNotApprovedError)
async def merchant_not_approved_handler(request: Request, exc: MerchantNotApprovedError):
    return JSONResponse(status_code=403, content={"error": "merchant_not_approved", "detail": str(exc)})


@app.exception_handler(OGPSPLimitExceededError)
async def opgsp_limit_handler(request: Request, exc: OGPSPLimitExceededError):
    return JSONResponse(status_code=422, content={"error": "opgsp_limit_exceeded", "detail": str(exc)})


@app.exception_handler(TransactionNotFoundError)
async def transaction_not_found_handler(request: Request, exc: TransactionNotFoundError):
    return JSONResponse(status_code=404, content={"error": "transaction_not_found", "detail": str(exc)})


@app.exception_handler(FXRateUnavailableError)
async def fx_rate_unavailable_handler(request: Request, exc: FXRateUnavailableError):
    return JSONResponse(status_code=502, content={"error": "fx_rate_unavailable", "detail": str(exc)})


@app.exception_handler(InvalidTransactionStateError)
async def invalid_state_handler(request: Request, exc: InvalidTransactionStateError):
    return JSONResponse(status_code=409, content={"error": "invalid_state_transition", "detail": str(exc)})


@app.exception_handler(CrossBorderAppBaseException)
async def base_handler(request: Request, exc: CrossBorderAppBaseException):
    return JSONResponse(status_code=400, content={"error": "payment_error", "detail": str(exc)})


app.include_router(merchants.router, prefix="/merchants", tags=["merchants"])
app.include_router(payments.router, prefix="/payments", tags=["payments"])
app.include_router(fx_rates.router, prefix="/fx-rates", tags=["fx-rates"])
app.include_router(reconciliation.router, prefix="/reconciliation", tags=["reconciliation"])


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok", "env": settings.APP_ENV}
