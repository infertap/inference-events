#!/usr/bin/env python3
"""
Regenerate conformance/vllm-wire/ from a captured wire dump.

Run this whenever the engine's wire format moves. The previous corpus was authored by reading
vLLM's source and did not survive contact with a running 0.26.0 engine -- it described tag-first
arrays that the engine had stopped emitting, and integer hashes narrow enough to fit i64. This
script exists so the corpus is never again a description of what we believe the wire to be.

Two rules it follows:

1. **Valid fixtures use real captured bytes.** Every `wire_hex` below came off a socket. None is
   constructed here.
2. **Expected events are derived independently.** The derivation in `derive()` implements the
   normative semantics from the specification (spec/kv-cache-v1.md) directly, in Python, from the decoded
   msgpack -- it does not call the Rust adapter and does not mirror its structure. If the two
   disagree, one of them is wrong, and finding that out is the entire point of a corpus.

Malformed fixtures ARE constructed here, deliberately: they are adversarial inputs, not engine
output, so there is nothing to capture. Each is a mutation of a real payload, so it stays
realistic in every respect except the one thing being tested.

    python3 tools/gen-vllm-wire-corpus.py capture/capture-sha256.jsonl capture/capture-salt.jsonl
"""

import argparse
import hashlib
import json
import pathlib
import sys

import msgpack

PRODUCER = {"vllm": "0.26.0", "event_schema": "vllm-0.26.0-map", "msgspec": "0.21.1"}
SOURCE = "s0"
OUT = pathlib.Path(__file__).resolve().parent.parent / "conformance" / "vllm-wire"


# --------------------------------------------------------------------------------------
# The independent derivation. Semantics from the specification, not from the
# Rust adapter. Keep this written the way the SPEC reads, not the way the code reads.
# --------------------------------------------------------------------------------------
# --- content identity -----------------------------------------------------------------
# Written from the documented reference construction, NOT transcribed
# from the Rust. A corpus is worth having because two implementations agree; a transcription
# only proves one of them agrees with itself.
CONTENT_TAG = b"infertap:content-key:v1\x00"
CONTENT_ROOT = 0


def content_chain(parent, tokens, extra_keys):
    """One block's content identity, given its parent's. Fixed-width and length-prefixed
    throughout, so no field boundary can be shifted into another's bytes."""
    h = hashlib.sha256()
    h.update(CONTENT_TAG)
    h.update(parent.to_bytes(8, "big"))
    h.update(len(tokens).to_bytes(4, "big"))
    for t in tokens:
        h.update(t.to_bytes(4, "big"))
    if extra_keys is None:
        h.update(b"\x00")          # absent and empty are different by construction
    else:
        h.update(b"\x01")
        h.update(len(extra_keys).to_bytes(4, "big"))
        for k in extra_keys:
            kb = k.encode("utf-8")
            h.update(len(kb).to_bytes(4, "big"))
            h.update(kb)
    return int.from_bytes(h.digest()[:8], "big")


def derive(batch):
    """(events, unknown_types) a faithful decoder must produce for this batch."""
    at_ms = batch[0] * 1000.0  # the engine publishes float SECONDS; the model is milliseconds
    dp_rank = batch[2] if len(batch) > 2 and isinstance(batch[2], int) else 0
    events, unknown = [], 0

    for ev in batch[1]:
        kind = ev["type"]
        group_idx = ev.get("group_idx") or 0
        common = {"at_ms": at_ms, "dp_rank": dp_rank, "group_idx": group_idx}

        if kind == "BlockStored":
            xk = ev.get("extra_keys") or []
            hs = ev["block_hashes"]
            # A BlockStored event is a contiguous RUN of consecutive blocks, not a set that
            # shares a parent. From vLLM's block_pool.py::cache_full_blocks:
            #
            #   parent_block_hash = maybe_convert_block_hash(block_hashes[num_cached_blocks-1])
            #   start_token_idx   = num_cached_blocks * block_size
            #   end_token_idx     = num_full_blocks  * block_size
            #
            # so the event names the parent of the FIRST block, token_ids spans the whole run,
            # and every later block's parent is its predecessor in the list. llm-d's independent
            # consumer agrees (token_processor.go::prefixHashes chains prefix across chunks).
            #
            # The engine SKIPS null/masked blocks when appending hashes (sliding-window, Mamba)
            # but does not filter the token range, so a hash list shorter than the token span
            # implies a skip -- and then list order implies nothing, not even for the first
            # block, whose true parent may be the one that was dropped.
            contiguous = len(ev["token_ids"]) == len(hs) * ev["block_size"]
            # Each fixture is decoded against a FRESH bridge, so a run seeded from a NAMED
            # parent has nothing to resolve against and derives no content identity, while a
            # ROOTED run seeds from the fixed root and chains all the way through. That
            # asymmetry is the mechanism working, not a hole in the corpus.
            bs = ev["block_size"]
            prev = CONTENT_ROOT if ev.get("parent_block_hash") is None else None
            for i, h in enumerate(hs):
                # one model event per block hash; extra_keys is parallel to block_hashes
                entry = xk[i] if i < len(xk) else None
                e = dict(common)
                e["type"] = "Stored"
                e["block_hash"] = h
                if not contiguous:
                    e["parent_unknown"] = True
                elif i > 0:
                    e["parent_hash"] = hs[i - 1]
                elif ev.get("parent_block_hash") is not None:
                    e["parent_hash"] = ev["parent_block_hash"]
                e["block_size"] = ev["block_size"]
                if ev.get("medium") is not None:
                    e["medium"] = ev["medium"]
                if entry is not None:
                    e["extra_keys"] = [str(x) for x in entry]
                if ev.get("lora_id") is not None:
                    e["lora_id"] = ev["lora_id"]
                if ev.get("lora_name") is not None:
                    e["lora_name"] = ev["lora_name"]
                if ev.get("kv_cache_spec_kind") is not None:
                    e["spec_kind"] = ev["kv_cache_spec_kind"]
                if ev.get("locality") is not None:
                    e["locality"] = ev["locality"]
                # the chain advances only while every link is honest
                if contiguous and prev is not None:
                    prev = content_chain(
                        prev,
                        ev["token_ids"][i * bs : (i + 1) * bs],
                        [str(x) for x in entry] if entry is not None else None,
                    )
                    e["content_id"] = prev
                else:
                    prev = None
                events.append(e)
                # token_ids is present on the wire and has no model representation at all

        elif kind == "BlockRemoved":
            for h in ev["block_hashes"]:
                e = dict(common)
                e["type"] = "Removed"
                e["block_hash"] = h
                if ev.get("medium") is not None:
                    e["medium"] = ev["medium"]
                if ev.get("locality") is not None:
                    e["locality"] = ev["locality"]
                events.append(e)

        elif kind == "AllBlocksCleared":
            # The clear's shape is ASSUMED (never observed live), so its scope is derived as
            # DECLARED, never defaulted: a dimension the wire does not carry is absent from
            # the event, meaning the clear is global over it. The observed kinds' rule --
            # absent reads as the single-worker zero -- must not apply to a shape nothing has
            # verified, because a guessed zero under-releases silently while a global release
            # fails into the visible unresolved counter.
            e = {"at_ms": at_ms}
            if len(batch) > 2 and isinstance(batch[2], int):
                e["dp_rank"] = batch[2]
            if "group_idx" in ev:
                e["group_idx"] = ev["group_idx"] or 0
            e["type"] = "Cleared"
            if ev.get("medium") is not None:
                e["medium"] = ev["medium"]
            events.append(e)

        else:
            unknown += 1  # a kind we do not model: skipped and counted, never fatal

    return events, unknown


# --------------------------------------------------------------------------------------
def load(paths):
    """Every captured payload that carries its bytes, with provenance."""
    out = []
    for p in paths:
        for i, line in enumerate(open(p)):
            r = json.loads(line)
            h = r.get("payload_hex")
            if not h:
                continue
            raw = bytes.fromhex(h)
            out.append({
                "hex": h,
                "batch": msgpack.unpackb(raw, raw=False),
                "size": len(raw),
                "from": f"{pathlib.Path(p).name}#{i}",
            })
    return out


def kinds_of(rec):
    return [e.get("type") for e in rec["batch"][1] if isinstance(e, dict)]


def stored_events(rec):
    return [e for e in rec["batch"][1] if isinstance(e, dict) and e.get("type") == "BlockStored"]


I64_MAX = (1 << 63) - 1

# Each selector: (fixture name, note, predicate). First (smallest) match wins, so fixtures stay
# readable. Order matters only for which payload a tie goes to.
SELECTORS = [
    ("stored_single", "one BlockStored carrying one block hash",
     lambda r: kinds_of(r) == ["BlockStored"] and len(stored_events(r)[0]["block_hashes"]) == 1),
    ("stored_fanout", "one BlockStored carrying many hashes: fans out to one event per hash",
     lambda r: kinds_of(r) == ["BlockStored"] and len(stored_events(r)[0]["block_hashes"]) >= 8),
    ("stored_root", "parent_block_hash null: the prefix root, parent absent (not null) downstream",
     lambda r: kinds_of(r) == ["BlockStored"] and stored_events(r)[0]["parent_block_hash"] is None),
    ("stored_with_parent", "chained parent hash carried through",
     lambda r: kinds_of(r) == ["BlockStored"]
               and stored_events(r)[0]["parent_block_hash"] is not None),
    ("hash_above_i64_max", "REGRESSION GUARD: a block hash above i64::MAX. An i64-typed model "
                           "rejected roughly half of real traffic on exactly this",
     lambda r: any(h > I64_MAX for e in stored_events(r) for h in e["block_hashes"])),
    ("stored_salted", "extra_keys carries cache_salt in the clear on the block where it enters "
                      "the hash chain: the tenant dimension, pseudonymized at egress",
     lambda r: any(any(x is not None for x in (e.get("extra_keys") or []))
                   for e in stored_events(r))),
    ("removed_single", "one BlockRemoved: the smallest message the engine emits",
     lambda r: kinds_of(r) == ["BlockRemoved"]
               and len(r["batch"][1][0]["block_hashes"]) == 1),
    ("removed_multi", "one BlockRemoved carrying several hashes: fans out",
     lambda r: kinds_of(r) == ["BlockRemoved"] and len(r["batch"][1][0]["block_hashes"]) > 1),
    ("multi_event_batch", "several events of mixed kinds in one batch, order preserved",
     lambda r: len(set(kinds_of(r))) > 1),
    ("many_events_batch", "a scheduler flush carrying many events at once",
     lambda r: len(r["batch"][1]) >= 20),
]


def build_valid(records):
    """Real bytes, one fixture per distinct shape we can find in the capture."""
    fixtures, used = [], set()
    for name, note, pred in SELECTORS:
        best = None
        for r in records:
            if r["hex"] in used:
                continue
            try:
                if pred(r):
                    if best is None or r["size"] < best["size"]:
                        best = r
            except (KeyError, IndexError, TypeError):
                continue
        if best is None:
            print(f"  ! no capture matches {name!r} - skipped", file=sys.stderr)
            continue
        used.add(best["hex"])
        events, unknown = derive(best["batch"])
        fixtures.append({
            "schema_version": "v0",
            "producer": PRODUCER,
            "capture": best["from"],
            "name": name,
            "note": note,
            "source": SOURCE,
            "wire_hex": best["hex"],
            "expect": {"events": events, "unknown_types": unknown},
        })
    return fixtures


def pack(obj):
    return msgpack.packb(obj, use_bin_type=True).hex()


def build_constructed(records):
    """Adversarial inputs. Constructed, because no engine emits them -- each is a mutation of a
    real payload so only the tested property differs from live traffic."""
    real = min((r for r in records if kinds_of(r) == ["BlockStored"]), key=lambda r: r["size"])
    ev = dict(stored_events(real)[0])
    ts, dp = real["batch"][0], real["batch"][2]

    def fx(name, note, hexstr, expect):
        return {"schema_version": "v0", "producer": PRODUCER, "name": name, "note": note,
                "source": SOURCE, "wire_hex": hexstr, "expect": expect}

    def err(stage, contains):
        return {"error": {"stage": stage, "contains": contains}}

    def mutate(**over):
        e = dict(ev)
        e.update(over)
        return pack([ts, [e], dp])

    out = [
        # --- not msgpack at all, or the wrong top-level shape -------------------------
        fx("truncated_payload", "a real payload cut mid-message",
           real["hex"][: len(real["hex"]) // 2], err("decode", "")),
        # 0xc1 is the one byte msgpack reserves as NEVER USED, so this cannot decode under any
        # reading. (0xff was the previous choice and was wrong: it is negative fixint -1.)
        fx("garbage_bytes", "0xc1 is never-used in msgpack: undecodable by construction",
           "c1c1c1c1c1c1c1c1", err("decode", "")),
        fx("trailing_garbage",
           "a complete, valid batch followed by junk. rmp_serde's from_slice decoded the leading "
           "value and ignored the remainder, so appended bytes rode along unnoticed on an input "
           "the threat model calls semi-trusted; decode_payload now consumes the buffer",
           pack([ts, [], dp]) + "c1c1c1c1", err("decode", "trailing byte")),
        fx("top_level_string", "msgpack for a bare string, not a batch array",
           pack("hello"), err("normalize", "batch is not an array")),
        fx("batch_is_a_map", "a map where the batch array belongs",
           pack({"ts": 1.0}), err("normalize", "batch is not an array")),
        fx("ts_missing", "batch[0] is not a number", pack(["not-a-ts", [], dp]),
           err("normalize", "ts missing")),
        fx("events_not_array", "batch[1] is not an array", pack([ts, "nope", dp]),
           err("normalize", "events missing")),

        # --- the OLD wire format, which must now fail closed rather than half-decode ---
        fx("event_is_tag_array",
           "the pre-0.26 tag-first array form. Pinned as MALFORMED on purpose: a decoder that "
           "still accepted it would silently misread a modern stream",
           pack([ts, [["BlockStored", [1, 2], None, [], 16, None, "GPU"]], dp]),
           err("normalize", "event is not a map")),

        # --- map-shaped but wrong ------------------------------------------------------
        fx("event_no_type", "an event map with no type discriminator",
           pack([ts, [{"block_hashes": [1], "medium": "GPU"}], dp]),
           err("normalize", "type")),
        fx("hash_is_string", "a block hash is a string, not an integer",
           mutate(block_hashes=["deadbeef"]), err("normalize", "unsigned integer")),
        fx("hash_is_negative", "a negative block hash: no longer representable once hashes are u64",
           mutate(block_hashes=[-1]), err("normalize", "unsigned integer")),
        fx("block_size_missing", "BlockStored without block_size",
           pack([ts, [{k: v for k, v in ev.items() if k != "block_size"}], dp]),
           err("normalize", "block_size")),
        fx("block_hashes_missing", "BlockStored without block_hashes",
           pack([ts, [{k: v for k, v in ev.items() if k != "block_hashes"}], dp]),
           err("normalize", "block_hashes")),
    ]

    # --- growth is tolerated, not fatal: valid fixtures with a skip count ---------------
    unknown_ev = {"type": "SomeFutureEvent", "whatever": [1, 2, 3], "group_idx": 0}
    hexstr = pack([ts, [unknown_ev], dp])
    events, unknown = derive(msgpack.unpackb(bytes.fromhex(hexstr), raw=False))
    out.append(fx("unknown_event_type",
                  "an event kind this build does not model. NOT an error: skipped and counted, "
                  "so an engine that adds a kind cannot take the tap down mid-upgrade",
                  hexstr, {"events": events, "unknown_types": unknown}))

    mixed = pack([ts, [unknown_ev, ev], dp])
    events, unknown = derive(msgpack.unpackb(bytes.fromhex(mixed), raw=False))
    out.append(fx("unknown_alongside_known",
                  "an unmodelled kind next to a modelled one: the known event still flows",
                  mixed, {"events": events, "unknown_types": unknown}))

    # --- a run with skipped blocks: list order stops implying parenthood ----------------
    # CONSTRUCTED: this capture has zero skips (1,215 of 1,215 events exact), but sliding-window
    # and Mamba groups drop null/masked blocks from the hash list while the token range keeps
    # covering them. Every block in such a run reports an UNKNOWN parent -- not absent, which
    # would claim it begins a prefix chain, and not chained, which would invent an edge.
    skipped = dict(ev)
    # Two DISTINCT hashes against three block positions: the middle block was null/masked and
    # never appended, so neither surviving hash can be said to be the other's child.
    skipped["block_hashes"] = [10841253731892115301, 12955354968414679641]
    skipped["token_ids"] = list(range(ev["block_size"] * 3))
    skipped["extra_keys"] = None
    payload = pack([ts, [skipped], dp])
    events, unknown = derive(msgpack.unpackb(bytes.fromhex(payload), raw=False))
    out.append(fx("run_with_skipped_blocks",
                  "CONSTRUCTED: a hash list shorter than its token span. Parenthood is "
                  "undeterminable for the whole run, so every block says UNKNOWN rather than "
                  "claiming a root or inventing a chain",
                  payload, {"events": events, "unknown_types": unknown}))

    # --- locality: on the wire at 0.26.0, invisible in every capture --------------------
    # msgspec's omit_defaults means a field left at its default is absent from the bytes, so a
    # capture-derived corpus cannot distinguish "this version lacks the field" from "this run
    # never set it". Our single-GPU, no-offload runs left locality unset, so it must be
    # constructed -- and it is exactly the field a consumer must not guess at, since counting a
    # remote block as a local copy invents duplication.
    for tag, note in [
        ("REMOTE", "a block in a store the publisher can reach but does not own"),
        ("LOCAL", "the explicit form of what every captured event meant implicitly"),
    ]:
        payload = pack([ts, [dict(ev, locality=tag)], dp])
        events, unknown = derive(msgpack.unpackb(bytes.fromhex(payload), raw=False))
        out.append(fx(f"locality_{tag.lower()}",
                      f"CONSTRUCTED, not captured: {note}. Carried through unmapped, so an "
                      f"unrecognized value reaches the consumer intact instead of being folded "
                      f"into LOCAL by a lenient parse",
                      payload, {"events": events, "unknown_types": unknown}))

    remove_ev = {"type": "BlockRemoved", "block_hashes": ev["block_hashes"], "medium": "GPU",
                 "group_idx": 0, "locality": "REMOTE"}
    payload = pack([ts, [remove_ev], dp])
    events, unknown = derive(msgpack.unpackb(bytes.fromhex(payload), raw=False))
    out.append(fx("locality_on_remove",
                  "CONSTRUCTED: BlockRemoved carries locality too, so a consumer can close an "
                  "interval on the same side it opened it",
                  payload, {"events": events, "unknown_types": unknown}))

    # --- AllBlocksCleared: unobserved, so this one IS constructed and says so -----------
    cleared = pack([ts, [{"type": "AllBlocksCleared", "medium": "GPU", "group_idx": 0}], dp])
    events, unknown = derive(msgpack.unpackb(bytes.fromhex(cleared), raw=False))
    out.append(fx("cleared_all",
                  "CONSTRUCTED, not captured: vLLM 0.26.0 exposes no route that triggers a cache "
                  "reset, so no live AllBlocksCleared exists to capture. Shape follows the two "
                  "observed kinds; re-cut from a real one when an engine can be made to emit it",
                  cleared, {"events": events, "unknown_types": unknown}))

    # The assumed-shape edge of the same event: a clear that declares NO scope at all. The
    # producer must treat it as global for the named tier -- released across all origins,
    # counted -- and the emitted event carries no scope claim, because absence failing toward
    # a guessed zero is exactly how an unobserved shape turns into silent tombstones.
    unscoped = pack([ts, [{"type": "AllBlocksCleared", "medium": "GPU"}]])
    events, unknown = derive(msgpack.unpackb(bytes.fromhex(unscoped), raw=False))
    out.append(fx("cleared_scope_undeclared",
                  "CONSTRUCTED: a clear whose wire shape declares no dp_rank and no group_idx. "
                  "Scope is transduced as declared -- absent, global for the tier -- never "
                  "defaulted to zero; the bridge releases the tier across all origins",
                  unscoped, {"events": events, "unknown_types": unknown}))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("captures", nargs="+")
    a = ap.parse_args()

    records = load(a.captures)
    print(f"loaded {len(records)} captured payloads", file=sys.stderr)

    for old in OUT.glob("*.json"):
        old.unlink()

    valid = build_valid(records)
    constructed = build_constructed(records)
    for fx in valid + constructed:
        (OUT / f"{fx['name']}.json").write_text(json.dumps(fx, indent=1) + "\n")

    v = [f["name"] for f in valid + constructed if "events" in f["expect"]]
    m = [f["name"] for f in valid + constructed if "error" in f["expect"]]
    (OUT / "manifest.json").write_text(json.dumps({
        "schema_version": "v0",
        "producer": PRODUCER,
        "derivation": "Valid fixtures are real captured bytes; their expected events are derived "
                      "independently by tools/gen-vllm-wire-corpus.py from the normative "
                      "semantics, never by running the implementation under test. Malformed "
                      "fixtures are deliberate mutations of real payloads.",
        "captures": a.captures,
        "valid": sorted(v),
        "malformed": sorted(m),
    }, indent=1) + "\n")

    print(f"wrote {len(v)} valid + {len(m)} malformed fixtures to {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
