"""
Tests for the Layer-2/Layer-3 quality improvements:

- Libya time helpers (core/timeutil.py)
- Today-aware working-hours reply (zero-token)
- New approved FAQs (services, walk-in)
- Live "now" context + prompt hardening in the system instruction

All tests are offline (no network, no real API keys).
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core import intent_router as intent_router_module
from core.ai_engine import PediatricianAIAssistant
from core.database import AssistantDatabase
from core.timeutil import (
    LIBYA_TZ,
    is_closed_value,
    ordered_weekday_keys,
    weekday_ar,
    weekday_key,
)

# 2026-10-13 is a Tuesday (Libya, UTC+2).
TUESDAY = datetime(2026, 10, 13, 12, 0, tzinfo=LIBYA_TZ)
SUNDAY = datetime(2026, 10, 11, 12, 0, tzinfo=LIBYA_TZ)


# --------------------------------------------------------------------------- #
# Time helpers
# --------------------------------------------------------------------------- #
def test_time_helpers_map_days_correctly():
    assert weekday_key(TUESDAY) == "tuesday"
    assert weekday_ar(TUESDAY) == "الثلاثاء"
    assert weekday_key(SUNDAY) == "sunday"
    assert LIBYA_TZ.utcoffset(None).total_seconds() == 2 * 3600


def test_weekday_keys_are_monday_first():
    keys = ordered_weekday_keys()
    assert keys[0] == "monday"
    assert keys[6] == "sunday"
    assert len(keys) == 7


def test_is_closed_value():
    assert is_closed_value("مغلق / غير متواجد")
    assert is_closed_value(None)
    assert not is_closed_value("طوال اليوم (24 ساعة)")
    assert not is_closed_value("مساءً")


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture
def bot(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.delenv("AI_FALLBACK_PROVIDER", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    assistant = PediatricianAIAssistant()
    assistant.db = AssistantDatabase(tmp_path / "test.db")
    assistant.router = intent_router_module.IntentRouter(assistant.db)
    assistant._histories.clear()
    return assistant


# --------------------------------------------------------------------------- #
# Today-aware working hours (zero-token)
# --------------------------------------------------------------------------- #
def test_hours_reply_states_today_open(bot, monkeypatch):
    monkeypatch.setattr(intent_router_module, "libya_now", lambda: TUESDAY)
    reply = bot.router._hours_reply()
    assert "توا يوم الثلاثاء، والدكتور متواجد" in reply
    assert "مواعيد د. رواد شحيمة" in reply


def test_hours_reply_states_closed_and_next_open(bot, monkeypatch):
    monkeypatch.setattr(intent_router_module, "libya_now", lambda: SUNDAY)
    reply = bot.router._hours_reply()
    assert "توا يوم الأحد العيادة مغلقة" in reply
    assert "أقرب دوام" in reply
    assert "الثلاثاء" in reply  # next open day after Sunday


def test_hours_route_is_zero_token(bot, monkeypatch):
    monkeypatch.setattr(intent_router_module, "libya_now", lambda: TUESDAY)
    result = bot.router.route("امتى تفتحوا؟")
    assert result.matched is True
    assert result.tokens_consumed == 0
    # The hours FAQ is answered live (today-aware), not with a static string.
    assert "توا يوم الثلاثاء، والدكتور متواجد" in result.direct_reply


# --------------------------------------------------------------------------- #
# New approved FAQs
# --------------------------------------------------------------------------- #
def test_services_faq_is_answered_zero_token(bot):
    result = bot.router.route("شنو الخدمات اللي تقدمونها؟")
    assert result.matched is True
    assert result.tokens_consumed == 0
    assert "متابعة حديثي الولادة" in result.direct_reply


def test_walk_in_faq_is_answered_zero_token(bot):
    result = bot.router.route("نقدر نجي بدون موعد؟")
    assert result.matched is True
    assert result.tokens_consumed == 0
    assert "بدون موعد" in result.direct_reply


# --------------------------------------------------------------------------- #
# Prompt quality
# --------------------------------------------------------------------------- #
def test_system_instruction_hardening(bot):
    instruction = bot.system_instruction
    assert "NEVER say you are a bot" in instruction
    assert "never ask again" in instruction


def test_dynamic_context_has_live_time(bot):
    context = bot._system_instruction_with_context()
    assert "CURRENT DATE & TIME" in context
    assert "Africa/Tripoli" in context
    # The injected block is appended to the base instruction.
    assert bot.system_instruction in context
