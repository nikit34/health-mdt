"""Base Agent class — wraps Anthropic SDK with prompt caching & structured output.

Design:
- The system prompt (role + methodology) is stable → cached for ~90% discount on re-reads.
- Each agent produces a JSON SOAP note plus a human-readable assessment.
- Agents can request PubMed evidence via a tool call before finalizing judgment.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from anthropic import (
    Anthropic,
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    RateLimitError,
)
from anthropic.types import MessageParam
from tenacity import (
    RetryError,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from ..config import anthropic_client_kwargs, get_settings

log = logging.getLogger(__name__)


def _is_retryable(exc: BaseException) -> bool:
    """Retry on transient errors only: rate limits, timeouts, 5xx, network blips.

    Do NOT retry 4xx bad-request errors — those won't fix themselves and cost money.
    """
    if isinstance(exc, (RateLimitError, APITimeoutError, APIConnectionError)):
        return True
    if isinstance(exc, APIStatusError):
        status = getattr(exc, "status_code", 0) or 0
        return status >= 500 or status == 429
    return False


@dataclass
class AgentResponse:
    """Structured output from an agent call."""
    agent_name: str
    role: str
    # SOAP structure — Subjective / Objective / Assessment / Plan
    soap: dict[str, str] = field(default_factory=dict)
    # Human-readable narrative (what the agent wants the GP to know)
    narrative: str = ""
    # Discrete recommendations the GP may convert to tasks
    recommendations: list[dict] = field(default_factory=list)
    # Clinically-significant patterns surfaced for PubMed grounding
    evidence_queries: list[str] = field(default_factory=list)
    # PubMed PMIDs that grounded this note (populated by orchestrator)
    evidence_pmids: list[str] = field(default_factory=list)
    # Confidence & safety
    confidence: float = 0.7
    safety_flags: list[str] = field(default_factory=list)
    # Full parsed JSON from the LLM — agents with custom schemas (GP) read from here
    payload: dict = field(default_factory=dict)
    # Raw LLM metadata — kept for debugging
    raw: dict = field(default_factory=dict)


class Agent:
    """An LLM agent with a stable role + methodology prompt.

    Agents are lightweight: just a name, role, and system prompt. The same
    Anthropic client is reused across all agents (passed in) so we benefit
    from connection reuse.
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
        """Return a new Agent with same prompt but tweaked model/tokens.

        Used for `kind='monthly'` MDT where GP synthesis uses Opus for deeper reasoning
        over longer windows without duplicating the system prompt.
        """
        return Agent(
            name=self.name,
            role=self.role,
            system_prompt=self.system_prompt,
            model=model or self.model,
            max_tokens=max_tokens or self.max_tokens,
        )

    def _client(self) -> Anthropic:
        """Build Anthropic client. Setup token wins over API key when both are set."""
        return Anthropic(**anthropic_client_kwargs(self._settings))

    def _cached_system(self) -> list[dict]:
        """System prompt as a list with cache_control — stable content is cached ~90% cheaper."""
        return [
            {
                "type": "text",
                "text": _METHODOLOGY_PREAMBLE,
                "cache_control": {"type": "ephemeral"},
            },
            {
                "type": "text",
                "text": self.system_prompt,
                "cache_control": {"type": "ephemeral"},
            },
        ]

    def run(self, user_payload: dict[str, Any]) -> AgentResponse:
        """Run the agent against the provided context bundle.

        `user_payload` is a dict containing the data the agent should reason over.
        We serialize as JSON and wrap in instructions asking for a SOAP JSON back.
        """
        client = self._client()
        user_message = (
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

        messages: list[MessageParam] = [{"role": "user", "content": user_message}]

        log.info("Running agent %s (%s)", self.name, self.role)
        try:
            resp = self._call_with_retry(client, messages)
        except RetryError as err:
            last = err.last_attempt.exception() if err.last_attempt else None
            raise RuntimeError(f"Agent {self.name} failed after retries: {last}") from last

        # Extract text content
        text = "".join(block.text for block in resp.content if block.type == "text")
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
            raw={
                "usage": {
                    "input_tokens": resp.usage.input_tokens,
                    "cached_input_tokens": getattr(resp.usage, "cache_read_input_tokens", 0),
                    "output_tokens": resp.usage.output_tokens,
                },
                "stop_reason": resp.stop_reason,
                "model": resp.model,
            },
        )

    @retry(
        retry=retry_if_exception(_is_retryable),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1.5, min=1, max=20),
        reraise=True,
    )
    def _call_with_retry(self, client: Anthropic, messages: list[MessageParam]):
        return client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=self._cached_system(),
            messages=messages,
        )

    def stream(self, user_message: str, system_override: str | None = None) -> Iterator[str]:
        """Stream a free-form response (plain text, not JSON).

        Used by the chat endpoint where we want progressive UI updates.
        The system prompt is still cached; output is streamed token by token.
        """
        client = self._client()
        system_blocks = (
            [{"type": "text", "text": system_override, "cache_control": {"type": "ephemeral"}}]
            if system_override
            else self._cached_system()
        )
        with client.messages.stream(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system_blocks,
            messages=[{"role": "user", "content": user_message}],
        ) as stream:
            for chunk in stream.text_stream:
                if chunk:
                    yield chunk


def _safe_float(v, default: float) -> float:
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def _safe_parse_json(text: str) -> dict:
    """Extract the first JSON object from `text`, even if wrapped in fences."""
    text = text.strip()
    # Strip common markdown fences
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.rstrip("`").strip()
    # Find first { and last }
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
