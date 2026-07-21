import os

from cryptography.fernet import Fernet
from itsdangerous import BadSignature, URLSafeSerializer

_fernet = Fernet(os.environ["PASSWORD_ENCRYPTION_KEY"])
_ticket_action_serializer = URLSafeSerializer(
    os.getenv("SESSION_SECRET", "dev-secret-change-me"), salt="ticket-advance"
)


def encrypt_password(raw: str) -> str:
    return _fernet.encrypt(raw.encode()).decode()


def decrypt_password(encrypted: str) -> str:
    return _fernet.decrypt(encrypted.encode()).decode()


def verify_password(raw: str, encrypted: str) -> bool:
    return decrypt_password(encrypted) == raw


def make_advance_token(ticket_id: int) -> str:
    return _ticket_action_serializer.dumps({"ticket_id": ticket_id})


def verify_advance_token(token: str) -> int | None:
    try:
        data = _ticket_action_serializer.loads(token)
    except BadSignature:
        return None
    return data.get("ticket_id")
