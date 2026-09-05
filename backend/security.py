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
SESSION_TTL_SECONDS = 60 * 60 * 24 * 30  

APP_SECRET_KEY = os.environ.get("APP_SECRET_KEY", "")
_IS_PRODUCTION = (
    os.environ.get("ENVIRONMENT", "").lower() == "production"
    or os.environ.get("FRONTEND_ORIGIN", "").startswith("https://")
)

if not APP_SECRET_KEY:
    if _IS_PRODUCTION:
        raise RuntimeError(
            "APP_SECRET_KEY must be set in production. Generate one with: "
            "python -c \"import secrets; print(secrets.token_urlsafe(48))\""
        )
    APP_SECRET_KEY = "dev-insecure-key-set-APP_SECRET_KEY-in-production"
    logger.warning(
        "APP_SECRET_KEY is not set -- using an insecure development key. "
        "Set APP_SECRET_KEY in production or stored FPL tokens will be readable."
    )

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
    try:
        return _fernet.decrypt(ciphertext.encode()).decode()
    except (InvalidToken, ValueError):
        return None
