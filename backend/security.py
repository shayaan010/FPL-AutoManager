"""
Password hashing, session tokens, and encryption for stored FPL tokens.

An FPL access token grants full control of someone's team, so tokens are
encrypted at rest rather than stored raw -- a leaked database dump alone
shouldn't hand over anyone's squad.
"""
from __future__ import annotations

import base64
import hashlib
import logging
import os
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError
from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger("security")

_hasher = PasswordHasher()

SESSION_COOKIE = "fpl_session"
SESSION_TTL_SECONDS = 60 * 60 * 24 * 30  # 30 days

APP_SECRET_KEY = os.environ.get("APP_SECRET_KEY", "")

if not APP_SECRET_KEY:
    # Dev convenience only: without a stable key, stored tokens become
    # unreadable on every restart, so warn loudly rather than fail silently.
    APP_SECRET_KEY = "dev-insecure-key-set-APP_SECRET_KEY-in-production"
    logger.warning(
        "APP_SECRET_KEY is not set -- using an insecure development key. "
        "Set APP_SECRET_KEY in production or stored FPL tokens will be readable."
    )

# Fernet needs a 32-byte urlsafe-base64 key; derive one from whatever secret
# was provided so operators can use any random string.
_fernet = Fernet(base64.urlsafe_b64encode(hashlib.sha256(APP_SECRET_KEY.encode()).digest()))


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        _hasher.verify(password_hash, password)
        return True
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return False


def new_session_id() -> str:
    return secrets.token_urlsafe(32)


def encrypt(plaintext: str) -> str:
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str | None:
    """Returns None when the value can't be decrypted (e.g. the key changed)."""
    try:
        return _fernet.decrypt(ciphertext.encode()).decode()
    except (InvalidToken, ValueError):
        return None
