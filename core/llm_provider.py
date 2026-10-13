"""
Pluggable LLM providers for Layer 3 of the assistant.

Supports Anthropic Claude and Google Gemini behind one small interface, so the
assistant can switch (or fall back) between engines without touching the
safety filter (Layer 1) or the zero-token intent router (Layer 2).

Security notes:
    - API keys are read from environment variables ONLY. They are never
      hard-coded, and never written to logs or error messages.
    - Configuring a provider is explicit via `AI_PROVIDER` / `AI_FALLBACK_PROVIDER`.

Environment variables:
    AI_PROVIDER            auto | claude | gemini   (default: auto)
                           auto = Claude when ANTHROPIC_API_KEY is set, else Gemini
    AI_FALLBACK_PROVIDER   optional second engine (e.g. gemini)
    ANTHROPIC_API_KEY      required when Claude is used
    CLAUDE_MODEL           default: claude-sonnet-5-5
    CLAUDE_FALLBACK_MODEL  default: claude-haiku-5-5
    CLAUDE_EFFORT          low | medium | high | xhigh | max (default: low)
    GEMINI_API_KEY         required when Gemini is used
    GEMINI_MODEL           default: gemini-3.5-flash
    GEMINI_FALLBACK_MODEL  default: gemini-flash-latest
"""

from __future__ import annotations

import logging
import os
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)

# Neutral chat message shared by every provider: role is "user" | "assistant".
Message = dict[str, str]

DEFAULT_PROVIDER = "auto"
DEFAULT_CLAUDE_MODEL = "claude-sonnet-5-5"
DEFAULT_CLAUDE_FALLBACK_MODEL = "claude-haiku-5-5"
DEFAULT_CLAUDE_EFFORT = "low"
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash"
DEFAULT_GEMINI_FALLBACK_MODEL = "gemini-flash-latest"

DEFAULT_TEMPERATURE = 0.4
DEFAULT_MAX_OUTPUT_TOKENS = 2048
DEFAULT_TIMEOUT_S = 20.0


def _is_configured(value: str | None) -> bool:
    """True when an env value looks like a real secret (not empty/placeholder)."""
    if not value:
        return False
    v = value.strip()
    return bool(v) and not v.startswith("your_")


@runtime_checkable
class LLMProvider(Protocol):
    """Minimal contract every engine must satisfy."""

    name: str

    def generate(
        self,
        system_instruction: str,
        history: list[Message],
        user_message: str,
    ) -> str | None:
        """Return the reply text, or None if this provider failed."""
        ...


# --------------------------------------------------------------------------- #
# Anthropic Claude
# --------------------------------------------------------------------------- #
class ClaudeProvider:
    name = "claude"

    def __init__(
        self,
        api_key: str,
        model: str,
        fallback_model: str | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        max_retries: int = 2,
        effort: str | None = None,
    ) -> None:
        import anthropic  # imported lazily so Gemini-only setups need no SDK

        self._anthropic = anthropic
        self.model = model
        self.fallback_model = (
            fallback_model if fallback_model and fallback_model != model else None
        )
        self.effort = effort
        self._client = anthropic.Anthropic(
            api_key=api_key,
            timeout=timeout_s,
            max_retries=max_retries,
        )

        # The Messages API changed over SDK generations: older versions accept
        # `temperature`, newer ones replaced it with `output_config.effort`.
        # Detect what this installed SDK supports so we never send a bad kwarg.
        import inspect

        params = inspect.signature(self._client.messages.create).parameters
        self._supports_temperature = "temperature" in params
        self._supports_output_config = "output_config" in params

    @staticmethod
    def _to_messages(history: list[Message], user_message: str) -> list[dict[str, str]]:
        """Convert neutral history into Anthropic's messages format.

        Anthropic requires the first message to be from the user and strictly
        alternating roles, so we normalise before sending.
        """
        raw: list[dict[str, str]] = [
            {
                "role": "assistant" if m.get("role") == "assistant" else "user",
                "content": str(m.get("text", "")),
            }
            for m in history
        ]
        raw.append({"role": "user", "content": user_message})

        cleaned: list[dict[str, str]] = []
        for msg in raw:
            if not msg["content"]:
                continue
            if cleaned and cleaned[-1]["role"] == msg["role"]:
                cleaned[-1]["content"] += "\n" + msg["content"]
            else:
                cleaned.append(dict(msg))
        while cleaned and cleaned[0]["role"] != "user":
            cleaned.pop(0)
        if not cleaned:  # defensive: never send an empty conversation
            cleaned = [{"role": "user", "content": user_message or "."}]
        return cleaned

    def generate(
        self,
        system_instruction: str,
        history: list[Message],
        user_message: str,
    ) -> str | None:
        messages = self._to_messages(history, user_message)
        models = [self.model] + ([self.fallback_model] if self.fallback_model else [])

        for model in models:
            kwargs: dict = {
                "model": model,
                "max_tokens": DEFAULT_MAX_OUTPUT_TOKENS,
                "system": system_instruction,
                "messages": messages,
            }
            if self._supports_temperature:
                kwargs["temperature"] = DEFAULT_TEMPERATURE
            if self._supports_output_config and self.effort:
                kwargs["output_config"] = {"effort": self.effort}

            try:
                response = self._client.messages.create(**kwargs)
                text = "".join(
                    block.text
                    for block in response.content
                    if getattr(block, "type", None) == "text"
                ).strip()
                if text:
                    return text
                logger.warning("Claude model=%s returned an empty response.", model)
            except Exception as exc:  # noqa: BLE001 - log & try next model
                logger.warning(
                    "Claude model=%s failed: %s (%s)",
                    model,
                    type(exc).__name__,
                    exc,
                )
        return None


# --------------------------------------------------------------------------- #
# Google Gemini
# --------------------------------------------------------------------------- #
class GeminiProvider:
    name = "gemini"

    def __init__(
        self,
        api_key: str,
        model: str,
        fallback_model: str | None = None,
        timeout_ms: int = int(DEFAULT_TIMEOUT_S * 1000),
        max_attempts: int = 2,
    ) -> None:
        from google import genai
        from google.genai import types

        self._types = types
        self.model = model
        self.fallback_model = (
            fallback_model if fallback_model and fallback_model != model else None
        )
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=timeout_ms,
                retry_options=types.HttpRetryOptions(
                    attempts=max_attempts,
                    initial_delay=1.0,
                    max_delay=8.0,
                    http_status_codes=[429, 500, 502, 503, 504],
                ),
            ),
        )

    def _to_contents(self, history: list[Message], user_message: str) -> list:
        types = self._types
        contents = [
            types.Content(
                role="model" if m.get("role") == "assistant" else "user",
                parts=[types.Part(text=str(m.get("text", "")))],
            )
            for m in history
        ]
        contents.append(types.Content(role="user", parts=[types.Part(text=user_message)]))
        return contents

    def generate(
        self,
        system_instruction: str,
        history: list[Message],
        user_message: str,
    ) -> str | None:
        types = self._types
        contents = self._to_contents(history, user_message)
        models = [self.model] + ([self.fallback_model] if self.fallback_model else [])

        for model in models:
            try:
                config = types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=DEFAULT_TEMPERATURE,
                    max_output_tokens=DEFAULT_MAX_OUTPUT_TOKENS,
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(
                        disable=True
                    ),
                )
                response = self._client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=config,
                )
                text = (response.text or "").strip()
                if text:
                    return text
                logger.warning("Gemini model=%s returned an empty response.", model)
            except Exception as exc:  # noqa: BLE001 - log & try next model
                logger.warning(
                    "Gemini model=%s failed: %s (%s)",
                    model,
                    type(exc).__name__,
                    exc,
                )
        return None


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
class LLMEngine:
    """Tries each configured provider in order, returning the first real reply."""

    def __init__(self, providers: list[LLMProvider]) -> None:
        if not providers:
            raise RuntimeError(
                "No LLM provider is configured. Set ANTHROPIC_API_KEY (Claude) "
                "or GEMINI_API_KEY (Gemini) in your .env file."
            )
        self.providers = providers

    @property
    def primary_name(self) -> str:
        return self.providers[0].name

    @property
    def primary_label(self) -> str:
        model = getattr(self.providers[0], "model", "?")
        return f"{self.providers[0].name}:{model}"

    def generate(
        self,
        system_instruction: str,
        history: list[Message],
        user_message: str,
    ) -> str | None:
        for provider in self.providers:
            text = provider.generate(system_instruction, history, user_message)
            if text:
                return text
            logger.warning("Provider %s produced no reply; trying next.", provider.name)
        return None


def _make_provider(name: str, *, require: bool) -> LLMProvider | None:
    name = (name or "").strip().lower()

    if name == "claude":
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not _is_configured(api_key):
            if require:
                raise RuntimeError(
                    "ANTHROPIC_API_KEY is not set. Add it to .env to use Claude."
                )
            return None
        return ClaudeProvider(
            api_key=api_key.strip(),
            model=os.getenv("CLAUDE_MODEL", DEFAULT_CLAUDE_MODEL),
            fallback_model=os.getenv("CLAUDE_FALLBACK_MODEL", DEFAULT_CLAUDE_FALLBACK_MODEL),
            effort=os.getenv("CLAUDE_EFFORT", DEFAULT_CLAUDE_EFFORT),
        )

    if name == "gemini":
        api_key = os.getenv("GEMINI_API_KEY")
        if not _is_configured(api_key):
            if require:
                raise RuntimeError(
                    "GEMINI_API_KEY is not set. Add it to .env to use Gemini."
                )
            return None
        return GeminiProvider(
            api_key=api_key.strip(),
            model=os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL),
            fallback_model=os.getenv("GEMINI_FALLBACK_MODEL", DEFAULT_GEMINI_FALLBACK_MODEL),
        )

    raise ValueError(
        f"Unknown AI provider {name!r}. Expected 'claude' or 'gemini'."
    )


def build_llm_engine() -> LLMEngine:
    """Build the ordered provider chain from environment configuration."""
    primary_name = os.getenv("AI_PROVIDER", DEFAULT_PROVIDER).strip().lower() or DEFAULT_PROVIDER

    if primary_name == "auto":
        primary_name = "claude" if _is_configured(os.getenv("ANTHROPIC_API_KEY")) else "gemini"

    providers: list[LLMProvider] = []
    primary = _make_provider(primary_name, require=True)
    if primary is not None:
        providers.append(primary)

    fallback_name = os.getenv("AI_FALLBACK_PROVIDER", "").strip().lower()
    if fallback_name and fallback_name != primary_name:
        fallback = _make_provider(fallback_name, require=False)
        if fallback is not None:
            providers.append(fallback)

    return LLMEngine(providers)
