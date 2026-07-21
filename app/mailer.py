import logging

logger = logging.getLogger(__name__)


async def send_ticket_resolved_email(to_email: str, client_name: str, ticket_code: str) -> None:
    logger.info(
        "Email sending not yet configured; would notify %s <%s> that ticket %s is resolved",
        client_name, to_email, ticket_code,
    )
