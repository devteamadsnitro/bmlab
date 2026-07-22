import logging

logger = logging.getLogger(__name__)


async def send_ticket_resolved_email(to_email: str, client_name: str, ticket_code: str) -> bool:
    """Returns True if the email was actually sent. Email delivery is not
    configured yet, so this always logs and returns False."""
    logger.info(
        "Email sending not yet configured; would notify %s <%s> that ticket %s is resolved",
        client_name, to_email, ticket_code,
    )
    return False
