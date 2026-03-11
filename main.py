from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from api.routes import transactions, rates, compliance, beneficiaries
from core.config import settings
from core.exceptions import (
    PaymentBaseException,
    RateLockExpiredError,
    LRSLimitExceededError,
    ComplianceError,
    InvalidStateMachineTransitionError,
    FXError,
)

app = FastAPI(
    title="INR→USD Cross-Border Payments",
    version="1.0.0",
    description="FX remittance system with RBI/FEMA/LRS compliance",
)

# ── Exception handlers ────────────────────────────────────────────────────────

@app.exception_handler(RateLockExpiredError)
async def rate_lock_expired_handler(request: Request, exc: RateLockExpiredError):
    return JSONResponse(status_code=410, content={"error": "rate_lock_expired", "detail": str(exc)})


@app.exception_handler(LRSLimitExceededError)
async def lrs_limit_handler(request: Request, exc: LRSLimitExceededError):
    return JSONResponse(status_code=422, content={"error": "lrs_limit_exceeded", "detail": str(exc)})


@app.exception_handler(ComplianceError)
async def compliance_handler(request: Request, exc: ComplianceError):
    return JSONResponse(status_code=422, content={"error": "compliance_error", "detail": str(exc)})


@app.exception_handler(InvalidStateMachineTransitionError)
async def state_machine_handler(request: Request, exc: InvalidStateMachineTransitionError):
    return JSONResponse(status_code=409, content={"error": "invalid_state_transition", "detail": str(exc)})


@app.exception_handler(FXError)
async def fx_error_handler(request: Request, exc: FXError):
    return JSONResponse(status_code=502, content={"error": "fx_error", "detail": str(exc)})


@app.exception_handler(PaymentBaseException)
async def payment_base_handler(request: Request, exc: PaymentBaseException):
    return JSONResponse(status_code=400, content={"error": "payment_error", "detail": str(exc)})


# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(transactions.router, prefix="/transactions", tags=["transactions"])
app.include_router(rates.router, prefix="/rates", tags=["rates"])
app.include_router(compliance.router, prefix="/compliance", tags=["compliance"])
app.include_router(beneficiaries.router, prefix="/beneficiaries", tags=["beneficiaries"])


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok", "env": settings.APP_ENV}
