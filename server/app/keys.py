import hashlib
import secrets

KEY_PREFIX = "lf_sk_"  # marks the project secret for secret scanners and for humans reading a bundle


def new_api_key() -> str:
    return KEY_PREFIX + secrets.token_urlsafe(24)


def hash_api_key(key: str) -> str:
    """Keys carry 24 random bytes, so an unsalted digest is enough; only the digest reaches the database."""
    return hashlib.sha256(key.encode()).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_matches(given: str | None, expected: str | None) -> bool:
    if not given or not expected:
        return False
    return secrets.compare_digest(given.encode("utf-8", "surrogateescape"), expected.encode())
