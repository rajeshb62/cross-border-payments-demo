"""Airwallex payout client.

Airwallex is a global payments platform that delivers USD to beneficiary bank
accounts using LOCAL rails (domestic ACH / Faster Payments / SEPA) rather than
SWIFT, eliminating correspondent-bank hops, reducing fees, and cutting delivery
time from 1-3 days to hours.

Flow:
  1. Create a beneficiary (register the recipient's bank details once).
     Airwallex returns a `beneficiary_id` we cache on the Beneficiary row.
  2. Create a payment from our Airwallex wallet to that beneficiary, specifying
     payment_method="LOCAL" to route via local rails (not SWIFT).
     Airwallex returns a `payment_id` stored as `payout_order_id` on Transaction.
  3. Airwallex POSTs a webhook when the payment reaches PAID or FAILED.

Auth: OAuth2 bearer token obtained by calling /authentication/login with
  x-api-key + x-client-id headers. Token is valid for 30 minutes; we cache it
  in memory and refresh automatically — much simpler than Coinbase's per-request
  HMAC signing.

API reference: https://www.airwallex.com/docs/api
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import time
from datetime import datetime, timezone
from decimal import Decimal

import httpx
from pydantic import BaseModel

from core.config import settings

logger = logging.getLogger(__name__)

AIRWALLEX_BASE_URL = "https://api.airwallex.com/api/v1"

# FEMA purpose code → Airwallex payment reason
_PURPOSE_TO_REASON: dict[str, str] = {
    "P0001": "EDUCATION",
    "P0002": "EDUCATION",
    "P0003": "MEDICAL",
    "P0301": "FAMILY_SUPPORT",
    "P1301": "TRAVEL",
}
_DEFAULT_REASON = "OTHER"


# ── OAuth2 token cache ────────────────────────────────────────────────────────
# Module-level cache: token is valid 30 min, refreshed automatically.

_token: str | None = None
_token_expires_at: float = 0.0      # unix timestamp


async def _get_token() -> str:
    """Return a valid Bearer token, refreshing if within 60 s of expiry."""
    global _token, _token_expires_at

    if _token and time.time() < _token_expires_at - 60:
        return _token

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            f"{AIRWALLEX_BASE_URL}/authentication/login",
            headers={
                "x-api-key": settings.AIRWALLEX_API_KEY,
                "x-client-id": settings.AIRWALLEX_CLIENT_ID,
            },
        )
    response.raise_for_status()
    data = response.json()
    _token = data["token"]
    # expires_at is ISO-8601 e.g. "2026-03-12T10:30:00+0000"
    dt = datetime.fromisoformat(data["expires_at"].replace("+0000", "+00:00"))
    _token_expires_at = dt.timestamp()
    logger.debug("Airwallex token refreshed, expires %s", data["expires_at"])
    return _token


async def _headers() -> dict[str, str]:
    token = await _get_token()
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


# ── Beneficiary models ────────────────────────────────────────────────────────

class AirwallexBankDetails(BaseModel):
    account_currency: str = "USD"
    account_name: str
    account_number: str
    bank_country_code: str          # ISO-3166 alpha-2
    bank_name: str
    aba: str | None = None          # ABA routing number — required for US USD accounts
    swift_code: str | None = None   # SWIFT BIC — used for non-US international accounts


class AirwallexCreateBeneficiaryRequest(BaseModel):
    request_id: str                 # "ben-<beneficiary_uuid>" — idempotency key
    name: str
    entity_type: str = "PERSONAL"   # "PERSONAL" | "COMPANY"
    bank_details: AirwallexBankDetails


class AirwallexBeneficiaryResponse(BaseModel):
    beneficiary_id: str             # cached as airwallex_beneficiary_id on Beneficiary
    name: str
    status: str                     # "PENDING_VERIFICATION" | "VERIFIED"


# ── Payment models ────────────────────────────────────────────────────────────

class AirwallexCreatePaymentRequest(BaseModel):
    request_id: str                 # transaction UUID — idempotency key
    source_currency: str = "USD"
    source_amount: float
    payment_currency: str = "USD"
    payment_amount: float
    beneficiary_id: str
    payment_method: str = "LOCAL"   # LOCAL = domestic rails (ACH/Faster Payments)
                                    # SWIFT = international wire (more expensive, slower)
    reason: str = "OTHER"           # maps from FEMA purpose code
    payment_date: str | None = None # YYYY-MM-DD; omit for same-day


class AirwallexPaymentResponse(BaseModel):
    payment_id: str                 # stored as payout_order_id on Transaction
    status: str                     # "CREATED" | "PENDING" | "PAID" | "FAILED" | "CANCELLED"
    source_currency: str
    source_amount: float
    payment_currency: str
    payment_amount: float
    error_message: str | None = None


# ── Webhook models ────────────────────────────────────────────────────────────

class AirwallexWebhookPayload(BaseModel):
    """
    Airwallex wraps all events as:
    {"name": "payment.paid", "payment_id": "...", "status": "PAID", ...}
    """
    name: str                       # "payment.paid" | "payment.failed"
    payment_id: str
    status: str
    error_message: str | None = None


# ── Beneficiary registration ──────────────────────────────────────────────────

async def create_beneficiary(
    beneficiary_id: str,
    full_name: str,
    account_number: str,
    bank_country_code: str,
    bank_name: str,
    aba: str | None = None,         # ABA routing number (US)
    swift_code: str | None = None,  # SWIFT BIC (international)
) -> AirwallexBeneficiaryResponse:
    """
    Register a beneficiary's bank account with Airwallex.

    One-time per beneficiary. Airwallex returns a `beneficiary_id` we cache
    on the Beneficiary row and reuse for all future payments.

    For US USD accounts, provide `aba` (ABA routing number).
    For non-US accounts, provide `swift_code` (SWIFT BIC).

    Idempotency: `request_id` = "ben-<our beneficiary UUID>". Airwallex returns
    the existing record if the same request_id is submitted again.
    """
    payload = AirwallexCreateBeneficiaryRequest(
        request_id=f"ben-{beneficiary_id}",
        name=full_name,
        bank_details=AirwallexBankDetails(
            account_name=full_name,
            account_number=account_number,
            bank_country_code=bank_country_code,
            bank_name=bank_name,
            aba=aba,
            swift_code=swift_code,
        ),
    )

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{AIRWALLEX_BASE_URL}/beneficiaries/create",
            headers=await _headers(),
            content=payload.model_dump_json(exclude_none=True),
        )

    if response.status_code == 409:
        logger.info("Airwallex beneficiary already exists for %s, fetching", beneficiary_id)
        return await get_beneficiary(f"ben-{beneficiary_id}")

    response.raise_for_status()
    data = response.json()
    logger.info(
        "Airwallex beneficiary created: beneficiary_id=%s our_id=%s",
        data["beneficiary_id"], beneficiary_id,
    )
    return AirwallexBeneficiaryResponse(**data)


async def get_beneficiary(request_id: str) -> AirwallexBeneficiaryResponse:
    """Fetch an existing beneficiary by the request_id used at creation."""
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(
            f"{AIRWALLEX_BASE_URL}/beneficiaries",
            headers=await _headers(),
            params={"request_id": request_id},
        )
    response.raise_for_status()
    items = response.json().get("items", [])
    if not items:
        raise ValueError(f"Airwallex beneficiary not found for request_id={request_id}")
    return AirwallexBeneficiaryResponse(**items[0])


# ── Payment ───────────────────────────────────────────────────────────────────

async def create_payment(
    transaction_id: str,
    amount_usd: Decimal,
    airwallex_beneficiary_id: str,
    purpose_code: str = "",
) -> AirwallexPaymentResponse:
    """
    Initiate a LOCAL USD payment to a registered beneficiary.

    `payment_method="LOCAL"` routes via domestic rails at the destination
    (e.g. ACH for US), avoiding SWIFT entirely. This is the key efficiency gain:
    - No correspondent bank fees (typically $15-$45 per SWIFT transfer)
    - Same-day or next-day delivery vs. 1-3 days for SWIFT
    """
    reason = _PURPOSE_TO_REASON.get(purpose_code, _DEFAULT_REASON)
    payload = AirwallexCreatePaymentRequest(
        request_id=transaction_id,
        source_amount=float(amount_usd),
        payment_amount=float(amount_usd),
        beneficiary_id=airwallex_beneficiary_id,
        reason=reason,
    )

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{AIRWALLEX_BASE_URL}/payments/create",
            headers=await _headers(),
            content=payload.model_dump_json(exclude_none=True),
        )

    if response.status_code == 409:
        logger.info("Airwallex payment already exists for tx %s, fetching status", transaction_id)
        return await get_payment_by_request_id(transaction_id)

    response.raise_for_status()
    data = response.json()
    logger.info(
        "Airwallex payment created: payment_id=%s tx=%s amount=%s method=LOCAL",
        data["payment_id"], transaction_id, amount_usd,
    )
    return AirwallexPaymentResponse(**data)


async def get_payment_by_request_id(transaction_id: str) -> AirwallexPaymentResponse:
    """Look up a payment by request_id (our transaction UUID)."""
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(
            f"{AIRWALLEX_BASE_URL}/payments",
            headers=await _headers(),
            params={"request_id": transaction_id},
        )
    response.raise_for_status()
    items = response.json().get("items", [])
    if not items:
        raise ValueError(f"Airwallex payment not found for request_id={transaction_id}")
    return AirwallexPaymentResponse(**items[0])


async def get_payment_status(payment_id: str) -> AirwallexPaymentResponse:
    """Fetch a payment's current status by Airwallex payment_id."""
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(
            f"{AIRWALLEX_BASE_URL}/payments/{payment_id}",
            headers=await _headers(),
        )
    response.raise_for_status()
    return AirwallexPaymentResponse(**response.json())


# ── Webhook signature verification ───────────────────────────────────────────

def verify_webhook_signature(raw_body: bytes, signature_header: str) -> bool:
    """
    Airwallex signs webhooks with HMAC-SHA256.
    Header: `x-signature: <hex_digest>`
    The secret is the webhook secret configured in the Airwallex portal
    under Developers → Webhooks.
    """
    expected = hmac.new(
        settings.AIRWALLEX_WEBHOOK_SECRET.encode(),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)
