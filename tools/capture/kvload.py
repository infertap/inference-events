#!/usr/bin/env python3
"""
kvload.py - drive traffic shaped to produce every KV-cache event kind.

Stdlib only. The shape matters more than the volume:

  * P distinct long prefixes, each reused many times  -> BlockStored + prefix reuse
  * more prefixes than the cache can hold             -> BlockRemoved (eviction)
  * an optional /reset_prefix_cache at the end        -> AllBlocksCleared

Pair with --num-gpu-blocks-override on the server so the cache is small enough to
actually evict; otherwise a tiny model on a big GPU never fills and you capture no
BlockRemoved at all.

  python3 kvload.py --base http://127.0.0.1:8000 --model Qwen/Qwen2.5-0.5B-Instruct
"""

import argparse
import json
import random
import sys
import threading
import time
import urllib.error
import urllib.request

WORDS = (
    "alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima mike "
    "november oscar papa quebec romeo sierra tango uniform victor whiskey xray yankee "
    "zulu anchor beacon cipher domain ember fathom girder harbor ingot jasper"
).split()


def make_prefix(rng, approx_tokens):
    # ~0.75 words per token is close enough; we only need length, not meaning.
    n = int(approx_tokens * 0.75)
    return " ".join(rng.choice(WORDS) for _ in range(n))


def post(url, payload, timeout=120):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--model", required=True)
    ap.add_argument("--prefixes", type=int, default=24, help="distinct shared prefixes")
    ap.add_argument("--prefix-tokens", type=int, default=1200)
    ap.add_argument("--requests", type=int, default=400)
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--max-tokens", type=int, default=8)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument(
        "--reset-at-end",
        action="store_true",
        help="POST /reset_prefix_cache to force an AllBlocksCleared event",
    )
    args = ap.parse_args()

    rng = random.Random(args.seed)
    prefixes = [make_prefix(rng, args.prefix_tokens) for _ in range(args.prefixes)]
    url = f"{args.base}/v1/completions"

    counter = {"done": 0, "err": 0}
    lock = threading.Lock()
    started = time.time()

    def worker(worker_id):
        r = random.Random(args.seed * 1000 + worker_id)
        while True:
            with lock:
                if counter["done"] + counter["err"] >= args.requests:
                    return
                counter["done"] += 1
                n = counter["done"]
            # Reuse a prefix, vary only the tail: the reuse is what produces cache
            # hits, and the variation is what forces new blocks at the end.
            p = prefixes[r.randrange(len(prefixes))]
            prompt = f"{p}\n\nQ{n}: {r.randrange(10**9)}\nA:"
            try:
                post(
                    url,
                    {
                        "model": args.model,
                        "prompt": prompt,
                        "max_tokens": args.max_tokens,
                        "temperature": 0.0,
                    },
                )
            except (urllib.error.URLError, OSError, TimeoutError) as e:
                with lock:
                    counter["err"] += 1
                print(f"[kvload] request error: {e}", file=sys.stderr)
            if n % 50 == 0:
                el = time.time() - started
                print(
                    f"[kvload] {n}/{args.requests}  {n/el:.1f} req/s", file=sys.stderr
                )

    threads = [
        threading.Thread(target=worker, args=(i,), daemon=True)
        for i in range(args.concurrency)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    el = time.time() - started
    print(
        f"[kvload] {counter['done']} sent, {counter['err']} errors, {el:.1f}s",
        file=sys.stderr,
    )

    if args.reset_at_end:
        # Endpoint name has moved between versions; try the known spellings and
        # report rather than fail. A miss just means no AllBlocksCleared fixture.
        for path in ("/reset_prefix_cache", "/v1/reset_prefix_cache"):
            try:
                status, _ = post(f"{args.base}{path}", {}, timeout=30)
                print(f"[kvload] {path} -> {status}", file=sys.stderr)
                if status < 300:
                    break
            except Exception as e:
                print(f"[kvload] {path} -> {e}", file=sys.stderr)
        else:
            print(
                "[kvload] no reset endpoint hit; AllBlocksCleared may be absent from "
                "this capture. Stopping the server while kvcap runs is the fallback.",
                file=sys.stderr,
            )


if __name__ == "__main__":
    main()
