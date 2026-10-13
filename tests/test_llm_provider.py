"""
Unit tests for the pluggable LLM provider layer (no network calls).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core import llm_provider
from core.llm_provider import (
    ClaudeProvider,
    LLMEngine,
    build_llm_engine,
)

PROVIDER_ENV_KEYS = [
    "AI_PROVIDER",
    "AI_FALLBACK_PROVIDER",
    "ANTHROPIC_API_KEY",
    "CLAUDE_MODEL",
    "CLAUDE_FALLBACK_MODEL",
    "GEMINI_API_KEY",
    "GEMINI_MODEL",
    "GEMINI_FALLBACK_MODEL",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in PROVIDER_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    yield


def test_build_engine_requires_a_key():
    with pytest.raises(RuntimeError):
        build_llm_engine()


def test_claude_primary_with_gemini_fallback(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("AI_FALLBACK_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "gm-test")

    engine = build_llm_engine()
    assert [p.name for p in engine.providers] == ["claude", "gemini"]
    assert engine.primary_name == "claude"


def test_missing_primary_key_raises(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "claude")
    with pytest.raises(RuntimeError):
        build_llm_engine()


def test_auto_picks_gemini_without_claude_key(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "auto")
    monkeypatch.setenv("GEMINI_API_KEY", "gm-test")
    engine = build_llm_engine()
    assert engine.primary_name == "gemini"


def test_placeholder_key_is_not_treated_as_configured(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "your_anthropic_api_key_here")
    with pytest.raises(RuntimeError):
        build_llm_engine()


def test_claude_messages_are_normalised():
    # Leading assistant turn is dropped; consecutive same-role turns are merged.
    history = [
        {"role": "assistant", "text": "stale"},
        {"role": "user", "text": "مرحبا"},
        {"role": "user", "text": "كيف الحال"},
    ]
    messages = ClaudeProvider._to_messages(history, "عندي سؤال")

    assert messages[0]["role"] == "user"
    roles = [m["role"] for m in messages]
    assert all(a != b for a, b in zip(roles, roles[1:])), roles
    # The final message is a user turn ending with the new message.
    assert messages[-1]["role"] == "user"
    assert messages[-1]["content"].endswith("عندي سؤال")
    assert "كيف الحال" in messages[0]["content"]


class _FakeProvider:
    def __init__(self, name: str, reply: str | None):
        self.name = name
        self.reply = reply

    def generate(self, system_instruction, history, user_message):
        return self.reply


def test_engine_falls_through_to_next_provider():
    engine = LLMEngine([_FakeProvider("claude", None), _FakeProvider("gemini", "مرحبا")])
    assert engine.generate("sys", [], "hi") == "مرحبا"


def test_engine_returns_none_when_all_fail():
    engine = LLMEngine([_FakeProvider("claude", None), _FakeProvider("gemini", None)])
    assert engine.generate("sys", [], "hi") is None
