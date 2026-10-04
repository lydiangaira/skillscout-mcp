import argparse
import os
import time
from pathlib import Path

import jwt

from auth import AUDIENCE, ISSUER, TOOL_SCOPES

PRIVATE_KEY = Path(os.environ.get("SKILLSCOUT_PRIVATE_KEY_FILE", Path(__file__).parent / "keys" / "private.pem"))

p = argparse.ArgumentParser()
p.add_argument("--sub", default="dev-user")
p.add_argument("--scope", default=" ".join(TOOL_SCOPES.values()), help="space separated scopes")
p.add_argument("--minutes", type=int, default=15)
a = p.parse_args()

if not PRIVATE_KEY.exists():
    raise SystemExit("No private key found. Create the keys with openssl first (see README).")

now = int(time.time())
print(jwt.encode(
    {"iss": ISSUER, "aud": AUDIENCE, "sub": a.sub, "scope": a.scope, "iat": now, "exp": now + a.minutes * 60},
    PRIVATE_KEY.read_text(), algorithm="RS256",
))