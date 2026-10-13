"""
Integration tests for FastAPI Webhook endpoints using TestClient.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

# Configure test secrets BEFORE importing the app so verification is exercised.
TEST_VERIFY_TOKEN = "test_secret_verify_token_123"
TEST_APP_SECRET = "test_app_secret_456"
os.environ["META_VERIFY_TOKEN"] = TEST_VERIFY_TOKEN
os.environ["META_APP_SECRET"] = TEST_APP_SECRET

# A dummy provider key lets the assistant construct offline (clients are lazy
# and make no network call). The exercised query is a zero-token Layer-2 hit,
# so these tests never reach an LLM. This keeps the suite hermetic: it passes
# with no real .env / secrets, exactly like CI.
os.environ["AI_PROVIDER"] = "gemini"
os.environ.pop("AI_FALLBACK_PROVIDER", None)
os.environ["GEMINI_API_KEY"] = "test-gemini-key"

from api.main import app

client = TestClient(app)


def _sign(raw_body: bytes) -> dict[str, str]:
    digest = hmac.new(TEST_APP_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
    return {"X-Hub-Signature-256": f"sha256={digest}"}


def test_root_and_health():
    res = client.get("/")
    assert res.status_code == 200
    assert res.json()["status"] == "online"

    res_h = client.get("/health")
    assert res_h.status_code == 200
    assert res_h.json()["status"] == "healthy"


def test_webhook_verification_success():
    params = {
        "hub.mode": "subscribe",
        "hub.verify_token": "test_secret_verify_token_123",
        "hub.challenge": "challenge_code_987654",
    }
    response = client.get("/webhook", params=params)
    assert response.status_code == 200
    assert response.text == "challenge_code_987654"


def test_webhook_verification_invalid_token():
    params = {
        "hub.mode": "subscribe",
        "hub.verify_token": "wrong_token",
        "hub.challenge": "challenge_code_987654",
    }
    response = client.get("/webhook", params=params)
    assert response.status_code == 403


def test_webhook_post_rejects_invalid_signature():
    payload = {"object": "page", "entry": []}
    raw = json.dumps(payload).encode()
    response = client.post(
        "/webhook", content=raw, headers={"X-Hub-Signature-256": "sha256=deadbeef"}
    )
    assert response.status_code == 403


def test_webhook_post_rejects_missing_signature():
    payload = {"object": "page", "entry": []}
    raw = json.dumps(payload).encode()
    response = client.post("/webhook", content=raw)
    assert response.status_code == 403


def test_webhook_post_message_received():
    payload = {
        "object": "page",
        "entry": [
            {
                "id": "123456789",
                "time": 1710000000,
                "messaging": [
                    {
                        "sender": {"id": "test_parent_user_1"},
                        "recipient": {"id": "page_id_1"},
                        "timestamp": 1710000000,
                        "message": {
                            "mid": "mid.123456789:abcdef",
                            "text": "وين مكان العيادة بالضبط؟",
                        },
                    }
                ],
            }
        ],
    }
    raw = json.dumps(payload).encode()

    # Mock messenger network call so test is 100% offline
    with patch("api.webhook.MessengerClient.send_text_message", new_callable=AsyncMock) as mock_send, \
         patch("api.webhook.MessengerClient.send_typing_indicator", new_callable=AsyncMock) as mock_type:
        mock_send.return_value = True
        mock_type.return_value = True

        response = client.post("/webhook", content=raw, headers=_sign(raw))
        assert response.status_code == 200
        assert response.json() == {"status": "EVENT_RECEIVED"}

        # Verify background task fired
        mock_type.assert_called_once_with("test_parent_user_1")
        mock_send.assert_called_once()
        args, _ = mock_send.call_args
        assert args[0] == "test_parent_user_1"
        assert "مجمع عيادات الرباط" in args[1]
