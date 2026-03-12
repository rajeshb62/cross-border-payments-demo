"""Inbound webhooks from external providers."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from services import airwallex as airwallex_svc
from services.transaction import settle_from_airwallex_webhook

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
logger = logging.getLogger(__name__)


@router.post(
    "/airwallex",
    status_code=status.HTTP_200_OK,
    summary="Airwallex payment status notification",
)
async def airwallex_webhook(
    request: Request,
    x_signature: str = Header(..., alias="x-signature"),
    db: AsyncSession = Depends(get_db),
):
    """
    Airwallex calls this endpoint when a payment reaches PAID or FAILED.

    Airwallex expects a 200 within 10 s; otherwise it retries with exponential
    back-off for up to 24 hours. Register this URL in the Airwallex portal
    under Developers → Webhooks.
    """
    raw_body = await request.body()

    if not airwallex_svc.verify_webhook_signature(raw_body, x_signature):
        logger.warning("Airwallex webhook: invalid signature")
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    payload = airwallex_svc.AirwallexWebhookPayload.model_validate_json(raw_body)
    logger.info("Airwallex webhook received: event=%s payment=%s", payload.name, payload.payment_id)

    if payload.name == "payment.paid":
        tx = await settle_from_airwallex_webhook(db, payload.payment_id, success=True)
        await db.commit()
        logger.info("Transaction %s settled via Airwallex (payment %s)", tx.id, payload.payment_id)

    elif payload.name == "payment.failed":
        tx = await settle_from_airwallex_webhook(
            db, payload.payment_id, success=False, failure_reason=payload.error_message
        )
        await db.commit()
        logger.error(
            "Transaction %s failed via Airwallex: %s", tx.id, payload.error_message
        )

    else:
        # Informational events (e.g. "payment.pending") — ack and ignore
        logger.debug("Airwallex webhook: unhandled event %s", payload.name)

    return {"received": True}
