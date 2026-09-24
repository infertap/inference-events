#!/usr/bin/env python3
"""Capture multipart ZMQ messages as hexadecimal frames for offline inspection.

The report summarizes framing and decoded batch shapes. Use kvinspect.py to inspect
map-shaped event fields. Subscribe before sending inference requests.
"""

import argparse
import json
import platform
import sys
import time
from collections import Counter, defaultdict

import zmq

try:
    import msgpack

    def unpack(b):
        return msgpack.unpackb(b, raw=False, strict_map_key=False)

    DECODER = "msgpack"
except ImportError:  # vLLM ships msgspec
    import msgspec

    def unpack(b):
        return msgspec.msgpack.decode(b)

    DECODER = "msgspec"


def describe(v):
    """Describe the observed value type and collection shape.

    Ints report their ACTUAL bit length, so a 256-bit hash arriving as an oversized
    int is distinguishable from a 64-bit one. Bytes report their length, so a sha256
    digest arriving as msgpack `bin` is unmistakable. Lists describe their first
    element, which is where block hashes live.
    """
    if v is None:
        return "null"
    if isinstance(v, bool):  # must precede int
        return "bool"
    if isinstance(v, int):
        return f"int({v.bit_length()}b)"
    if isinstance(v, float):
        return "float"
    if isinstance(v, bytes):
        return f"bytes({len(v)})"
    if isinstance(v, str):
        return "str"
    if isinstance(v, (list, tuple)):
        return f"list[{len(v)}]<{describe(v[0]) if v else 'empty'}>"
    if isinstance(v, dict):
        return f"map[{len(v)}]"
    return type(v).__name__


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint", default="tcp://127.0.0.1:5557")
    ap.add_argument("--duration", type=float, default=180.0, help="seconds")
    ap.add_argument("--max-msgs", type=int, default=20000)
    ap.add_argument("--tag", default="run", help="label for output filenames")
    ap.add_argument(
        "--hex-limit",
        type=int,
        default=500,
        help="store full payload hex for this many messages; after that, only "
        "shape-novel messages are stored (keeps the file small, keeps the variety)",
    )
    ap.add_argument("--note", default="", help="free text recorded in the manifest")
    args = ap.parse_args()

    cap_path = f"capture-{args.tag}.jsonl"
    rep_path = f"report-{args.tag}.txt"
    man_path = f"manifest-{args.tag}.json"

    ctx = zmq.Context()
    sock = ctx.socket(zmq.SUB)
    sock.setsockopt(zmq.SUBSCRIBE, b"")
    sock.setsockopt(zmq.RCVHWM, 500_000)  # never be the reason a message is lost
    sock.connect(args.endpoint)
    poller = zmq.Poller()
    poller.register(sock, zmq.POLLIN)

    print(f"[kvcap] decoder={DECODER} endpoint={args.endpoint}", file=sys.stderr)
    print(f"[kvcap] capturing for {args.duration}s -> {cap_path}", file=sys.stderr)

    msgs = 0
    total_payload = 0
    hex_stored = 0
    first_arrival = None
    last_arrival = None

    frame_arity = Counter()
    batch_arity = Counter()
    tag_counts = Counter()
    shapes = defaultdict(set)  # (event_tag, field_index) -> {descriptors}
    batch_field_shapes = defaultdict(set)  # batch_index -> {descriptors}
    decode_errors = Counter()
    seen_signatures = set()
    seqs = []

    started = time.time()
    with open(cap_path, "w") as out:
        while msgs < args.max_msgs and (time.time() - started) < args.duration:
            if not poller.poll(500):
                continue
            parts = sock.recv_multipart()
            arrival = time.time()
            if first_arrival is None:
                first_arrival = arrival
            last_arrival = arrival
            msgs += 1

            frame_arity[len(parts)] += 1
            topic = parts[0] if parts else b""
            seq = None
            if len(parts) > 1 and len(parts[1]) == 8:
                seq = int.from_bytes(parts[1], "big")
                seqs.append(seq)
            payload = parts[-1] if parts else b""
            total_payload += len(payload)

            batch = None
            err = None
            try:
                batch = unpack(payload)
            except Exception as e:  # Preserve undecodable frames for inspection.
                err = f"{type(e).__name__}: {e}"
                decode_errors[err[:120]] += 1

            sig_parts = []
            if isinstance(batch, (list, tuple)):
                batch_arity[len(batch)] += 1
                for i, f in enumerate(batch):
                    batch_field_shapes[i].add(describe(f))
                events = (
                    batch[1]
                    if len(batch) > 1 and isinstance(batch[1], (list, tuple))
                    else []
                )
                for ev in events:
                    if not isinstance(ev, (list, tuple)) or not ev:
                        continue
                    etag = ev[0] if isinstance(ev[0], str) else repr(ev[0])
                    tag_counts[etag] += 1
                    for i, f in enumerate(ev):
                        d = describe(f)
                        shapes[(etag, i)].add(d)
                        sig_parts.append((etag, i, d))

            signature = frozenset(sig_parts)
            novel = signature not in seen_signatures
            if novel:
                seen_signatures.add(signature)

            rec = {
                "i": msgs - 1,
                "arrival": arrival,
                "seq": seq,
                "n_parts": len(parts),
                "topic_hex": topic.hex(),
                "payload_len": len(payload),
            }
            if err:
                rec["decode_error"] = err
            # Full bytes for the first N, then only for newly-seen shapes. Those are
            # the ones worth turning into fixtures.
            if hex_stored < args.hex_limit or novel:
                rec["payload_hex"] = payload.hex()
                rec["shape_novel"] = novel
                hex_stored += 1
            out.write(json.dumps(rec) + "\n")

    elapsed = (
        (last_arrival - first_arrival) if (first_arrival and last_arrival) else 0.0
    )
    gaps = 0
    if len(seqs) > 1:
        for a, b in zip(seqs, seqs[1:]):
            if b > a + 1:
                gaps += b - a - 1

    # ---- report -------------------------------------------------------------
    L = []
    w = L.append
    w("=" * 72)
    w(f"kvcap report  tag={args.tag}")
    w("=" * 72)
    w(f"endpoint          {args.endpoint}")
    w(f"decoder           {DECODER}")
    w(f"messages          {msgs}")
    w(f"payload bytes     {total_payload}")
    w(f"observed span     {elapsed:.1f}s")
    if elapsed > 0:
        w(f"message rate      {msgs/elapsed:.1f} msg/s")
        w(f"wire rate         {total_payload/elapsed/1024:.1f} KiB/s")
        w(f"mean payload      {total_payload/max(msgs,1):.0f} B")
    w(f"publisher seq gaps {gaps}   (nonzero = the publisher outran this capture)")
    w("")
    w("-- framing ---------------------------------------------------------")
    w(
        f"multipart arity   {dict(frame_arity)}   (vLLM publishes 3: topic, seq, payload)"
    )
    w("")
    w("-- batch envelope --------------------------------------------------")
    w(f"batch arity       {dict(batch_arity)}")
    for i in sorted(batch_field_shapes):
        w(f"  batch[{i}]        {sorted(batch_field_shapes[i])}")
    w("")
    w("-- events ----------------------------------------------------------")
    for etag, n in tag_counts.most_common():
        w(f"{etag}  x{n}")
        idxs = sorted(i for (t, i) in shapes if t == etag)
        for i in idxs:
            w(f"    [{i}]  {sorted(shapes[(etag, i)])}")
    if decode_errors:
        w("")
        w("-- decode errors ---------------------------------------------------")
        for e, n in decode_errors.most_common():
            w(f"  x{n}  {e}")
    w("")
    report = "\n".join(L)

    with open(rep_path, "w") as f:
        f.write(report + "\n")
    print("\n" + report, file=sys.stderr)

    manifest = {
        "tag": args.tag,
        "note": args.note,
        "endpoint": args.endpoint,
        "decoder": DECODER,
        "captured_at_unix": started,
        "captured_at_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
        "messages": msgs,
        "payload_bytes": total_payload,
        "observed_span_s": elapsed,
        "seq_gaps": gaps,
        "frame_arity": dict(frame_arity),
        "batch_arity": dict(batch_arity),
        "event_counts": dict(tag_counts),
        "field_shapes": {f"{t}[{i}]": sorted(v) for (t, i), v in shapes.items()},
        "batch_field_shapes": {
            str(i): sorted(v) for i, v in batch_field_shapes.items()
        },
        "python": platform.python_version(),
        "platform": platform.platform(),
        "TODO_fill_in": {
            "vllm_version": "<paste `pip show vllm | head -2`>",
            "msgspec_version": "<paste `pip show msgspec | head -2`>",
            "engine_args": "<paste the full vllm serve command>",
            "prefix_caching_hash_algo": "<the value you passed>",
            "gpu": "<paste `nvidia-smi --query-gpu=name --format=csv,noheader`>",
        },
    }
    with open(man_path, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"\n[kvcap] wrote {cap_path}, {rep_path}, {man_path}", file=sys.stderr)
    print("[kvcap] fill in manifest TODO_fill_in before copying back", file=sys.stderr)


if __name__ == "__main__":
    main()
