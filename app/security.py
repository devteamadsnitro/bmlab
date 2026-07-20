import os

from cryptography.fernet import Fernet

_fernet = Fernet(os.environ["PASSWORD_ENCRYPTION_KEY"])


def encrypt_password(raw: str) -> str:
    return _fernet.encrypt(raw.encode()).decode()


def decrypt_password(encrypted: str) -> str:
    return _fernet.decrypt(encrypted.encode()).decode()


def verify_password(raw: str, encrypted: str) -> bool:
    return decrypt_password(encrypted) == raw
