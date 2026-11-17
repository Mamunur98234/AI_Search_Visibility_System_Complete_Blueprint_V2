import pytest
from cryptography.fernet import Fernet

from app.core.ids import uuid7
from app.core.security import SecretBox, hash_password, verify_password
from app.schemas import normalize_hostname
from app.services.audit import _clean


def test_uuid7_is_versioned_and_sortable() -> None:
    ids = [uuid7() for _ in range(200)]
    assert all(i.version == 7 and i.variant == "specified in RFC 4122" for i in ids)
    assert len(set(ids)) == 200


@pytest.mark.parametrize("good,expected", [("Example.COM", "example.com"), ("a.b.example.", "a.b.example")])
def test_hostname_ok(good: str, expected: str) -> None:
    assert normalize_hostname(good) == expected


@pytest.mark.parametrize("bad", ["", "example", "http://x.example", "[::1]", "10.0.0.1", "x..example", "a_b.example",
                                 "x.123"])
def test_hostname_rejected(bad: str) -> None:
    with pytest.raises(ValueError):
        normalize_hostname(bad)


def test_password_hashing() -> None:
    h = hash_password("a long passphrase")
    assert h.startswith("$argon2id$")
    assert verify_password(h, "a long passphrase")
    assert not verify_password(h, "wrong")
    assert not verify_password(None, "anything")


def test_secret_box_rotation() -> None:
    old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    ct = SecretBox([old]).encrypt("seed")
    rotated_box = SecretBox([new, old])
    assert rotated_box.decrypt(ct) == "seed"
    ct2 = rotated_box.rotate(ct)
    assert SecretBox([new]).decrypt(ct2) == "seed"
    with pytest.raises(RuntimeError):
        SecretBox([new]).decrypt(ct)


def test_audit_redaction() -> None:
    out = _clean({"name": "x", "password": "p", "api_token": "t", "nested": {"client_secret": "s"}})
    assert out == {"name": "x", "password": "[redacted]", "api_token": "[redacted]",
                   "nested": {"client_secret": "[redacted]"}}
