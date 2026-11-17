import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.core.config import get_settings

_hasher = PasswordHasher()  # Argon2id with library-recommended parameters
# Constant dummy hash so unknown-user logins take the same time as wrong-password logins.
_DUMMY_HASH = _hasher.hash("dummy-password-for-timing")

MIN_PASSWORD_LENGTH = 12


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(stored_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(stored_hash or _DUMMY_HASH, password) and stored_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(stored_hash: str) -> bool:
    return _hasher.check_needs_rehash(stored_hash)


def new_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def token_hash(token: str) -> str:
    """Tokens are high-entropy, so a fast hash is appropriate; only hashes are stored."""
    return hashlib.sha256(token.encode()).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


class SecretBox:
    """Symmetric encryption for secrets at rest (MFA seeds now, integration tokens later).
    ENCRYPTION_KEYS is a comma-separated list; first key encrypts, all decrypt (rotation)."""

    def __init__(self, keys: list[str]) -> None:
        if not keys:
            raise RuntimeError("ENCRYPTION_KEYS is not configured")
        self._f = MultiFernet([Fernet(k.encode()) for k in keys])

    def encrypt(self, plaintext: str) -> str:
        return self._f.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        try:
            return self._f.decrypt(ciphertext.encode()).decode()
        except InvalidToken as exc:
            raise RuntimeError("Unable to decrypt secret (wrong or rotated-out key)") from exc

    def rotate(self, ciphertext: str) -> str:
        return self._f.rotate(ciphertext.encode()).decode()


def secret_box() -> SecretBox:
    keys = [k.strip() for k in get_settings().encryption_keys.split(",") if k.strip()]
    return SecretBox(keys)
