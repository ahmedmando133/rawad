"""
Meta Messenger Client using Graph API (async via httpx).

Responsible for:
    - Sending text messages to users via Page-scoped ID (PSID).
    - Displaying typing indicators ("sender_action": "typing_on") for a natural human feel.
    - Handling rate limits and API errors gracefully.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

GRAPH_API_VERSION = os.getenv("META_GRAPH_API_VERSION", "v21.0")
GRAPH_API_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}/me/messages"


class MessengerClient:
    """Async client for Meta Graph API messaging."""

    def __init__(self, page_access_token: str | None = None) -> None:
        self.access_token = page_access_token or os.getenv("META_PAGE_ACCESS_TOKEN", "")
        if not self.access_token or self.access_token.startswith("your_"):
            logger.warning(
                "META_PAGE_ACCESS_TOKEN is not configured or still a placeholder. "
                "Outgoing Messenger calls will fail until a valid Page token is set in .env."
            )

    async def send_typing_indicator(self, recipient_id: str) -> bool:
        """Show typing indicator ('مساعد العيادة يكتب الآن...') in Messenger."""
        payload = {
            "recipient": {"id": recipient_id},
            "sender_action": "typing_on",
        }
        return await self._post_to_graph(payload)

    async def send_text_message(self, recipient_id: str, text: str) -> bool:
        """Send a plain text message to the recipient."""
        text = (text or "").strip()
        if not text:
            return False

        # Facebook Messenger limits single message text to 2000 characters
        if len(text) > 2000:
            chunks = [text[i : i + 1950] for i in range(0, len(text), 1950)]
            success = True
            for chunk in chunks:
                ok = await self.send_text_message(recipient_id, chunk)
                if not ok:
                    success = False
            return success

        payload = {
            "recipient": {"id": recipient_id},
            "messaging_type": "RESPONSE",
            "message": {"text": text},
        }
        return await self._post_to_graph(payload)

    async def _post_to_graph(self, payload: dict[str, Any]) -> bool:
        if not self.access_token or self.access_token.startswith("your_"):
            logger.error("Cannot send to Meta: META_PAGE_ACCESS_TOKEN is missing or invalid.")
            return False

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(GRAPH_API_URL, json=payload, headers=headers)
                if response.status_code == 200:
                    return True

                logger.error(
                    "Meta Graph API error (status %s): %s",
                    response.status_code,
                    response.text,
                )
                return False
        except Exception:
            logger.exception("HTTP error while calling Meta Graph API.")
            return False
