#!/usr/bin/env python3
"""Independent SHA-256 content-chain and HMAC pseudonym conformance vectors."""
import hashlib, hmac, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEY = b"infertap-conformance-test-key!!!"
TAG = b"infertap:content-key:v2\0"
CONTEXT = b"infertap:content-id:v2"


def chain(parent, tokens, extras):
    b = (
        TAG
        + parent.to_bytes(16, "big")
        + len(tokens).to_bytes(4, "big")
        + b"".join(t.to_bytes(4, "big") for t in tokens)
    )
    if extras is None:
        b += b"\0"
    else:
        b += b"\1" + len(extras).to_bytes(4, "big")
        for text in extras:
            text = text.encode()
            b += len(text).to_bytes(4, "big") + text
    return int.from_bytes(hashlib.sha256(b).digest()[:16], "big")


def pseudonym(raw, epoch):
    return (
        hmac.new(
            KEY,
            CONTEXT
            + b"\0"
            + epoch.to_bytes(4, "big")
            + b"\0"
            + raw.to_bytes(16, "big"),
            hashlib.sha256,
        )
        .digest()[:16]
        .hex()
    )


def main():
    p = ROOT / "conformance/pseudonym/vectors.json"
    doc = json.loads(p.read_text())
    for v in doc["vectors"]:
        if v["context"].startswith("infertap:content-id:"):
            v["context"] = CONTEXT.decode()
            v["raw_id"] = str(v["raw_id"])
            v["pseudonym"] = pseudonym(int(v["raw_id"]), v["epoch"])
    doc["construction"] = (
        "HMAC-SHA256(key, context||0x00||epoch:u32-be||0x00||raw_id)[:16] hex; engine IDs use 8-byte big endian, content IDs use 16-byte big endian"
    )
    doc["construction_note"] = (
        "Engine and content identities use separate contexts and fixed input widths. Content construction v2 retains 128 bits."
    )
    p.write_text(json.dumps(doc, indent=1) + "\n")
    cases = []
    for parent, tokens, extras in [
        (0, [], None),
        (0, [1, 2, 3], None),
        (0, [1, 2, 3], []),
        (0, [1, 2, 3], ["tenant-a"]),
        (2**100 + 7, [4294967295, 0], ["雪"]),
    ]:
        raw = chain(parent, tokens, extras)
        cases.append(
            {
                "parent": str(parent),
                "tokens": tokens,
                "extra_keys": extras,
                "content_id": str(raw),
                "epoch": 7,
                "pseudonym": pseudonym(raw, 7),
            }
        )
    raw = chain(int(cases[1]["content_id"]), [4, 5], None)
    cases.append(
        {
            "parent": cases[1]["content_id"],
            "tokens": [4, 5],
            "extra_keys": None,
            "content_id": str(raw),
            "epoch": 0,
            "pseudonym": pseudonym(raw, 0),
        }
    )
    p = ROOT / "conformance/content"
    p.mkdir(exist_ok=True)
    (p / "vectors.json").write_text(
        json.dumps({"construction": "sha256-chain-128-v2", "vectors": cases}, indent=2)
        + "\n"
    )


if __name__ == "__main__":
    main()
