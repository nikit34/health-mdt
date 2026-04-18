"""Medical document processor — PDF / photo → structured extraction.

Dual backend like `agents/base.py`:
- With ANTHROPIC_API_KEY → direct vision call via the `anthropic` SDK
  (base64 image/document content blocks).
- With CLAUDE_CODE_OAUTH_TOKEN only → `claude-agent-sdk` with the `Read` tool
  enabled so the `claude` CLI can open the file by path. Slower (subprocess
  startup + extra round-trip where the agent calls Read) but doesn't need
  pay-per-use API access.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from datetime import date
from pathlib import Path

from pypdf import PdfReader
from sqlmodel import Session

from ..config import get_settings
from ..db import Document, LabResult, User

log = logging.getLogger(__name__)

EXTRACTION_PROMPT = """Ты извлекаешь структурированные данные из медицинского документа.

На вход — изображение или текст документа (анализы, выписка, заключение врача).
Верни СТРОГО JSON без markdown:

{
  "doc_type": "lab_results | prescription | discharge_summary | consultation | imaging | other",
  "date": "YYYY-MM-DD (если известно)",
  "patient_name": "... (если есть)",
  "clinic": "... (если есть)",
  "summary": "1-3 предложения о содержимом",
  "lab_panels": [
    {
      "panel": "cbc|cmp|lipids|thyroid|hba1c|vitamin_d|ferritin|b12|other",
      "analytes": [
        {"name": "hemoglobin", "value": 14.2, "unit": "g/dL", "ref_low": 13.0, "ref_high": 17.0, "flag": "L|H|null"}
      ]
    }
  ],
  "diagnoses": ["текст диагноза 1", "..."],
  "medications": [{"name": "...", "dose": "...", "frequency": "..."}],
  "notes": "прочие наблюдения (если есть)"
}

Правила:
- Если поле неизвестно — null (или пустой массив).
- Референсные интервалы, если указаны в документе, обязательно извлекай.
- Для каждого analyte используй стандартизированное англоязычное имя (hemoglobin, ldl_cholesterol, tsh, ...).
- doc_type определяй уверенно.
- ничего не выдумывай.
"""


def process_medical_document(
    session: Session,
    user: User,
    file_path: Path,
    original_filename: str,
    mime: str,
) -> Document:
    """Run vision/text extraction → persist Document + LabResults."""
    settings = get_settings()
    if not settings.has_llm:
        raise RuntimeError("LLM credentials required for document processing")

    doc = Document(
        user_id=user.id,
        filename=original_filename,
        path=str(file_path),
        mime=mime,
        status="pending",
    )
    session.add(doc)
    session.commit()
    session.refresh(doc)

    try:
        text_out = _extract(Path(file_path), mime)
        extracted = _safe_json(text_out)
        doc.extracted = extracted
        doc.summary = extracted.get("summary", "")
        doc.status = "processed"

        drawn_at = _parse_date(extracted.get("date")) or date.today()
        for panel_info in extracted.get("lab_panels", []) or []:
            panel_name = panel_info.get("panel", "other")
            for a in panel_info.get("analytes", []) or []:
                try:
                    value = float(a.get("value"))
                except (TypeError, ValueError):
                    continue
                session.add(LabResult(
                    user_id=user.id,
                    drawn_at=drawn_at,
                    panel=panel_name,
                    analyte=(a.get("name") or "").lower().strip(),
                    value=value,
                    unit=a.get("unit") or "",
                    ref_low=_to_float(a.get("ref_low")),
                    ref_high=_to_float(a.get("ref_high")),
                    flag=a.get("flag") or None,
                    source_document_id=doc.id,
                ))
        session.commit()
    except Exception as e:
        log.exception("Document processing failed: %s", e)
        doc.status = "failed"
        doc.summary = f"Ошибка обработки: {e}"
        session.commit()

    session.refresh(doc)
    return doc


# --- Backend dispatch ---

def _extract(path: Path, mime: str) -> str:
    settings = get_settings()
    if settings.anthropic_api_key:
        return _extract_anthropic(path, mime)
    if settings.claude_code_oauth_token:
        return _extract_claude_sdk(path, mime)
    raise RuntimeError("No LLM credentials configured")


# --- Anthropic SDK path (api_key) ---

def _extract_anthropic(path: Path, mime: str) -> str:
    """Direct vision call through the `anthropic` SDK."""
    from anthropic import Anthropic
    settings = get_settings()
    client = Anthropic(api_key=settings.anthropic_api_key)
    content = _build_anthropic_content(path, mime)
    resp = client.messages.create(
        model=settings.agent_model,
        max_tokens=3500,
        system=EXTRACTION_PROMPT,
        messages=[{"role": "user", "content": content}],
    )
    return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")


def _build_anthropic_content(path: Path, mime: str) -> list[dict]:
    """Return Anthropic message content for image, pdf, or text."""
    if mime.startswith("image/"):
        data = base64.standard_b64encode(path.read_bytes()).decode()
        return [
            {"type": "image", "source": {"type": "base64", "media_type": mime, "data": data}},
            {"type": "text", "text": "Извлеки структурированные данные из этого медицинского документа."},
        ]
    if mime == "application/pdf":
        # Try text extraction first; fall back to PDF-as-base64 if the text layer is weak
        text = ""
        try:
            reader = PdfReader(str(path))
            text = "\n\n".join((p.extract_text() or "") for p in reader.pages[:30])
        except Exception:
            pass
        if len(text.strip()) > 200:
            return [{"type": "text", "text": f"Документ (извлечённый текст):\n\n{text}"}]
        data = base64.standard_b64encode(path.read_bytes()).decode()
        return [
            {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": data}},
            {"type": "text", "text": "Извлеки структурированные данные из этого медицинского документа."},
        ]
    # Plain text fallback
    return [{"type": "text", "text": path.read_text(encoding="utf-8", errors="ignore")[:100000]}]


# --- claude-agent-sdk path (subscription) ---

def _extract_claude_sdk(path: Path, mime: str) -> str:
    """Run extraction through the `claude` CLI via claude-agent-sdk.

    The CLI doesn't accept base64 content blocks — instead we enable the Read
    tool and point it at the file path on disk. For PDFs with a good text
    layer we preflight `pypdf.extract_text` to avoid the extra Read roundtrip.
    """
    settings = get_settings()

    # Preflight PDF text extraction — if strong, feed text directly (no Read tool needed)
    if mime == "application/pdf":
        try:
            reader = PdfReader(str(path))
            text = "\n\n".join((p.extract_text() or "") for p in reader.pages[:30])
            if len(text.strip()) > 200:
                prompt = f"Документ (извлечённый текст):\n\n{text}\n\nИзвлеки структурированные данные."
                return asyncio.run(_aclaude_text_only(prompt, settings))
        except Exception:
            pass

    # Image or weak-text PDF — let claude Read the file from disk
    prompt = (
        "Открой файл `"
        + str(path)
        + "` через инструмент Read и извлеки из него структурированные данные "
        "медицинского документа по схеме из system prompt."
    )
    return asyncio.run(_aclaude_with_read(prompt, path, settings))


async def _aclaude_text_only(prompt: str, settings) -> str:
    from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, TextBlock, query

    options = ClaudeAgentOptions(
        system_prompt=EXTRACTION_PROMPT,
        model=settings.agent_model,
        allowed_tools=[],
        max_turns=1,
        setting_sources=[],
        env=_subprocess_env(settings),
    )
    chunks: list[str] = []
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    chunks.append(block.text)
    return "".join(chunks)


async def _aclaude_with_read(prompt: str, file_path: Path, settings) -> str:
    from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, TextBlock, query

    options = ClaudeAgentOptions(
        system_prompt=EXTRACTION_PROMPT,
        model=settings.agent_model,
        allowed_tools=["Read"],
        permission_mode="acceptEdits",  # auto-approve read-only ops
        cwd=str(file_path.parent),
        max_turns=3,  # give room for: think → Read → extract
        setting_sources=[],
        env=_subprocess_env(settings),
    )
    chunks: list[str] = []
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    chunks.append(block.text)
    return "".join(chunks)


def _subprocess_env(settings) -> dict[str, str]:
    return {
        "CLAUDE_CODE_OAUTH_TOKEN": settings.claude_code_oauth_token or "",
        "PATH": os.environ.get("PATH", "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"),
        "HOME": os.environ.get("HOME", "/app"),
    }


# --- Shared helpers ---

def _safe_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.rstrip("`").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        return {}
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return {}


def _parse_date(s) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except (TypeError, ValueError):
        return None


def _to_float(x) -> float | None:
    if x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None
