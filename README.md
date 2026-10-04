# SkillScout MCP

SkillScout is a small Model Context Protocol (MCP) server that lets an AI assistant explore skill demand in job postings. An assistant can ask which jobs need a skill, which companies hire the most, and open the full details of one posting.

It is built with the official MCP Python SDK and is built to show three things: tools a model can pick correctly, input validation that gives helpful errors, and a security design for exposing it to outside clients. It runs locally over stdio, and it can also run over HTTP with a token check, scope check and rate limit on every request.

## Tools

| Tool | What it does | Inputs |
|---|---|---|
| `search_postings_by_skill` | Finds postings that require a skill and returns short summaries, so the model gets a compact answer instead of full job descriptions. | `skill` (required), `location` (optional), `level` (optional), `limit` (1 to 25, default 10) |
| `count_postings_by_company` | Counts postings per company and returns the companies with the most postings, optionally for one skill. | `skill` (optional), `top_n` (1 to 20, default 10) |
| `get_posting` | Returns the full details of one posting, including a trimmed summary and the link, using an `id` from a search result. | `posting_id` (required) |

## Input validation

Every tool checks its input and returns an error message the model can act on to retry:

- Skills are trimmed and lowercased. Empty or very long values are rejected.
- An unknown skill returns close matches, for example `No postings mention the skill 'pyhton'. Did you mean: python, phyton, cpython?`
- An unknown level returns the list of valid levels read from the data.
- `limit`, `top_n` and `posting_id` are range checked, so a model cannot request an unbounded amount of data.

Note: in the real dataset some postings have an empty job level, so a `level` filter skips those postings.

## Proof it works

MCP Inspector calling the tools:

![Inspector counting postings by company](docs/inspector-count.png)

![Inspector showing a helpful validation error](docs/inspector-error.png)

## Run it

```bash
uv venv env && source env/bin/activate
uv pip install "mcp[cli]" pydantic pandas pytest cryptography
python -m pytest -q          # tests run against the bundled sample data
python demo_client.py        # calls the tools like a real MCP client
npx @modelcontextprotocol/inspector python server.py   # explore in the Inspector
```

To run it over HTTP with authentication, first create a dev RSA key pair (once):

```bash
mkdir -p keys
openssl genrsa -out keys/private.pem 3072
openssl rsa -in keys/private.pem -pubout -out keys/public.pem
chmod 600 keys/private.pem
```

`keys/` is git-ignored. The private key must never be committed or shared. The server only reads the public key, and `make_token.py` (standing in for an authorization server) uses the private key to sign tokens.

```bash
python http_server.py                       # listens on 127.0.0.1:8000/mcp
TOKEN=$(python make_token.py --scope "postings:search")   # short-lived dev token
curl -s -H "Authorization: Bearer $TOKEN" \
     -H "Accept: application/json, text/event-stream" -H "Content-Type: application/json" \
     -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' http://127.0.0.1:8000/mcp
```

The server uses the first data source it finds: the `SKILLSCOUT_DATA` environment variable, then `data/raw/postings.csv`, then the bundled synthetic sample `data/sample_postings.csv`.

## Data and attribution

SkillScout is designed for the "LinkedIn Software Engineering Jobs Dataset" by asaniczka on Kaggle, which is licensed under the Open Data Commons Attribution License (ODC-By 1.0): https://opendatacommons.org/licenses/by/1-0/

This repository does not include that dataset. It includes a small synthetic sample (`data/sample_postings.csv`) in the same format so everything runs out of the box. To use the real data, download `postings.csv` from Kaggle and place it in `data/raw/`.

## Security review

This server has no SQL layer. Data is loaded from a CSV into memory and filtered with pandas, so there is no query string to inject into. The checks below cover the risks that do apply.

| Risk | How it is handled |
|---|---|
| Injection through tool arguments | Arguments are never used to build SQL, shell commands, file paths or code. Text filters use plain substring matching (`regex=False`), so input cannot become a regular expression. |
| Oversized or abusive input | Skills must be 2 to 50 characters, locations at most 100, numbers are range checked, and results are capped at 25 postings or 20 companies. HTTP request bodies are capped at 64 KB. |
| Unauthenticated access over HTTP | Every request needs a valid bearer token. The server accepts only RS256, requires `exp`, `iss`, `aud` and `sub`, and rejects expired, forged, tampered, wrong-audience, `alg: none` and HS256 key-confusion tokens. |
| Over-broad access | Each tool needs its own scope. A tool with no scope assigned is denied, and a batch request cannot smuggle in a tool the token does not allow. |
| Scraping and floods | Requests are rate limited per user (60 per minute by default). |
| Untrusted text reaching the model | Posting text comes from third parties and could contain instructions aimed at the model. Control characters are stripped, summaries are trimmed, and results carry a notice telling the model to treat the text as data. This reduces the risk but cannot remove it. |
| Keys and secrets | The server holds only the public key, so a compromised server cannot forge tokens. It refuses to start without an RSA public key of at least 2048 bits. The private key is created with owner-only permissions, is git-ignored and is never committed. |
| Traceability | Every allow and deny decision is logged with the user and tool, never the token itself. |

Tests for all of this are in `tests/test_security.py`.

**Known limits.** In the demo, `make_token.py` plays the authorization server and signs with a local private key. A real deployment would use an actual authorization server and have this server fetch its public keys from a JWKS endpoint, which also allows key rotation. Stdio mode has no authentication, because it trusts the local process that launches it. The rate limiter is in memory, so it resets on restart and does not work across several server instances.

## Securing the server with OAuth 2.0 (design plan)

The HTTP mode described above implements RS256 token verification, the scope check and the rate limit using a locally signed demo token. This section describes the full OAuth 2.0 design I would use in production, where a real authorization server issues the tokens. The MCP specification's authorization rules for HTTP transport are built on OAuth 2.1 and are still changing, so I would check the current spec version before implementing.

**Roles.** SkillScout acts as the OAuth resource server. A separate authorization server (for example Keycloak or Auth0) authenticates users and issues tokens. SkillScout never handles passwords.

**Flow.** I would use the authorization code flow with PKCE (S256). AI assistants are public clients that cannot keep a client secret, and PKCE protects the code from being stolen and reused.

**Where tokens are checked.** On every HTTP request, inside the server, before any tool runs:

1. Reject requests without a bearer token using `401` and a `WWW-Authenticate` header that points to the authorization server.
2. Verify the token signature against the authorization server's public keys (JWKS), then check `exp`, the issuer (`iss`) and that the audience (`aud`) is this server's own URL, so tokens issued for other services are refused.
3. Read the scopes from the token and compare them with the scope the requested tool needs. If one is missing, return `403`.

**Scopes.**

| Scope | What it allows | Tools it unlocks |
|---|---|---|
| `postings:search` | Lets a client search postings and see short summaries. | `search_postings_by_skill` |
| `postings:read` | Lets a client open the full details of a single posting. | `get_posting` |
| `postings:aggregate` | Lets a client see company-level counts without seeing individual postings. | `count_postings_by_company` |

Splitting the scopes applies least privilege: a client can be given aggregate counts without ever seeing individual postings.

**Token lifetime.** Access tokens would last about 15 minutes. Refresh tokens would be rotated on every use and revocable, so a leaked token stops working quickly.

**Access control per user.** Every request is tied to a user through the token's `sub` claim. Any per-user or per-customer data restriction is applied in the data layer using that identity, never from a tool argument, because a model can be tricked into passing someone else's identifier.

**Misuse and reliability.**

- Rate limiting per user, plus the existing result caps (25 postings, 20 companies), to make bulk scraping impractical.
- An audit log of user, tool, arguments and time for every call.
- Secrets live in environment variables and are never committed. The server never forwards a client's token to another service.
- Text inside postings (such as `job_summary`) is untrusted content. A malicious posting could contain instructions aimed at the model, so summaries are trimmed, and a production version would label them clearly as data in tool results.

## Next steps

- Replace the demo key pair with an authorization server and verify tokens against its public keys (JWKS), with key rotation.
- Add the authorization code flow with PKCE on the client side.
- Add a small Rust program that reads the same dataset.