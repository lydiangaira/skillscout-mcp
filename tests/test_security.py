import os
import time
from pathlib import Path

os.environ["SKILLSCOUT_DATA"] = str(Path(__file__).parent.parent / "data" / "sample_postings.csv")

import base64  # noqa: E402
import hashlib  # noqa: E402
import hmac  # noqa: E402
import json  # noqa: E402
import tempfile  # noqa: E402

import jwt  # noqa: E402
import pytest  # noqa: E402
from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402


def _new_key(bits=2048):
    return rsa.generate_private_key(public_exponent=65537, key_size=bits)


def _private_pem(key):
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption())


def _public_pem(key):
    return key.public_key().public_bytes(serialization.Encoding.PEM,
                                         serialization.PublicFormat.SubjectPublicKeyInfo)


# The server is given only the public half of this pair. Tests sign with the private half.
TEST_KEY = _new_key()
_pub_file = Path(tempfile.mkdtemp()) / "public.pem"
_pub_file.write_bytes(_public_pem(TEST_KEY))
os.environ["SKILLSCOUT_PUBLIC_KEY_FILE"] = str(_pub_file)

import auth  # noqa: E402
import http_server  # noqa: E402

HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def token(scope="postings:search", key=None, **overrides):
    now = int(time.time())
    claims = {"iss": auth.ISSUER, "aud": auth.AUDIENCE, "sub": "alice", "scope": scope, "exp": now + 300}
    claims.update(overrides)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, _private_pem(key or TEST_KEY), algorithm="RS256")


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def call(tool, args=None):
    return {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": args or {}}}


@pytest.fixture
def client():
    with TestClient(http_server.build_app(max_requests=1000)) as c:
        yield c


def post(client, body, tok=None, **kw):
    headers = dict(HEADERS)
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    return client.post("/mcp", json=body, headers=headers, **kw)


# ---- authentication ----

def test_no_token_is_401(client):
    r = post(client, call("get_posting"))
    assert r.status_code == 401 and "www-authenticate" in r.headers


def test_garbage_token_is_401(client):
    assert post(client, call("get_posting"), "not-a-jwt").status_code == 401


def test_expired_token_is_401(client):
    assert post(client, call("get_posting"), token(exp=int(time.time()) - 10)).status_code == 401


def test_wrong_audience_is_401(client):
    assert post(client, call("get_posting"), token(aud="https://other-service")).status_code == 401


def test_wrong_issuer_is_401(client):
    assert post(client, call("get_posting"), token(iss="https://evil.example")).status_code == 401


def test_token_without_expiry_is_401(client):
    assert post(client, call("get_posting"), token(exp=None)).status_code == 401


def test_token_signed_with_other_key_is_401(client):
    attacker_key = _new_key()
    assert post(client, call("search_postings_by_skill"), token(key=attacker_key)).status_code == 401


def test_tampered_payload_is_401(client):
    header, _, signature = token().split(".")
    evil_payload = _b64(json.dumps({"iss": auth.ISSUER, "aud": auth.AUDIENCE, "sub": "alice",
                                    "scope": "postings:search postings:read postings:aggregate",
                                    "exp": int(time.time()) + 300}).encode())
    assert post(client, call("get_posting"), f"{header}.{evil_payload}.{signature}").status_code == 401


def test_alg_none_token_is_401(client):
    none_tok = jwt.encode({"iss": auth.ISSUER, "aud": auth.AUDIENCE, "sub": "x", "scope": "postings:search",
                           "exp": int(time.time()) + 300}, None, algorithm="none")
    assert post(client, call("search_postings_by_skill"), none_tok).status_code == 401


def test_hs256_key_confusion_attack_is_401(client):
    """Attacker signs an HS256 token using the PUBLIC key bytes as the HMAC secret."""
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64(json.dumps({"iss": auth.ISSUER, "aud": auth.AUDIENCE, "sub": "attacker",
                               "scope": "postings:search postings:read postings:aggregate",
                               "exp": int(time.time()) + 300}).encode())
    signing_input = f"{header}.{payload}".encode()
    sig = _b64(hmac.new(_public_pem(TEST_KEY), signing_input, hashlib.sha256).digest())
    assert post(client, call("get_posting"), f"{header}.{payload}.{sig}").status_code == 401


def test_server_refuses_a_weak_public_key(monkeypatch, tmp_path):
    weak = tmp_path / "weak.pem"
    weak.write_bytes(_public_pem(_new_key(1024)))
    monkeypatch.setenv("SKILLSCOUT_PUBLIC_KEY_FILE", str(weak))
    with pytest.raises(RuntimeError, match="2048"):
        auth.load_public_key()


def test_server_refuses_to_start_without_a_key(monkeypatch, tmp_path):
    monkeypatch.setenv("SKILLSCOUT_PUBLIC_KEY_FILE", str(tmp_path / "missing.pem"))
    with pytest.raises(RuntimeError, match="openssl"):
        http_server.build_app()


# ---- authorization ----

def test_missing_scope_is_403(client):
    r = post(client, call("count_postings_by_company"), token("postings:search"))
    assert r.status_code == 403


def test_unknown_tool_is_denied(client):
    assert post(client, call("drop_everything"), token("postings:search postings:read postings:aggregate")).status_code == 403


def test_batch_cannot_smuggle_a_forbidden_tool(client):
    batch = [call("search_postings_by_skill", {"skill": "python"}), call("count_postings_by_company")]
    assert post(client, batch, token("postings:search")).status_code == 403


def test_right_scope_passes_the_gate(client):
    r = post(client, call("search_postings_by_skill", {"skill": "python"}), token("postings:search"))
    assert r.status_code not in (401, 403, 429)


def test_listing_tools_needs_only_a_valid_token(client):
    r = post(client, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, token(""))
    assert r.status_code not in (401, 403)


# ---- abuse limits ----

def test_rate_limit_is_429():
    with TestClient(http_server.build_app(max_requests=3)) as c:
        codes = [post(c, {"jsonrpc": "2.0", "id": i, "method": "tools/list"}, token()).status_code for i in range(5)]
    assert codes[-1] == 429 and 429 not in codes[:3]


def test_oversized_body_is_rejected(client):
    big = call("search_postings_by_skill", {"skill": "x" * 200_000})
    assert post(client, big, token()).status_code == 413


def test_invalid_json_is_400(client):
    r = client.post("/mcp", content=b"{not json", headers={**HEADERS, "Authorization": f"Bearer {token()}"})
    assert r.status_code == 400


# ---- hosting ----

def test_health_check_needs_no_token(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_health_check_exposes_nothing_else(client):
    assert client.post("/health", json={}).status_code == 401  # only GET is public


def test_public_key_can_come_from_an_env_var(monkeypatch):
    monkeypatch.setenv("SKILLSCOUT_PUBLIC_KEY_FILE", "/does/not/exist.pem")
    monkeypatch.setenv("SKILLSCOUT_PUBLIC_KEY_PEM", _public_pem(TEST_KEY).decode().replace("\n", "\\n"))
    with TestClient(http_server.build_app()) as c:
        r = post(c, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, token())
    assert r.status_code not in (401, 403)


def test_unknown_public_host_is_refused_by_default():
    with TestClient(http_server.build_app(), base_url="https://skillscout.example.com") as c:
        r = post(c, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, token())
    assert r.status_code == 421


def test_named_public_host_is_accepted(monkeypatch):
    monkeypatch.setenv("SKILLSCOUT_PUBLIC_HOST", "skillscout.example.com")
    with TestClient(http_server.build_app(), base_url="https://skillscout.example.com") as c:
        r = post(c, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, token())
    assert r.status_code == 200