"""
Tests for Layer-3 conversation memory in PediatricianAIAssistant.

These exercise the warm/cold history logic without making any network calls.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.ai_engine import PediatricianAIAssistant
from core.database import AssistantDatabase


@pytest.fixture
def bot(monkeypatch, tmp_path):
    # A dummy key is enough: provider construction is lazy and offline.
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.delenv("AI_FALLBACK_PROVIDER", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    assistant = PediatricianAIAssistant()
    assistant.db = AssistantDatabase(tmp_path / "test.db")
    assistant._histories.clear()
    return assistant


def test_history_rebuilt_from_db(bot):
    uid = "u1"
    bot.db.save_message(uid, "user", "وين العيادة")
    bot.db.save_message(uid, "model", "في تاجوراء")
    bot._histories.clear()

    assert bot._get_history(uid) == [
        {"role": "user", "text": "وين العيادة"},
        {"role": "assistant", "text": "في تاجوراء"},
    ]


def test_history_is_cached_in_memory(bot):
    uid = "u2"
    bot._histories[uid] = [{"role": "user", "text": "cached"}]
    bot.db.save_message(uid, "user", "from-db")

    # A warm entry wins; the DB is not consulted again.
    assert bot._get_history(uid) == [{"role": "user", "text": "cached"}]


def test_reset_clears_memory_and_db(bot):
    uid = "u3"
    bot.db.save_message(uid, "user", "hi")
    bot._histories[uid] = [{"role": "user", "text": "hi"}]

    bot.reset_conversation(uid)

    assert uid not in bot._histories
    assert bot.db.get_recent_history(uid) == []
