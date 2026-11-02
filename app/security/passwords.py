"""Password and PIN hashing with scrypt (Python standard library, memory-hard).
Stored format: scrypt$N$r$p$salt_b64$hash_b64 -- parameters travel with the hash,
so they can be raised later without breaking existing accounts."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re

SCRYPT_N = 2 ** 14
SCRYPT_R = 8
SCRYPT_P = 1
MIN_PASSWORD_LENGTH = 6
_USERNAME = re.compile(r"^[a-z0-9_.-]{3,32}$")
_PIN = re.compile(r"^[0-9]{4,8}$")  # ASCII digits only


class ValidationError(ValueError):
    """Carries a translation key (`code`) and its parameters so the UI can localise it."""

    def __init__(self, code: str, **params: object) -> None:
        super().__init__(code)
        self.code = code
        self.params = params


def _derive(secret: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(secret.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=32,
                          maxmem=128 * n * r * 2 + 2 ** 20)


def hash_secret(secret: str) -> str:
    salt = os.urandom(16)
    digest = _derive(secret, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P)
    b64 = lambda raw: base64.b64encode(raw).decode("ascii")
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${b64(salt)}${b64(digest)}"


def verify_secret(secret: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, hash_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(hash_b64)
        actual = _derive(secret, base64.b64decode(salt_b64), int(n), int(r), int(p))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def validate_password(password: str) -> str:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValidationError("error.password_short", min=MIN_PASSWORD_LENGTH)
    return password


def validate_pin(pin: str) -> str:
    if not _PIN.match(pin):
        raise ValidationError("error.pin_invalid")
    return pin


def validate_username(username: str) -> str:
    cleaned = username.strip().lower()
    if not _USERNAME.match(cleaned):
        raise ValidationError("error.username_invalid")
    return cleaned
