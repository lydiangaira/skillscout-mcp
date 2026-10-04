"""Runs SkillScout over HTTP with a token check, scope check and rate limit on every request."""
import json
import logging
import os

import uvicorn
from mcp.server.transport_security import TransportSecuritySettings

from auth import AuthError, RateLimiter, TOOL_SCOPES, load_public_key, verify_token
from server import mcp

MAX_BODY = 64 * 1024  # 64 KB is plenty for a tool call
log = logging.getLogger("skillscout.audit")


async def _reply(send, status: int, code: str, extra_headers=()):
    key = "status" if status == 200 else "error"
    body = json.dumps({key: code}).encode()
    headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()), *extra_headers]
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


def _requested_tools(payload) -> list[str | None]:
    """Names of every tool a JSON-RPC payload tries to call (batches included)."""
    messages = payload if isinstance(payload, list) else [payload]
    names = []
    for m in messages:
        if isinstance(m, dict) and m.get("method") == "tools/call":
            params = m.get("params")
            names.append(params.get("name") if isinstance(params, dict) else None)
    return names


class AuthMiddleware:
    def __init__(self, app, limiter: RateLimiter):
        self.app, self.limiter = app, limiter

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Health check for hosting platforms. No token needed, and it reveals nothing.
        if scope["path"] == "/health" and scope["method"] == "GET":
            return await _reply(send, 200, "ok")

        headers = dict(scope["headers"])
        auth = headers.get(b"authorization", b"").decode("latin-1")
        challenge = lambda extra="": [(b"www-authenticate", f'Bearer realm="skillscout"{extra}'.encode())]

        # 1. Authentication: a valid token on every request
        if not auth[:7].lower() == "bearer ":
            log.warning("deny reason=missing_token")
            return await _reply(send, 401, "missing_token", challenge())
        try:
            user, scopes = verify_token(auth[7:].strip())
        except AuthError as exc:
            log.warning("deny reason=%s detail=%s", exc.code, exc.detail)
            return await _reply(send, 401, exc.code, challenge(', error="invalid_token"'))

        # 2. Rate limit per user
        if not self.limiter.allow(user):
            log.warning("deny user=%s reason=rate_limited", user)
            return await _reply(send, 429, "rate_limited", [(b"retry-after", b"60")])

        # 3. Read a bounded body so we can see which tool is being called
        body, more = b"", True
        while more:
            msg = await receive()
            if msg["type"] != "http.request":
                return
            body += msg.get("body", b"")
            more = msg.get("more_body", False)
            if len(body) > MAX_BODY:
                log.warning("deny user=%s reason=body_too_large", user)
                return await _reply(send, 413, "request_too_large")

        # 4. Authorization: the scope must match the tool
        tools = []
        if body:
            try:
                tools = _requested_tools(json.loads(body))
            except (ValueError, RecursionError):
                return await _reply(send, 400, "invalid_json")
        for name in tools:
            needed = TOOL_SCOPES.get(name)
            if needed is None or needed not in scopes:
                log.warning("deny user=%s tool=%s reason=insufficient_scope", user, name)
                extra = f', error="insufficient_scope", scope="{needed}"' if needed else ""
                return await _reply(send, 403, "insufficient_scope", challenge(extra))
        log.info("allow user=%s method=%s tools=%s", user, scope["method"], tools)

        # 5. Pass the request on, replaying the body we consumed
        sent = False

        async def replay():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, replay, send)


def build_app(max_requests: int = 60):
    load_public_key()  # refuse to start without a valid RSA public key

    # The SDK rejects unknown Host headers. When hosted, name the public host explicitly,
    # for example SKILLSCOUT_PUBLIC_HOST=skillscout.onrender.com
    public_host = os.environ.get("SKILLSCOUT_PUBLIC_HOST", "").strip()
    hosts, origins = ["127.0.0.1:*", "localhost:*"], ["http://127.0.0.1:*", "http://localhost:*"]
    if public_host:
        hosts.append(public_host)
        origins.append(f"https://{public_host}")
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True, allowed_hosts=hosts, allowed_origins=origins,
    )

    app = mcp.streamable_http_app(
        stateless_http=True,       # every request stands alone, so every request is checked
        json_response=True,
        max_request_body_size=MAX_BODY,
        transport_security=security,
    )
    app.add_middleware(AuthMiddleware, limiter=RateLimiter(max_requests))
    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    uvicorn.run(
        build_app(),
        host=os.environ.get("SKILLSCOUT_HOST", "127.0.0.1"),  # hosting platforms need 0.0.0.0
        port=int(os.environ.get("PORT", "8000")),             # hosting platforms provide PORT
    )