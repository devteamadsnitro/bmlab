import logging
import os

import httpx

logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


async def send_ticket_notification(ticket, cuenta: str, password: str) -> None:
    if not BOT_TOKEN or not CHAT_ID:
        logger.warning("Telegram not configured; skipping notification for %s", ticket.code)
        return

    text = (
        f"🚨 Nueva incidencia {ticket.code}\n"
        f"Cliente: {ticket.client_name}\n"
        f"Cuenta: {cuenta}\n"
        f"Pass: {password}\n"
        f"Activo: {ticket.asset_label} ({ticket.asset_external_id})"
    )
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json={"chat_id": CHAT_ID, "text": text})
        if resp.status_code != 200 or not resp.json().get("ok"):
            logger.error("Telegram send failed for %s: %s %s", ticket.code, resp.status_code, resp.text)
        else:
            logger.info("Telegram notification sent for %s", ticket.code)
    except httpx.HTTPError:
        logger.exception("Telegram request errored for %s", ticket.code)
