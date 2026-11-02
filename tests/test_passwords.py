import pytest

from app.security import passwords
from app.security.passwords import (
    ValidationError, hash_secret, validate_password, validate_pin, validate_username, verify_secret,
)

passwords.SCRYPT_N = 2 ** 4


def test_hash_and_verify():
    stored = hash_secret("secret123")
    assert stored.startswith("scrypt$")
    assert "secret123" not in stored
    assert verify_secret("secret123", stored)
    assert not verify_secret("secret124", stored)


def test_same_password_gets_different_salts():
    assert hash_secret("abcdef") != hash_secret("abcdef")


def test_urdu_passwords_work():
    stored = hash_secret("پاسورڈ١٢٣")
    assert verify_secret("پاسورڈ١٢٣", stored)


def test_old_hashes_keep_working_after_cost_change():
    stored = hash_secret("abcdef")
    passwords.SCRYPT_N = 2 ** 5
    try:
        assert verify_secret("abcdef", stored)  # parameters are read from the stored hash
    finally:
        passwords.SCRYPT_N = 2 ** 4


def test_malformed_hash_is_rejected_not_crashing():
    for bad in ("", "plain", "scrypt$x$y", "md5$1$2$3$4$5", "scrypt$16$8$1$@@$@@"):
        assert verify_secret("abcdef", bad) is False


def test_validators():
    with pytest.raises(ValidationError) as err:
        validate_password("abc")
    assert err.value.code == "error.password_short" and err.value.params == {"min": 6}
    assert validate_password("abcdef") == "abcdef"
    assert validate_username("  Ali.Khan ") == "ali.khan"
    for bad in ("ab", "has space", "x" * 33, "علی"):
        with pytest.raises(ValidationError):
            validate_username(bad)
    assert validate_pin("1234") == "1234"
    for bad in ("123", "123456789", "12a4", "١٢٣٤"):  # last one: Arabic-Indic digits are refused
        with pytest.raises(ValidationError):
            validate_pin(bad)
