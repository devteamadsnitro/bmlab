import logging
import os

import httpx

logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


async def send_ticket_notification(ticket) -> None:
    if not BOT_TOKEN or not CHAT_ID:
        logger.info("Telegram not configured; skipping notification for %s", ticket.code)
        return

    text = (
        f"🚨 Nueva incidencia {ticket.code}\n"
        f"Cliente: {ticket.client_name}\n"
        f"Activo: {ticket.asset_label} ({ticket.asset_external_id})"
    )
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json={"chat_id": CHAT_ID, "text": text})
            resp.raise_for_status()
    except httpx.HTTPError:
        logger.exception("Failed to send Telegram notification for %s", ticket.code)
