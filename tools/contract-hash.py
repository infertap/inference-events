#!/usr/bin/env python3
"""
Compute the contract hash: one value that moves when, and only when, the contract moves.

A consumer vendors this repo at a pinned commit. If the contract changes and the consumer does
not bump its pin, the consumer keeps testing against the old vendored corpora and passes
cleanly — a stale pin fails on the ABSENCE of action, and CI runs on action, so nothing fires.
That is the same shape as every other silent failure in this system.

Comparing commit SHAs would fix it and immediately become noise: every unrelated commit here —
a typo, a lint, a packaging tweak — would flag the consumer as stale, and a check that cries
wolf gets muted inside a week. Hashing the CONTRACT instead means the value is stable across
churn and moves exactly once per real change.

Scope is `conformance/`: the corpora ARE the machine-readable contract, and this design's own
rule is that a normative change arrives with a fixture. A prose-only change to
`spec/kv-cache-v1.md` therefore will not move this hash — a gap worth knowing about,
and the alternative (hashing the prose) reintroduces exactly the noise the commit-SHA approach
had.

    python3 tools/contract-hash.py            # print
    python3 tools/contract-hash.py --write    # write conformance/CONTRACT_HASH
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
