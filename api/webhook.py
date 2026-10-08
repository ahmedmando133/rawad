"""
FastAPI Webhook router for Meta Facebook Page / Messenger.

Endpoints:
    GET  /webhook  -> Verification challenge by Meta during setup.
    POST /webhook  -> Incoming message events from Messenger users.
"""

from __future__ import annotations

import logging
import os
from collections import OrderedDict
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, Response, status
from pydantic import BaseModel

from core.ai_engine import PediatricianAIAssistant
from core.messenger import MessengerClient

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Meta Webhook"])

# Singleton instances (shared in the application)
_assistant: PediatricianAIAssistant | None = None
_messenger: MessengerClient | None = None

# In-memory deduplication cache for recent message IDs (Meta can send duplicates)
_PROCESSED_MIDS: OrderedDict[str, bool] = OrderedDict()
_MAX_PROCESSED_MIDS = 1000


def get_assistant() -> PediatricianAIAssistant:
    global _assistant
    if _assistant is None:
        _assistant = PediatricianAIAssistant()
    return _assistant


def get_messenger() -> MessengerClient:
    global _messenger
    if _messenger is None:
        _messenger = MessengerClient()
    return _messenger


# --------------------------------------------------------------------------- #
# 1. Webhook Verification (GET /webhook)
# --------------------------------------------------------------------------- #
@router.get("/webhook")
async def verify_webhook(
    hub_mode: str | None = Query(None, alias="hub.mode"),
    hub_verify_token: str | None = Query(None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(None, alias="hub.challenge"),
) -> Response:
    """Meta verification handshake. Returns challenge string if token matches."""
    expected_token = os.getenv("META_VERIFY_TOKEN", "")

    if hub_mode == "subscribe" and hub_verify_token:
        if hub_verify_token == expected_token:
            logger.info("Meta Webhook successfully verified.")
            return Response(content=hub_challenge or "", media_type="text/plain")

        logger.warning(
            "Webhook verification failed. Token received does not match META_VERIFY_TOKEN."
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Verification token mismatch",
        )

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Missing verification parameters",
    )


# --------------------------------------------------------------------------- #
# 2. Message Event Receiver (POST /webhook)
# --------------------------------------------------------------------------- #
async def process_incoming_message(sender_id: str, message_text: str) -> None:
    """Background task to generate reply and send it back to the user."""
    assistant = get_assistant()
    messenger = get_messenger()

    try:
        # Show typing indicator for a natural, human-like chat feel
        await messenger.send_typing_indicator(sender_id)

        # Generate reply (via Safety Filter / Zero-Token DB Router / Gemini AI)
        reply = assistant.generate_reply(user_id=sender_id, user_message=message_text)

        # Send the final response to the user via Meta Graph API
        await messenger.send_text_message(sender_id, reply)
    except Exception:
        logger.exception("Error processing background message for sender_id=%s", sender_id)


@router.post("/webhook")
async def receive_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    """Receives event notifications from Meta. Returns 200 OK immediately."""
    try:
        body: dict[str, Any] = await request.json()
    except Exception:
        return {"status": "INVALID_JSON"}

    # Meta requires object to be 'page' for Messenger webhooks
    if body.get("object") != "page":
        return {"status": "IGNORED_NON_PAGE"}

    entries = body.get("entry", [])
    for entry in entries:
        messaging_events = entry.get("messaging", [])
        for event in messaging_events:
            sender_id = (event.get("sender") or {}).get("id")
            message = event.get("message")

            # Ignore echoes (messages sent by the page itself) and non-text events
            if not message or message.get("is_echo") or not sender_id:
                continue

            mid = message.get("mid")
            if mid:
                if mid in _PROCESSED_MIDS:
                    logger.debug("Skipping duplicate message mid=%s", mid)
                    continue
                _PROCESSED_MIDS[mid] = True
                if len(_PROCESSED_MIDS) > _MAX_PROCESSED_MIDS:
                    _PROCESSED_MIDS.popitem(last=False)

            text = message.get("text")
            if text:
                logger.info(
                    "Received message from PSID=%s: %s",
                    sender_id,
                    text[:40] if len(text) > 40 else text,
                )
                background_tasks.add_task(process_incoming_message, sender_id, text)

    # Always return 200 OK fast so Meta doesn't retry
    return {"status": "EVENT_RECEIVED"}
