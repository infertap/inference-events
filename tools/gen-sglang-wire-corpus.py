#!/usr/bin/env python3
"""Generate SGLang wire fixtures from captured MessagePack payloads.

SGLang's ``ZmqEventPublisher`` speaks vLLM's wire format: three ZMQ frames, a positional
batch ``[ts, events, attn_dp_rank]``, and tagged event maps. The fixtures here pin the
SGLang profile of that format, whose ``BlockStored`` carries ``cache_salt`` and
``session_id`` at event level and no ``extra_keys``, ``lora_name``, group, spec, locality
or ownership fields.

Captured cases preserve the source bytes. Constructed cases exercise malformed input
and fields absent from the captures. Expected events are derived independently from
the specification without invoking a consumer implementation.

Run with the captures the corpus manifest names, under ``capture/sglang-*``.
"""

import argparse
import hashlib
import json
import pathlib
import sys

import msgpack

PRODUCER = {
    "sglang": "0.5.20",
    "event_schema": "sglang-0.5.20-map",
    "msgspec": "0.21.1",
}
SOURCE = "s0"
OUT = pathlib.Path(__file__).resolve().parent.parent / "conformance" / "sglang-wire"
U64 = (1 << 64) - 1


# --------------------------------------------------------------------------------------
# The independent derivation, written from the specification (spec/kv-cache-v2.md,
# sections 2.3 and 3.1.1) and from SGLang's event definitions
# (python/sglang/srt/disaggregation/kv_events.py, python/sglang/srt/mem_cache/events.py
# at v0.5.20), never from a consumer implementation.
# --------------------------------------------------------------------------------------
CONTENT_TAG = b"infertap:content-key:v2\x00"
CONTENT_ROOT = 0


def content_chain(parent, tokens, extra_keys):
    """One block's content identity, given its parent's (section 3.1.1)."""
    h = hashlib.sha256()
    h.update(CONTENT_TAG)
    h.update(parent.to_bytes(16, "big"))
    h.update(len(tokens).to_bytes(4, "big"))
    for t in tokens:
        h.update(t.to_bytes(4, "big"))
    if extra_keys is None:
        h.update(b"\x00")
    else:
        h.update(b"\x01")
        h.update(len(extra_keys).to_bytes(4, "big"))
        for k in extra_keys:
            kb = k.encode("utf-8")
            h.update(len(kb).to_bytes(4, "big"))
            h.update(kb)
    return int.from_bytes(h.digest()[:16], "big")


def unsigned(h):
    """SGLang's ``hash_str_to_int64`` folds the leading 64 bits of a SHA-256 into a
    signed 64-bit integer, so about half of all hashes arrive negative. The block
    identity is those 64 bits read unsigned (section 3.1, ``block_id`` is engine-local).
    """
    return h & U64


def salt_of(ev):
    """The event-level salt, or None. SGLang folds ``cache_salt or None`` into its key, so
    an empty string is no salt."""
    salt = ev.get("cache_salt")
    return salt if isinstance(salt, str) and salt else None


def token_ids_usable(token_ids):
    """Every entry is an unsigned 32-bit token id. A bigram key (EAGLE) exposes pairs,
    which are not token ids: the store is kept and no identity is derived."""
    return all(isinstance(t, int) and 0 <= t < (1 << 32) for t in token_ids)


def derive(batch):
    """(events, unknown_types) a faithful decoder must produce for this batch."""
    at_ms = batch[0] * 1000.0
    # batch[2] is attn_dp_rank. Absent reads as rank 0 for block events; a clear keeps
    # the declared-or-absent distinction.
    dp_rank = batch[2] if len(batch) > 2 and isinstance(batch[2], int) else 0
    events, unknown = [], 0

    for ev in batch[1]:
        kind = ev["type"]
        # SGLang has no group_idx; the single cache group is group 0.
        common = {"at_ms": at_ms, "dp_rank": dp_rank, "group_idx": 0}

        if kind == "BlockStored":
            hs = [unsigned(h) for h in ev["block_hashes"]]
            bs = ev["block_size"]
            token_ids = ev["token_ids"]
            # The recorder emits one BlockStored per page and coalesces a run of pages
            # whose parent is the predecessor's hash. Keys are page-aligned, so every
            # stored page is full and block_size is the page size; the run is
            # contiguous exactly when the hash count times block_size covers the tokens.
            contiguous = len(token_ids) == len(hs) * bs
            rooted = ev.get("parent_block_hash") is None
            # The salt enters the chain where vLLM puts it: the first block of a rooted
            # run, as that block's extra keys. Every descendant inherits it through its
            # parent, so the same content under the same salt is one identity on both
            # engines (section 3.1, extra_keys participates in identity).
            salt = salt_of(ev)
            usable = token_ids_usable(token_ids)
            prev = CONTENT_ROOT if rooted else None
            for i, h in enumerate(hs):
                extra = [salt] if (i == 0 and rooted and salt is not None) else None
                e = dict(common)
                e["type"] = "Stored"
                e["block_hash"] = h
                if not contiguous:
                    e["parent_unknown"] = True
                elif i > 0:
                    e["parent_hash"] = hs[i - 1]
                elif not rooted:
                    e["parent_hash"] = unsigned(ev["parent_block_hash"])
                e["block_size"] = bs
                if ev.get("medium") is not None:
                    e["medium"] = ev["medium"]
                if extra is not None:
                    e["extra_keys"] = extra
                if ev.get("lora_id") is not None:
                    e["lora_id"] = ev["lora_id"]
                # lora_name, spec_kind and locality are not on this wire; session_id is
                # read for drift and never carried (the tap provides no request
                # attribution).
                if contiguous and usable and prev is not None:
                    prev = content_chain(prev, token_ids[i * bs : (i + 1) * bs], extra)
                    e["content_id"] = str(prev)
                else:
                    prev = None
                events.append(e)

        elif kind == "BlockRemoved":
            for h in ev["block_hashes"]:
                e = dict(common)
                e["type"] = "Removed"
                e["block_hash"] = unsigned(h)
                if ev.get("medium") is not None:
                    e["medium"] = ev["medium"]
                events.append(e)

        elif kind == "AllBlocksCleared":
            # Fieldless on this wire (``class AllBlocksCleared(KVCacheEvent): pass``):
            # the only scope it can carry is the batch's rank, declared or absent, and
            # the clear is global over group and tier.
            e = {"at_ms": at_ms}
            if len(batch) > 2 and isinstance(batch[2], int):
                e["dp_rank"] = batch[2]
            e["type"] = "Cleared"
            events.append(e)

        else:
            unknown += 1

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
            out.append(
                {
                    "hex": h,
                    "batch": msgpack.unpackb(raw, raw=False),
                    "size": len(raw),
                    "from": f"{pathlib.Path(p).name}#{i}",
                }
            )
    return out


def kinds_of(rec):
    return [e.get("type") for e in rec["batch"][1] if isinstance(e, dict)]


def stored_events(rec):
    return [
        e
        for e in rec["batch"][1]
        if isinstance(e, dict) and e.get("type") == "BlockStored"
    ]


def removed_events(rec):
    return [
        e
        for e in rec["batch"][1]
        if isinstance(e, dict) and e.get("type") == "BlockRemoved"
    ]


# Each selector: (fixture name, note, predicate). The smallest match wins.
SELECTORS = [
    (
        "stored_single",
        "one BlockStored carrying one block hash",
        lambda r: kinds_of(r) == ["BlockStored"]
        and len(stored_events(r)[0]["block_hashes"]) == 1,
    ),
    (
        "stored_fanout",
        "one BlockStored carrying many hashes: the recorder coalesced a run of pages",
        lambda r: kinds_of(r) == ["BlockStored"]
        and len(stored_events(r)[0]["block_hashes"]) >= 8,
    ),
    (
        "stored_root",
        "parent_block_hash null: the tree root's child, parent absent downstream",
        lambda r: kinds_of(r) == ["BlockStored"]
        and stored_events(r)[0]["parent_block_hash"] is None,
    ),
    (
        "stored_with_parent",
        "chained parent hash: the last page of the parent node",
        lambda r: kinds_of(r) == ["BlockStored"]
        and stored_events(r)[0]["parent_block_hash"] is not None,
    ),
    (
        "hash_negative",
        "a negative block hash: the leading 64 bits of the engine's SHA-256 read as a "
        "signed integer, whose unsigned value is the block identity",
        lambda r: any(h < 0 for e in stored_events(r) for h in e["block_hashes"]),
    ),
    (
        "parent_hash_negative",
        "a negative parent hash, read the same way",
        lambda r: any((e["parent_block_hash"] or 0) < 0 for e in stored_events(r)),
    ),
    (
        "stored_salted",
        "cache_salt at event level on a rooted run: folded into the first block's "
        "extra keys, where vLLM carries it, and pseudonymized at egress",
        lambda r: any(
            salt_of(e) is not None and e["parent_block_hash"] is None
            for e in stored_events(r)
        ),
    ),
    (
        "stored_salted_with_parent",
        "cache_salt on a run continuing a salted chain: not folded again; the parent "
        "carries the salt",
        lambda r: any(
            salt_of(e) is not None and e["parent_block_hash"] is not None
            for e in stored_events(r)
        ),
    ),
    (
        "stored_host_tier",
        "a write-through to the host tier: medium CPU_PINNED, the same hashes and "
        "tokens as the GPU store",
        lambda r: any(e.get("medium") == "CPU_PINNED" for e in stored_events(r)),
    ),
    (
        "removed_single",
        "a BlockRemoved carrying one hash: an eviction lands in the same step's batch "
        "as the store that needed the room",
        lambda r: any(len(e["block_hashes"]) == 1 for e in removed_events(r)),
    ),
    (
        "removed_multi",
        "a BlockRemoved carrying a whole node's pages",
        lambda r: any(len(e["block_hashes"]) > 1 for e in removed_events(r)),
    ),
    (
        "removed_host_tier",
        "an eviction from the host tier: medium CPU_PINNED",
        lambda r: any(e.get("medium") == "CPU_PINNED" for e in removed_events(r)),
    ),
    (
        "cleared_all",
        "a captured AllBlocksCleared from /flush_cache: fieldless, scoped by the "
        "batch's attn_dp_rank alone",
        lambda r: "AllBlocksCleared" in kinds_of(r),
    ),
    (
        "multi_event_batch",
        "several events of mixed kinds in one batch, order preserved",
        lambda r: len(set(kinds_of(r))) > 1,
    ),
    (
        "many_events_batch",
        "a scheduler step carrying several events at once: the recorder coalesces "
        "pages, so a step's batch stays short",
        lambda r: len(r["batch"][1]) >= 4,
    ),
]


def build_valid(records):
    """Select captured bytes for each available event shape."""
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
        fixtures.append(
            {
                "schema_version": "v0",
                "producer": PRODUCER,
                "capture": best["from"],
                "name": name,
                "note": note,
                "source": SOURCE,
                "wire_hex": best["hex"],
                "expect": {"events": events, "unknown_types": unknown},
            }
        )
    return fixtures


def pack(obj):
    return msgpack.packb(obj, use_bin_type=True).hex()


def build_constructed(records):
    """Adversarial and uncaptured inputs, each a mutation of a real payload."""
    real = min(
        (
            r
            for r in records
            if kinds_of(r) == ["BlockStored"]
            and stored_events(r)[0]["parent_block_hash"] is None
        ),
        key=lambda r: r["size"],
    )
    ev = dict(stored_events(real)[0])
    ev.pop("cache_salt", None)
    ev.pop("session_id", None)
    ts, dp = real["batch"][0], real["batch"][2]

    def fx(name, note, hexstr, expect):
        return {
            "schema_version": "v0",
            "producer": PRODUCER,
            "name": name,
            "note": note,
            "source": SOURCE,
            "wire_hex": hexstr,
            "expect": expect,
        }

    def err(stage, contains):
        return {"error": {"stage": stage, "contains": contains}}

    def mutate(**over):
        e = dict(ev)
        e.update(over)
        return pack([ts, [e], dp])

    def valid(name, note, hexstr):
        events, unknown = derive(msgpack.unpackb(bytes.fromhex(hexstr), raw=False))
        return fx(name, note, hexstr, {"events": events, "unknown_types": unknown})

    out = [
        fx(
            "truncated_payload",
            "a real payload cut mid-message",
            real["hex"][: len(real["hex"]) // 2],
            err("decode", ""),
        ),
        fx(
            "garbage_bytes",
            "0xc1 is never-used in msgpack: undecodable by construction",
            "c1c1c1c1c1c1c1c1",
            err("decode", ""),
        ),
        fx(
            "trailing_garbage",
            "a complete, valid batch followed by junk: a decoder must consume the "
            "whole buffer",
            pack([ts, [], dp]) + "c1c1c1c1",
            err("decode", "trailing byte"),
        ),
        fx(
            "top_level_string",
            "msgpack for a bare string, not a batch array",
            pack("hello"),
            err("normalize", "batch is not an array"),
        ),
        fx(
            "batch_is_a_map",
            "a map where the batch array belongs",
            pack({"ts": 1.0}),
            err("normalize", "batch is not an array"),
        ),
        fx(
            "ts_missing",
            "batch[0] is not a number",
            pack(["not-a-ts", [], dp]),
            err("normalize", "ts missing"),
        ),
        fx(
            "events_not_array",
            "batch[1] is not an array",
            pack([ts, "nope", dp]),
            err("normalize", "events missing"),
        ),
        fx(
            "event_is_tag_array",
            "a tag-first array where the tagged map belongs",
            pack([ts, [["BlockStored", [1, 2], None, [], 16, None, "GPU"]], dp]),
            err("normalize", "event is not a map"),
        ),
        fx(
            "event_no_type",
            "an event map with no type discriminator",
            pack([ts, [{"block_hashes": [1], "medium": "GPU"}], dp]),
            err("normalize", "type"),
        ),
        fx(
            "hash_is_string",
            "a block hash is a string, not an integer",
            mutate(block_hashes=["deadbeef"]),
            err("normalize", "unsigned integer"),
        ),
        fx(
            "hash_is_float",
            "a block hash is a float, not an integer",
            mutate(block_hashes=[1.5]),
            err("normalize", "unsigned integer"),
        ),
        fx(
            "block_size_missing",
            "BlockStored without block_size",
            pack([ts, [{k: v for k, v in ev.items() if k != "block_size"}], dp]),
            err("normalize", "block_size"),
        ),
        fx(
            "block_hashes_missing",
            "BlockStored without block_hashes",
            pack([ts, [{k: v for k, v in ev.items() if k != "block_hashes"}], dp]),
            err("normalize", "block_hashes"),
        ),
        fx(
            "attn_dp_rank_negative",
            "a negative attn_dp_rank is not a rank and must not read as rank 0",
            pack([ts, [ev], -7]),
            err("normalize", "dp_rank"),
        ),
    ]

    unknown_ev = {"type": "SomeFutureEvent", "whatever": [1, 2, 3]}
    out.append(
        valid(
            "unknown_event_type",
            "an event kind this build does not model: skipped and counted, not an error",
            pack([ts, [unknown_ev], dp]),
        )
    )
    out.append(
        valid(
            "unknown_alongside_known",
            "an unmodelled kind next to a modelled one: the known event still flows",
            pack([ts, [unknown_ev, ev], dp]),
        )
    )

    # A hash list shorter than its token span: parenthood is undeterminable for the
    # whole run. SGLang's recorder never emits this; it is pinned so the rule holds.
    skipped = dict(ev)
    skipped["block_hashes"] = [10841253731892115301, 12955354968414679641]
    skipped["block_size"] = 4
    skipped["token_ids"] = list(range(12))
    out.append(
        valid(
            "run_with_skipped_blocks",
            "CONSTRUCTED: two hashes against three block positions; every block says "
            "UNKNOWN rather than claiming a root or inventing a chain",
            pack([ts, [skipped], dp]),
        )
    )

    # The salt, in every shape the profile distinguishes.
    out.append(
        valid(
            "salt_empty",
            "CONSTRUCTED: an empty cache_salt is no salt; the identity equals the "
            "unsalted form and no extra keys are carried",
            mutate(cache_salt=""),
        )
    )
    out.append(
        valid(
            "stored_with_session",
            "CONSTRUCTED: session_id is attribution the tap does not provide; the "
            "store normalizes and nothing of the session is carried",
            mutate(session_id="session-1"),
        )
    )
    out.append(
        valid(
            "stored_with_lora_id",
            "CONSTRUCTED: lora_id is carried and no lora_name is synthesized",
            mutate(lora_id=7),
        )
    )

    # Media the enum declares and the capture cannot show: at v0.5.20 no record site
    # names DISK or EXTERNAL. Carried through as terms, never remapped.
    for medium in ("DISK", "EXTERNAL"):
        out.append(
            valid(
                f"medium_{medium.lower()}",
                f"CONSTRUCTED: StorageMedium.{medium}, not recorded by any v0.5.20 path; "
                "an unknown medium passes through as a term",
                mutate(medium=medium),
            )
        )

    # Bigram keys (EAGLE speculative decoding) expose token pairs as token_ids.
    pairs = dict(ev)
    pairs["block_hashes"] = ev["block_hashes"][:1]
    pairs["block_size"] = 2
    pairs["token_ids"] = [[1, 2], [2, 3]]
    out.append(
        valid(
            "stored_bigram_pairs",
            "CONSTRUCTED: token pairs are not token ids; the store is kept and no "
            "identity is derived",
            pack([ts, [pairs], dp]),
        )
    )

    out.append(
        valid(
            "cleared_scope_undeclared",
            "CONSTRUCTED: the fieldless clear in a batch that declares no rank; global "
            "over every dimension, never defaulted to zero",
            pack([ts, [{"type": "AllBlocksCleared"}]]),
        )
    )
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("captures", nargs="+")
    a = ap.parse_args()

    records = load(a.captures)
    print(f"loaded {len(records)} captured payloads", file=sys.stderr)

    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.json"):
        old.unlink()

    valid = build_valid(records)
    constructed = build_constructed(records)
    for fx in valid + constructed:
        (OUT / f"{fx['name']}.json").write_text(json.dumps(fx, indent=1) + "\n")

    v = [f["name"] for f in valid + constructed if "events" in f["expect"]]
    m = [f["name"] for f in valid + constructed if "error" in f["expect"]]
    (OUT / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "v0",
                "producer": PRODUCER,
                "derivation": "Valid fixtures are real captured bytes; their expected events "
                "are derived independently by tools/gen-sglang-wire-corpus.py from the "
                "normative semantics, never by running the implementation under test. "
                "Malformed fixtures are deliberate mutations of real payloads.",
                "captures": a.captures,
                "valid": sorted(v),
                "malformed": sorted(m),
            },
            indent=1,
        )
        + "\n"
    )

    print(
        f"wrote {len(v)} valid + {len(m)} malformed fixtures to {OUT}", file=sys.stderr
    )


if __name__ == "__main__":
    main()
