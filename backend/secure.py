"""Encrypts Plaid access tokens at rest.

The encryption key lives in Windows Credential Manager (via keyring).
If keyring is not available, it falls back to data/.key (less safe, logged).
"""
import logging
from cryptography.fernet import Fernet

from db import DATA

log = logging.getLogger("secure")
SERVICE = "ScottsFinanceApp"
USER = "token-key"


def _load_key() -> bytes:
    try:
        import keyring
        k = keyring.get_password(SERVICE, USER)
        if not k:
            k = Fernet.generate_key().decode()
            keyring.set_password(SERVICE, USER, k)
        return k.encode()
    except Exception as e:  # keyring backend missing
        log.warning("keyring unavailable (%s), using data/.key file", e)
        path = DATA / ".key"
        if not path.exists():
            path.write_bytes(Fernet.generate_key())
        return path.read_bytes()


_f = Fernet(_load_key())


def encrypt(text: str) -> str:
    return _f.encrypt(text.encode()).decode()


def decrypt(token: str) -> str:
    return _f.decrypt(token.encode()).decode()
