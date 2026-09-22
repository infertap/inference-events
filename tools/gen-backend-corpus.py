#!/usr/bin/env python3
"""Backend identity vectors derived from the contract's UTF-8 HMAC construction."""
import hashlib
import hmac
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEY = b"infertap-conformance-test-key!!!"
CONTEXT = "infertap:backend-id:v1"
vectors = []
for raw, epoch in [("cache-a", 0), ("cache-b", 0), ("cache-a", 1), ("雪", 0), ("", 0)]:
    message = CONTEXT.encode() + b"\0" + epoch.to_bytes(4, "big") + b"\0" + raw.encode()
    vectors.append({"raw": raw, "epoch": epoch, "pseudonym": hmac.new(KEY, message, hashlib.sha256).digest()[:16].hex()})
(ROOT / "conformance/pseudonym/backend.json").write_text(json.dumps({"context": CONTEXT, "test_key_hex": KEY.hex(), "vectors": vectors}, indent=2) + "\n")
