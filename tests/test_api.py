"""
Integration tests for FastAPI Webhook endpoints using TestClient.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, r"c:\antigravity learning")

from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

# Ensure test verify token is configured
os.environ["META_VERIFY_TOKEN"] = "test_secret_verify_token_123"

from api.main import app

client = TestClient(app)


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

    # Mock messenger network call so test is 100% offline
    with patch("api.webhook.MessengerClient.send_text_message", new_callable=AsyncMock) as mock_send, \
         patch("api.webhook.MessengerClient.send_typing_indicator", new_callable=AsyncMock) as mock_type:
        mock_send.return_value = True
        mock_type.return_value = True

        response = client.post("/webhook", json=payload)
        assert response.status_code == 200
        assert response.json() == {"status": "EVENT_RECEIVED"}

        # Verify background task fired
        mock_type.assert_called_once_with("test_parent_user_1")
        mock_send.assert_called_once()
        args, _ = mock_send.call_args
        assert args[0] == "test_parent_user_1"
        assert "مجمع عيادات الرباط" in args[1]
