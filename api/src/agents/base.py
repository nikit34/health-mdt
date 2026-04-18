"""Base Agent class — dual-backend LLM access.

Design:
- The system prompt (role + methodology) is stable.
- Each agent produces a JSON SOAP note plus a human-readable assessment.

Two backends are selected at runtime based on what's in `.env`:

1. `ANTHROPIC_API_KEY` → the raw `anthropic` SDK. Direct Messages API calls
   with `cache_control: ephemeral` for ~90% prompt-caching discount. Best
   for pay-per-use operators.

2. `CLAUDE_CODE_OAUTH_TOKEN` (no API key) → `claude-agent-sdk`, which spawns
   the `claude` CLI as a subprocess. Uses the user's Claude Pro/Max
   subscription — no separate API billing. The raw Messages API rejects
   Bearer/OAuth tokens ("OAuth authentication is currently not supported"),
   so this indirection is mandatory for subscription users.

API key wins when both are set (lower latency, explicit caching, cheaper when
you're already paying for it).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from tenacity import (
    RetryError,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from ..config import get_settings

log = logging.getLogger(__name__)


# --- Retry policy shared across both backends ---

def _is_retryable(exc: BaseException) -> bool:
    """Retry on transient errors only. Reach into anthropic SDK exceptions if
    that SDK is installed and in use; otherwise string-match on claude-agent-sdk
    process errors for rate-limit / timeout signals.
    """
    # Anthropic SDK path (only imported if available)
    try:
        from anthropic import (
            APIConnectionError,
            APIStatusError,
            APITimeoutError,
            RateLimitError,
        )
        if isinstance(exc, (RateLimitError, APITimeoutError, APIConnectionError)):
            return True
        if isinstance(exc, APIStatusError):
            status = getattr(exc, "status_code", 0) or 0
            return status >= 500 or status == 429
    except Exception:
        pass
    # claude-agent-sdk path — CLI errors are wrapped in RuntimeError/ProcessError
    msg = str(exc).lower()
    return any(s in msg for s in ("timeout", "rate limit", "429", "502", "503", "504"))


@dataclass
class AgentResponse:
    """Structured output from an agent call."""
    agent_name: str
    role: str
    soap: dict[str, str] = field(default_factory=dict)
    narrative: str = ""
    recommendations: list[dict] = field(default_factory=list)
    evidence_queries: list[str] = field(default_factory=list)
    evidence_pmids: list[str] = field(default_factory=list)
    confidence: float = 0.7
    safety_flags: list[str] = field(default_factory=list)
    payload: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict)


class Agent:
    """An LLM agent with a stable role + methodology prompt.

    Two transport paths; the choice is made at call time based on settings.
    """

    def __init__(
        self,
        *,
        name: str,
        role: str,
        system_prompt: str,
        model: str | None = None,
        max_tokens: int = 2000,
    ) -> None:
        self.name = name
        self.role = role
        self.system_prompt = system_prompt
        self._settings = get_settings()
        self.model = model or self._settings.agent_model
        self.max_tokens = max_tokens

    def clone(self, *, model: str | None = None, max_tokens: int | None = None) -> "Agent":
        return Agent(
            name=self.name,
            role=self.role,
            system_prompt=self.system_prompt,
            model=model or self.model,
            max_tokens=max_tokens or self.max_tokens,
        )

    def _full_system(self) -> str:
        """The full system prompt that both backends use."""
        return _METHODOLOGY_PREAMBLE + "\n\n" + self.system_prompt

    # --- Public API ---

    def run(self, user_payload: dict[str, Any]) -> AgentResponse:
        """Run the agent; returns structured AgentResponse."""
        user_message = _build_user_message(user_payload)
        log.info("Running agent %s (%s) via %s", self.name, self.role, self._settings.llm_auth_mode)
        try:
            text, raw = self._generate_with_retry(user_message)
        except RetryError as err:
            last = err.last_attempt.exception() if err.last_attempt else None
            raise RuntimeError(f"Agent {self.name} failed after retries: {last}") from last

        parsed = _safe_parse_json(text)
        return AgentResponse(
            agent_name=self.name,
            role=self.role,
            soap=parsed.get("soap", {}),
            narrative=parsed.get("narrative", ""),
            recommendations=parsed.get("recommendations", []),
            evidence_queries=parsed.get("evidence_queries", []),
            confidence=_safe_float(parsed.get("confidence"), 0.7),
            safety_flags=parsed.get("safety_flags", []),
            payload=parsed,
            raw=raw,
        )

    def stream(self, user_message: str, system_override: str | None = None) -> Iterator[str]:
        """Stream plain-text chunks (for the chat endpoint)."""
        system = system_override or self._full_system()
        if self._settings.anthropic_api_key:
            yield from self._stream_anthropic(user_message, system)
        else:
            yield from self._stream_claude_sdk(user_message, system)

    # --- Backend dispatch (non-streaming) ---

    @retry(
        retry=retry_if_exception(_is_retryable),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1.5, min=1, max=20),
        reraise=True,
    )
    def _generate_with_retry(self, user_message: str) -> tuple[str, dict]:
        """Dispatch to whichever backend is configured. Returns (text, raw_meta)."""
        if self._settings.anthropic_api_key:
            return self._generate_anthropic(user_message)
        if self._settings.claude_code_oauth_token:
            return self._generate_claude_sdk(user_message)
        raise RuntimeError(
            "No LLM credentials configured. Set ANTHROPIC_API_KEY (pay-per-use) "
            "or CLAUDE_CODE_OAUTH_TOKEN (Claude Pro/Max subscription) in .env."
        )

    # --- Backend: Anthropic SDK (api_key path, prompt-cached) ---

    def _generate_anthropic(self, user_message: str) -> tuple[str, dict]:
        from anthropic import Anthropic
        client = Anthropic(api_key=self._settings.anthropic_api_key)
        resp = client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=[
                {"type": "text", "text": _METHODOLOGY_PREAMBLE,
                 "cache_control": {"type": "ephemeral"}},
                {"type": "text", "text": self.system_prompt,
                 "cache_control": {"type": "ephemeral"}},
            ],
            messages=[{"role": "user", "content": user_message}],
        )
        text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
        raw = {
            "usage": {
                "input_tokens": resp.usage.input_tokens,
                "cached_input_tokens": getattr(resp.usage, "cache_read_input_tokens", 0),
                "output_tokens": resp.usage.output_tokens,
            },
            "stop_reason": resp.stop_reason,
            "model": resp.model,
            "backend": "anthropic",
        }
        return text, raw

    def _stream_anthropic(self, user_message: str, system: str) -> Iterator[str]:
        from anthropic import Anthropic
        client = Anthropic(api_key=self._settings.anthropic_api_key)
        with client.messages.stream(
            model=self.model,
            max_tokens=self.max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user_message}],
        ) as stream:
            for chunk in stream.text_stream:
                if chunk:
                    yield chunk

    # --- Backend: claude-agent-sdk (subscription path via Claude Code CLI) ---

    def _generate_claude_sdk(self, user_message: str) -> tuple[str, dict]:
        """Non-streaming bridge: asyncio.run() collects the full text output."""
        return asyncio.run(self._aclaude_collect(user_message))

    async def _aclaude_collect(self, user_message: str) -> tuple[str, dict]:
        from claude_agent_sdk import (
            AssistantMessage,
            ClaudeAgentOptions,
            ResultMessage,
            TextBlock,
            query,
        )
        options = ClaudeAgentOptions(
            system_prompt=self._full_system(),
            model=self.model,
            allowed_tools=[],  # pure text gen — no tools
            max_turns=1,
            setting_sources=[],  # don't read user's Claude Code settings
            env=self._subprocess_env(),
        )
        chunks: list[str] = []
        result_meta: dict = {}
        async for message in query(prompt=user_message, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        chunks.append(block.text)
            elif isinstance(message, ResultMessage):
                result_meta = {
                    "duration_ms": getattr(message, "duration_ms", 0),
                    "num_turns": getattr(message, "num_turns", 0),
                    "total_cost_usd": getattr(message, "total_cost_usd", 0.0),
                    "is_error": getattr(message, "is_error", False),
                }
        return "".join(chunks), {"backend": "claude_agent_sdk", "model": self.model, "result": result_meta}

    def _stream_claude_sdk(self, user_message: str, system: str) -> Iterator[str]:
        """Sync-iterator bridge over the async generator.

        A dedicated event loop runs on the same thread — each `next()` drives
        one step. Cleaner than threading for the SSE handler, which is already
        inside FastAPI's async context when it calls this.
        """
        async def agen():
            from claude_agent_sdk import (
                AssistantMessage,
                ClaudeAgentOptions,
                TextBlock,
                query,
            )
            options = ClaudeAgentOptions(
                system_prompt=system,
                model=self.model,
                allowed_tools=[],
                max_turns=1,
                setting_sources=[],
                env=self._subprocess_env(),
            )
            async for message in query(prompt=user_message, options=options):
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock) and block.text:
                            yield block.text

        loop = asyncio.new_event_loop()
        gen = agen()
        try:
            while True:
                try:
                    chunk = loop.run_until_complete(gen.__anext__())
                except StopAsyncIteration:
                    break
                yield chunk
        finally:
            try:
                loop.run_until_complete(gen.aclose())
            except Exception:
                pass
            loop.close()

    def _subprocess_env(self) -> dict[str, str]:
        """Env vars to pass into the `claude` CLI subprocess.

        The CLI reads CLAUDE_CODE_OAUTH_TOKEN for auth. We explicitly pass it
        (plus minimal PATH/HOME) so the subprocess gets exactly what it needs
        and nothing else — avoids leaking unrelated host env.
        """
        env = {
            "CLAUDE_CODE_OAUTH_TOKEN": self._settings.claude_code_oauth_token or "",
            "PATH": os.environ.get("PATH", "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"),
            "HOME": os.environ.get("HOME", "/app"),
        }
        if os.environ.get("ANTHROPIC_API_KEY"):
            # Some CLI versions prefer API key when both are present; unset it
            # so we stay on the subscription path deliberately chosen here.
            pass
        return env


# --- Shared helpers ---

def _build_user_message(user_payload: dict[str, Any]) -> str:
    return (
        "Ниже — структурированные данные пациента за релевантный период. "
        "Оцени их в рамках своей дисциплины и верни СТРОГО JSON по схеме, без markdown-обёрток.\n\n"
        "Схема:\n"
        "{\n"
        '  "soap": {"subjective": "...", "objective": "...", "assessment": "...", "plan": "..."},\n'
        '  "narrative": "2-4 предложения для GP-координатора",\n'
        '  "recommendations": [{"title": "...", "detail": "...", "priority": "urgent|normal|low", "due_days": 0}],\n'
        '  "evidence_queries": ["PubMed-запрос 1", "..."],\n'
        '  "confidence": 0.0-1.0,\n'
        '  "safety_flags": ["..."]\n'
        "}\n\n"
        "ПРАВИЛА:\n"
        "- Учитывай окна валидности лабораторных данных (CBC — 90 дней, липиды — 365 дней, "
        "гормоны — 180 дней, глюкоза/HbA1c — 120 дней). Если данные устарели, укажи это "
        "явно в assessment и снизь confidence.\n"
        "- Не выдавай рекомендации за пределами своей дисциплины.\n"
        "- safety_flags заполняй только при реальных триггерах, требующих внимания в пределах суток.\n\n"
        f"ДАННЫЕ:\n{json.dumps(user_payload, ensure_ascii=False, default=str, indent=2)}"
    )


def _safe_float(v, default: float) -> float:
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def _safe_parse_json(text: str) -> dict:
    """Extract the first JSON object from `text`, even if wrapped in fences."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.rstrip("`").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        log.warning("No JSON object in agent response: %s", text[:200])
        return {}
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError as e:
        log.warning("JSON parse error: %s; text=%s", e, text[:300])
        return {}


_METHODOLOGY_PREAMBLE = """# Операционные стандарты

Ты — часть мультидисциплинарной команды (MDT) в системе персонального health-ассистента.
Твои суждения агрегируются семейным врачом (GP-координатор) для синтеза.

## Принципы
1. **Доказательная медицина**: если у тебя нет убедительных данных — скажи об этом,
   не заполняй пробелы догадками.
2. **Клинические окна валидности**: старые анализы ≠ текущее состояние. Указывай дату
   забора и возраст данных явно.
3. **Scope discipline**: не выходи за рамки своей специальности. Пересечения — работа GP.
4. **SOAP-мышление**: Subjective (что рассказал пациент) → Objective (измеримое) →
   Assessment (твоё клиническое суждение) → Plan (что делать дальше).
5. **Safety net**: если видишь триггер, требующий действий < 24ч — укажи в safety_flags.
6. **Нет паники, нет преуменьшения**: тон спокойно-профессиональный.

## Что ты НЕ делаешь
- Не ставишь диагнозов (ты не в кабинете, данных недостаточно).
- Не назначаешь медикаменты.
- Не заменяешь визит к врачу — ты помогаешь пациенту быть информированным партнёром.

## Формат вывода
Строго JSON без markdown. GP-координатор парсит твой ответ программно.
"""
