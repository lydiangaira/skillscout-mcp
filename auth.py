"""Token checking, scope rules and rate limiting for the HTTP version of SkillScout."""
import os
import time
from collections import defaultdict, deque
from functools import lru_cache
from pathlib import Path

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

ISSUER = os.environ.get("SKILLSCOUT_ISSUER", "https://auth.skillscout.local")
AUDIENCE = os.environ.get("SKILLSCOUT_AUDIENCE", "http://127.0.0.1:8000/mcp")
DEFAULT_PUBLIC_KEY = Path(__file__).parent / "keys" / "public.pem"

# Which scope each tool needs. A tool missing from this table is denied.
TOOL_SCOPES = {
    "search_postings_by_skill": "postings:search",
    "get_posting": "postings:read",
    "count_postings_by_company": "postings:aggregate",
}


class AuthError(Exception):
    def __init__(self, status: int, code: str, detail: str = ""):
        super().__init__(detail or code)
        self.status, self.code, self.detail = status, code, detail


def _parse_key(pem: bytes):
    key = serialization.load_pem_public_key(pem)
    if not isinstance(key, rsa.RSAPublicKey):
        raise RuntimeError("The public key must be an RSA key.")
    if key.key_size < 2048:
        raise RuntimeError("The RSA key must be at least 2048 bits.")
    return key


@lru_cache(maxsize=4)
def _load_key(source: str, is_pem: bool):
    if is_pem:
        return _parse_key(source.encode())
    key_file = Path(source)
    if not key_file.exists():
        raise RuntimeError(f"Public key not found at {key_file}. Create the keys with openssl first (see README).")
    return _parse_key(key_file.read_bytes())


def load_public_key():
    """The server only ever holds the PUBLIC key, so it can verify tokens but never create them.

    On a host with no key files, set SKILLSCOUT_PUBLIC_KEY_PEM to the contents of public.pem.
    """
    pem = os.environ.get("SKILLSCOUT_PUBLIC_KEY_PEM", "").replace("\\n", "\n").strip()
    if pem:
        return _load_key(pem, True)
    return _load_key(os.environ.get("SKILLSCOUT_PUBLIC_KEY_FILE", str(DEFAULT_PUBLIC_KEY)), False)


def verify_token(token: str) -> tuple[str, set[str]]:
    """Return (user id, scopes) or raise AuthError. Only RS256 is accepted."""
    try:
        claims = jwt.decode(
            token,
            load_public_key(),
            algorithms=["RS256"],  # fixed list blocks 'alg: none' and HS256 key-confusion attacks
            audience=AUDIENCE,
            issuer=ISSUER,
            options={"require": ["exp", "iss", "aud", "sub"]},
        )
    except jwt.ExpiredSignatureError:
        raise AuthError(401, "invalid_token", "token expired")
    except jwt.InvalidTokenError as exc:
        raise AuthError(401, "invalid_token", type(exc).__name__)
    return str(claims["sub"]), set(str(claims.get("scope", "")).split())


class RateLimiter:
    """Sliding window limit per user."""

    def __init__(self, max_requests: int = 60, window_seconds: int = 60):
        self.max, self.window = max_requests, window_seconds
        self.hits: dict[str, deque] = defaultdict(deque)

    def allow(self, user: str) -> bool:
        now = time.monotonic()
        q = self.hits[user]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.max:
            return False
        q.append(now)
        return True