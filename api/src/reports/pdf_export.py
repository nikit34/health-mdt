"""PDF rendering of an MDT report — for handing to a real physician.

Design:
- Typography optimized for letterpaper / A4 with wide margins for doctor notes.
- Section order mirrors what a physician wants to scan: patient → problem list →
  GP synthesis → specialist notes → safety net → evidence → disclaimer.
- No emojis, no colors that obscure — print-friendly.
"""
from __future__ import annotations

from datetime import datetime
from io import BytesIO

from sqlmodel import Session, select

from ..db import MdtReport, PubmedEvidence, User


def render_mdt_pdf(session: Session, report: MdtReport) -> bytes:
    """Return PDF bytes for the given MDT report."""
    # Import weasyprint lazily so the module imports cleanly even without system deps
    from weasyprint import HTML  # type: ignore

    user = session.get(User, report.user_id)
    evidence = []
    if report.evidence_pmids:
        rows = session.exec(
            select(PubmedEvidence).where(PubmedEvidence.pmid.in_(report.evidence_pmids))
        ).all()
        seen = set()
        for e in rows:
            if not e.pmid or e.pmid in seen or e.title == "(no results)":
                continue
            seen.add(e.pmid)
            evidence.append(e)

    html = _render_html(report, user, evidence)
    buf = BytesIO()
    HTML(string=html).write_pdf(target=buf)
    return buf.getvalue()


def _render_html(report: MdtReport, user: User | None, evidence: list[PubmedEvidence]) -> str:
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    patient = _patient_block(user)
    problems = _problems_block(report.problem_list)
    specialists = _specialists_block(report.specialist_notes)
    safety = _safety_block(report.safety_net)
    ev = _evidence_block(evidence)

    return f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>MDT Report — {report.created_at.date().isoformat()}</title>
<style>
@page {{
  size: A4;
  margin: 18mm 15mm 20mm 15mm;
  @top-right {{
    content: "Consilium · стр. " counter(page) " из " counter(pages);
    font-size: 9pt;
    color: #777;
  }}
}}
body {{
  font-family: "Noto Sans", "DejaVu Sans", sans-serif;
  font-size: 10.5pt;
  color: #111;
  line-height: 1.45;
}}
h1 {{ font-size: 18pt; margin: 0 0 4pt 0; }}
h2 {{ font-size: 13pt; margin: 16pt 0 6pt 0; padding-bottom: 3pt; border-bottom: 1px solid #333; }}
h3 {{ font-size: 11pt; margin: 8pt 0 3pt 0; }}
.meta {{ color: #555; font-size: 9.5pt; margin-bottom: 12pt; }}
.synthesis {{ white-space: pre-wrap; }}
table {{ width: 100%; border-collapse: collapse; margin: 4pt 0; }}
th, td {{ text-align: left; padding: 4pt 6pt; vertical-align: top; border-bottom: 1px solid #ddd; font-size: 9.5pt; }}
th {{ font-weight: 600; background: #f3f3f3; }}
.pill {{
  display: inline-block; padding: 1pt 5pt; border-radius: 3pt;
  font-size: 8.5pt; font-weight: 600; text-transform: uppercase;
  border: 1px solid #999;
}}
.pill-active {{ background: #ffecec; border-color: #a33; color: #a33; }}
.pill-watchful {{ background: #fff7e1; border-color: #a77; color: #875; }}
.pill-resolved {{ background: #e7f6ea; border-color: #585; color: #375; }}
.safety {{
  border-left: 3pt solid #a33; background: #fff9f9;
  padding: 6pt 10pt; margin: 4pt 0;
}}
.specialist {{
  border: 1px solid #ddd; padding: 6pt 10pt; margin: 6pt 0;
  page-break-inside: avoid;
}}
.role {{ font-weight: 600; }}
.soap {{ font-size: 9pt; color: #444; margin-top: 4pt; }}
.soap span {{ text-transform: uppercase; font-weight: 600; color: #555; }}
.evidence li {{ margin-bottom: 4pt; font-size: 9.5pt; }}
.disclaimer {{
  margin-top: 22pt; padding-top: 8pt; border-top: 1px solid #aaa;
  font-size: 8.5pt; color: #555; font-style: italic;
}}
.patient {{ margin-bottom: 8pt; }}
.patient dt {{ float: left; width: 100pt; color: #555; }}
.patient dd {{ margin-left: 100pt; margin-bottom: 2pt; }}
</style>
</head>
<body>
<h1>MDT-отчёт</h1>
<div class="meta">
  Дата отчёта: {report.created_at.strftime('%Y-%m-%d %H:%M')}
  · Тип: {report.kind}
  · Сформирован: {now}
</div>

<h2>Пациент</h2>
{patient}

<h2>Синтез семейного врача</h2>
<div class="synthesis">{_escape(report.gp_synthesis) or '(нет данных)'}</div>

{problems}

{safety}

{specialists}

{ev}

<div class="disclaimer">
Отчёт сформирован автоматизированной системой Consilium на основе данных носимых устройств,
лабораторных результатов и чек-инов пациента. Выводы агентов следует рассматривать
как информационный вход для очной консультации — не как диагноз или назначение.
Референсные интервалы и клинические окна валидности указаны рядом с каждым значением
где применимо.
</div>
</body>
</html>
"""


def _patient_block(user: User | None) -> str:
    if not user:
        return "<div>—</div>"
    items = []
    if user.name:
        items.append(("Имя", user.name))
    if user.birthdate:
        from datetime import date
        today = date.today()
        age = today.year - user.birthdate.year - ((today.month, today.day) < (user.birthdate.month, user.birthdate.day))
        items.append(("Дата рождения", f"{user.birthdate.isoformat()} ({age} лет)"))
    if user.sex:
        items.append(("Пол", user.sex))
    if user.height_cm:
        items.append(("Рост", f"{user.height_cm:.0f} см"))
    if user.weight_kg:
        items.append(("Вес", f"{user.weight_kg:.1f} кг"))
    if user.context:
        items.append(("Контекст", user.context))
    rows = "".join(f"<dt>{_escape(k)}</dt><dd>{_escape(str(v))}</dd>" for k, v in items)
    return f'<dl class="patient">{rows}</dl>'


def _problems_block(problems: list[dict]) -> str:
    if not problems:
        return ""
    rows = []
    for p in problems:
        status = p.get("status", "active")
        rows.append(
            f"<tr>"
            f"<td><span class='pill pill-{status}'>{_escape(status)}</span></td>"
            f"<td>{_escape(p.get('problem', ''))}</td>"
            f"<td>{_escape(p.get('since', '') or '—')}</td>"
            f"<td>{_escape(p.get('note', '') or '—')}</td>"
            f"</tr>"
        )
    return (
        "<h2>Список проблем</h2>"
        "<table><thead><tr><th>Статус</th><th>Проблема</th><th>С</th><th>Комментарий</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def _safety_block(safety: list[str]) -> str:
    if not safety:
        return ""
    items = "".join(f"<div class='safety'>⚠ {_escape(s)}</div>" for s in safety)
    return f"<h2>Safety net — когда не ждать планового визита</h2>{items}"


def _specialists_block(specialist_notes: dict) -> str:
    if not specialist_notes:
        return ""
    blocks = []
    for name, note in specialist_notes.items():
        role = note.get("role", name)
        narrative = note.get("narrative", "")
        conf = note.get("confidence")
        soap = note.get("soap") or {}
        flags = note.get("safety_flags") or []

        soap_rows = []
        for key in ("subjective", "objective", "assessment", "plan"):
            if soap.get(key):
                soap_rows.append(
                    f"<div><span>{key}:</span> {_escape(soap[key])}</div>"
                )
        soap_html = f"<div class='soap'>{''.join(soap_rows)}</div>" if soap_rows else ""

        flags_html = ""
        if flags:
            chips = " ".join(f"<span class='pill pill-active'>⚠ {_escape(f)}</span>" for f in flags)
            flags_html = f"<div style='margin-top:4pt'>{chips}</div>"

        conf_str = f" · confidence {int(conf * 100)}%" if conf else ""
        blocks.append(
            f"<div class='specialist'>"
            f"<div class='role'>{_escape(role)}{conf_str}</div>"
            f"<div>{_escape(narrative) or '(no narrative)'}</div>"
            f"{soap_html}"
            f"{flags_html}"
            f"</div>"
        )
    return f"<h2>Ноты специалистов</h2>{''.join(blocks)}"


def _evidence_block(evidence: list[PubmedEvidence]) -> str:
    if not evidence:
        return ""
    items = []
    for e in evidence:
        authors = ", ".join(e.authors[:3]) if e.authors else ""
        if len(e.authors) > 3:
            authors += " et al."
        venue = f"<em>{_escape(e.journal)}</em>" if e.journal else ""
        year = f" ({e.pub_year})" if e.pub_year else ""
        url = f"https://pubmed.ncbi.nlm.nih.gov/{e.pmid}/" if e.pmid else ""
        items.append(
            f"<li><strong>{_escape(e.title)}</strong><br>"
            f"{_escape(authors)} · {venue}{year} · "
            f"<a href='{url}'>PMID {e.pmid}</a></li>"
        )
    return f"<h2>Доказательная база (PubMed)</h2><ul class='evidence'>{''.join(items)}</ul>"


def _escape(s: str | None) -> str:
    if not s:
        return ""
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
