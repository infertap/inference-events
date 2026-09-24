#!/usr/bin/env python3
"""Compute SHA-256 over conformance file paths and bytes, excluding CONTRACT_HASH.

Any corpus byte change updates the hash, including schema descriptions and formatting.
Specification-only and implementation-only changes do not update it.
"""

import argparse
import hashlib
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CORPUS = ROOT / "conformance"
HASH_FILE = CORPUS / "CONTRACT_HASH"


def contract_hash() -> str:
    """SHA-256 over every corpus file, path and contents, in sorted order.

    Paths are included so a rename moves the hash; lengths are included so no concatenation of
    two files can collide with a different pair.
    """
    h = hashlib.sha256()
    for path in sorted(p for p in CORPUS.rglob("*") if p.is_file() and p != HASH_FILE):
        rel = path.relative_to(CORPUS).as_posix().encode()
        body = path.read_bytes()
        h.update(len(rel).to_bytes(8, "big"))
        h.update(rel)
        h.update(len(body).to_bytes(8, "big"))
        h.update(body)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument(
        "--check",
        action="store_true",
        help="exit nonzero if the committed value is stale",
    )
    a = ap.parse_args()

    current = contract_hash()
    if a.write:
        HASH_FILE.write_text(current + "\n")
        print(f"wrote {HASH_FILE.relative_to(ROOT)}: {current}")
        return 0
    if a.check:
        committed = HASH_FILE.read_text().strip() if HASH_FILE.exists() else "<absent>"
        if committed != current:
            print(
                f"contract hash is stale\n  committed: {committed}\n  actual:    {current}\n"
                f"Run: python3 tools/contract-hash.py --write",
                file=sys.stderr,
            )
            return 1
        print(f"contract hash current: {current}")
        return 0
    print(current)
    return 0


if __name__ == "__main__":
    sys.exit(main())
