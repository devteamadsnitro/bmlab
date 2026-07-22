import html
import logging
import os

import httpx

logger = logging.getLogger(__name__)

RESEND_API_KEY = os.getenv("RESEND_API_KEY")
MAIL_FROM = os.getenv("MAIL_FROM", "onboarding@resend.dev")


async def send_ticket_resolved_email(to_email: str, client_name: str, ticket_code: str) -> bool:
    """Returns True if Resend accepted the email for delivery."""
    if not RESEND_API_KEY:
        logger.warning("RESEND_API_KEY not configured; skipping resolved email for %s", ticket_code)
        return False

    subject = f"Tu ticket {ticket_code} ha sido resuelto"
    body_html = (
        f"<p>Hola {html.escape(client_name)},</p>"
        f"<p>Tu ticket <strong>{html.escape(ticket_code)}</strong> ha sido marcado como resuelto por el equipo.</p>"
        f"<p>Si el problema persiste, por favor abre una nueva incidencia.</p>"
    )

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
                json={"from": MAIL_FROM, "to": [to_email], "subject": subject, "html": body_html},
            )
        if resp.status_code >= 400:
            logger.error("Resend send failed for %s: %s %s", ticket_code, resp.status_code, resp.text)
            return False
        return True
    except httpx.HTTPError as exc:
        logger.error("Resend send error for %s: %s", ticket_code, exc)
        return False
