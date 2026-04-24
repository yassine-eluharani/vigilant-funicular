"""Email notifications — Resend (primary) or SMTP (fallback).

Environment variables:
  RESEND_API_KEY   — Resend API key (preferred)
  SMTP_HOST        — SMTP server hostname
  SMTP_PORT        — SMTP port (default 587)
  SMTP_USER        — SMTP username
  SMTP_PASS        — SMTP password
  SMTP_FROM        — Sender address (default noreply@applypilot.app)

If neither is configured, send_email() is a no-op (logs a warning).
"""

from __future__ import annotations

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

log = logging.getLogger(__name__)


def send_email(to: str, subject: str, html: str, text: str | None = None) -> bool:
    """Send an email. Returns True on success, False on failure/not-configured."""
    resend_key = os.environ.get("RESEND_API_KEY", "")
    if resend_key:
        return _send_resend(resend_key, to, subject, html, text)

    smtp_host = os.environ.get("SMTP_HOST", "")
    if smtp_host:
        return _send_smtp(smtp_host, to, subject, html, text)

    log.debug("Email not configured — skipping notification to %s", to)
    return False


def _send_resend(api_key: str, to: str, subject: str, html: str, text: str | None) -> bool:
    try:
        import httpx
        from_addr = os.environ.get("SMTP_FROM", "noreply@applypilot.app")
        payload: dict = {"from": from_addr, "to": [to], "subject": subject, "html": html}
        if text:
            payload["text"] = text
        resp = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        log.error("Resend send failed: %s", e)
        return False


def _send_smtp(host: str, to: str, subject: str, html: str, text: str | None) -> bool:
    try:
        port = int(os.environ.get("SMTP_PORT", "587"))
        user = os.environ.get("SMTP_USER", "")
        password = os.environ.get("SMTP_PASS", "")
        from_addr = os.environ.get("SMTP_FROM", "noreply@applypilot.app")

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = to
        if text:
            msg.attach(MIMEText(text, "plain"))
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP(host, port) as server:
            server.ehlo()
            server.starttls()
            if user and password:
                server.login(user, password)
            server.sendmail(from_addr, [to], msg.as_string())
        return True
    except Exception as e:
        log.error("SMTP send failed: %s", e)
        return False


# ---------------------------------------------------------------------------
# High-score job digest
# ---------------------------------------------------------------------------

_MIN_NOTIFY_SCORE = 7


def notify_new_high_score_jobs(user_id: int, new_job_urls: list[str]) -> bool:
    """Send a digest email about newly scored high-matching jobs.

    Only sends if the user has email_notifications enabled and an email address.
    Returns True if email was sent.
    """
    if not new_job_urls:
        return False

    from applypilot.database import get_connection
    conn = get_connection()

    # Check opt-in and get email
    row = conn.execute(
        "SELECT email, email_notifications FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    if not row or not row["email_notifications"]:
        return False

    email = row["email"]

    # Fetch job details for the digest
    placeholders = ",".join("?" * len(new_job_urls))
    jobs = conn.execute(
        f"SELECT j.title, j.company, j.location, uj.fit_score "
        f"FROM jobs j JOIN user_jobs uj ON uj.job_url = j.url "
        f"WHERE uj.user_id = ? AND j.url IN ({placeholders}) "
        f"AND uj.fit_score >= ? "
        f"ORDER BY uj.fit_score DESC",
        [user_id, *new_job_urls, _MIN_NOTIFY_SCORE],
    ).fetchall()

    if not jobs:
        return False

    count = len(jobs)
    subject = f"{count} new high-match job{'s' if count > 1 else ''} on ApplyPilot"

    rows_html = "".join(
        f"<tr><td style='padding:8px 12px'>{j['title'] or '—'}</td>"
        f"<td style='padding:8px 12px'>{j['company'] or '—'}</td>"
        f"<td style='padding:8px 12px'>{j['location'] or '—'}</td>"
        f"<td style='padding:8px 12px;text-align:center'><strong>{j['fit_score']}/10</strong></td></tr>"
        for j in jobs
    )
    html = f"""
<html><body style="font-family:sans-serif;color:#1a1a1a;max-width:600px;margin:0 auto">
  <h2 style="margin-bottom:4px">New high-match jobs</h2>
  <p style="color:#666;margin-top:0">ApplyPilot found {count} new job{'s' if count > 1 else ''} that match your profile.</p>
  <table style="width:100%;border-collapse:collapse;border:1px solid #e5e7eb;border-radius:8px;overflow:hidden">
    <thead style="background:#f9fafb">
      <tr>
        <th style="padding:8px 12px;text-align:left">Title</th>
        <th style="padding:8px 12px;text-align:left">Company</th>
        <th style="padding:8px 12px;text-align:left">Location</th>
        <th style="padding:8px 12px;text-align:center">Score</th>
      </tr>
    </thead>
    <tbody>{rows_html}</tbody>
  </table>
  <p style="margin-top:24px">
    <a href="https://applypilot.app/jobs" style="background:#6366f1;color:#fff;padding:10px 20px;border-radius:6px;text-decoration:none;font-weight:600">
      View jobs →
    </a>
  </p>
  <p style="color:#999;font-size:12px;margin-top:32px">
    You're receiving this because you enabled email notifications in ApplyPilot.
    <a href="https://applypilot.app/profile" style="color:#999">Unsubscribe</a>
  </p>
</body></html>"""

    text = f"ApplyPilot: {count} new high-match job{'s' if count > 1 else ''}.\n\n" + "\n".join(
        f"- {j['title']} at {j['company']} ({j['fit_score']}/10)" for j in jobs
    )

    return send_email(email, subject, html, text)
