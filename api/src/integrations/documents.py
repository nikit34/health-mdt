"""Medical document processor — PDF / photo → structured extraction via Claude vision."""
from __future__ import annotations

import base64
import json
import logging
from datetime import date
from pathlib import Path

from anthropic import Anthropic
from pypdf import PdfReader
from sqlmodel import Session

from ..config import anthropic_client_kwargs, get_settings
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
        content = _build_content(file_path, mime)
        client = Anthropic(**anthropic_client_kwargs(settings))
        resp = client.messages.create(
            model=settings.agent_model,
            max_tokens=3500,
            system=EXTRACTION_PROMPT,
            messages=[{"role": "user", "content": content}],
        )
        text = "".join(b.text for b in resp.content if b.type == "text")
        extracted = _safe_json(text)
        doc.extracted = extracted
        doc.summary = extracted.get("summary", "")
        doc.status = "processed"

        # Persist lab values
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


def _build_content(path: Path, mime: str) -> list[dict]:
    """Return Anthropic message content for image or pdf/text."""
    path = Path(path)
    if mime.startswith("image/"):
        data = base64.standard_b64encode(path.read_bytes()).decode()
        return [
            {"type": "image", "source": {"type": "base64", "media_type": mime, "data": data}},
            {"type": "text", "text": "Извлеки структурированные данные из этого медицинского документа."},
        ]
    if mime == "application/pdf":
        # Try text extraction first; if weak, fall back to rendering pages
        text = ""
        try:
            reader = PdfReader(str(path))
            text = "\n\n".join((p.extract_text() or "") for p in reader.pages[:30])
        except Exception:
            pass
        if len(text.strip()) > 200:
            return [{"type": "text", "text": f"Документ (извлечённый текст):\n\n{text}"}]
        # Weak text → use PDF as base64 directly (Claude can read PDFs)
        data = base64.standard_b64encode(path.read_bytes()).decode()
        return [
            {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": data}},
            {"type": "text", "text": "Извлеки структурированные данные из этого медицинского документа."},
        ]
    # Plain text fallback
    return [{"type": "text", "text": path.read_text(encoding="utf-8", errors="ignore")[:100000]}]


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
