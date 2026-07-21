import logging
import os

import httpx

from .security import make_advance_token

logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
BASE_URL = (
    f"https://{os.environ['RAILWAY_PUBLIC_DOMAIN']}"
    if os.getenv("RAILWAY_PUBLIC_DOMAIN")
    else "http://127.0.0.1:8000"
)


async def send_ticket_notification(ticket, items, cuenta: str, password: str) -> None:
    if not BOT_TOKEN or not CHAT_ID:
        logger.warning("Telegram not configured; skipping notification for %s", ticket.code)
        return

    advance_link = f"{BASE_URL}/t/advance/{make_advance_token(ticket.id)}"
    activos_text = "\n".join(f"• {item.label} ({item.external_id})" for item in items)
    text = (
        f"🚨 Nueva incidencia {ticket.code}\n"
        f"Cliente: {ticket.client_name}\n"
        f"Cuenta: {cuenta}\n"
        f"Pass: {password}\n"
        f"Activos:\n{activos_text}\n\n"
        f"👉 Marcar en proceso: {advance_link}"
    )
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                url,
                json={"chat_id": CHAT_ID, "text": text, "disable_web_page_preview": True},
            )
        if resp.status_code != 200 or not resp.json().get("ok"):
            logger.error("Telegram send failed for %s: %s %s", ticket.code, resp.status_code, resp.text)
        else:
            logger.info("Telegram notification sent for %s", ticket.code)
    except httpx.HTTPError:
        logger.exception("Telegram request errored for %s", ticket.code)
