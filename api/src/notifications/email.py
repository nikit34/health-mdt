"""Email notifications via SMTP.

Sends brief/MDT summaries to the user's notification email.
Uses standard smtplib — no external dependencies.
"""
from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from ..config import get_settings
from ..db import User

log = logging.getLogger(__name__)


def send_email_to_user(
    user: User,
    *,
    subject: str,
    body_text: str,
    body_html: str = "",
) -> bool:
    """Send email to the user. Returns True on success."""
    settings = get_settings()
    if not settings.has_smtp or not user.email_notifications:
        return False

    to_addr = user.notification_email or user.email
    if not to_addr:
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from
    msg["To"] = to_addr

    msg.attach(MIMEText(body_text, "plain", "utf-8"))
    if body_html:
        msg.attach(MIMEText(body_html, "html", "utf-8"))

    try:
        if settings.smtp_tls:
            server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15)
            server.starttls()
        else:
            server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15)

        if settings.smtp_user:
            server.login(settings.smtp_user, settings.smtp_pass)

        server.sendmail(settings.smtp_from, [to_addr], msg.as_string())
        server.quit()
        log.info("Email sent to %s: %s", to_addr, subject)
        return True
    except Exception as e:
        log.warning("Email send failed to %s: %s", to_addr, e)
        return False


def format_brief_email(brief_text: str, highlights: list[str], for_date: str) -> tuple[str, str]:
    """Return (plain_text, html) for a daily brief email."""
    plain = f"Утренний бриф на {for_date}\n\n{brief_text}"
    if highlights:
        plain += "\n\nФокусы дня:\n" + "\n".join(f"• {h}" for h in highlights)

    html = f"""<div style="font-family: -apple-system, sans-serif; max-width: 600px; margin: 0 auto; color: #222;">
<h2 style="color: #333; border-bottom: 1px solid #ddd; padding-bottom: 8px;">
Утренний бриф — {for_date}
</h2>
<p style="line-height: 1.6; white-space: pre-wrap;">{_escape(brief_text)}</p>"""
    if highlights:
        html += '<ul style="color: #555;">'
        for h in highlights:
            html += f"<li>{_escape(h)}</li>"
        html += "</ul>"
    html += """<hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
<p style="font-size: 12px; color: #888;">Consilium · Информационный инструмент, не заменяет врача.</p>
</div>"""
    return plain, html


def format_mdt_email(gp_synthesis: str, problems: list[dict], safety_net: list[str], kind: str) -> tuple[str, str]:
    """Return (plain_text, html) for an MDT report email."""
    plain = f"MDT-отчёт ({kind})\n\n{gp_synthesis}"
    if problems:
        plain += "\n\nСписок проблем:\n"
        for p in problems:
            plain += f"• [{p.get('status', '')}] {p.get('problem', '')}\n"
    if safety_net:
        plain += "\nSafety net:\n"
        for s in safety_net:
            plain += f"⚠ {s}\n"

    html = f"""<div style="font-family: -apple-system, sans-serif; max-width: 600px; margin: 0 auto; color: #222;">
<h2 style="color: #333; border-bottom: 1px solid #ddd; padding-bottom: 8px;">
MDT-отчёт ({kind})
</h2>
<p style="line-height: 1.6; white-space: pre-wrap;">{_escape(gp_synthesis)}</p>"""
    if problems:
        html += '<h3 style="color: #444;">Список проблем</h3><ul>'
        for p in problems:
            status = p.get("status", "")
            html += f"<li><strong>[{_escape(status)}]</strong> {_escape(p.get('problem', ''))}</li>"
        html += "</ul>"
    if safety_net:
        html += '<h3 style="color: #a33;">Safety net</h3>'
        for s in safety_net:
            html += f'<div style="border-left: 3px solid #a33; padding: 6px 12px; margin: 4px 0; background: #fff9f9;">⚠ {_escape(s)}</div>'
    html += """<hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
<p style="font-size: 12px; color: #888;">Consilium · Информационный инструмент, не заменяет врача.</p>
</div>"""
    return plain, html


def _escape(s: str | None) -> str:
    if not s:
        return ""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
