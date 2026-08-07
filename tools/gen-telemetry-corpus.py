#!/usr/bin/env python3
"""
Regenerate conformance/telemetry/ -- the Compute contract.

Compute is now a stateless transducer: one event in, one record out, no state consulted and
none kept. That makes this corpus much smaller than it was, and the shrinkage is the point.
Most of the old fixtures (resident_cap_overflow, evicted_cap_ageout, eviction_recompute,
cross_instance_residual, no_false_sharing) existed to exercise working sets that were deleted
because nothing consumed them and they were the agent's only super-linear cost. The
classifications they described are the aggregator's, computed from this record stream.

What is left to pin is exactly what a transducer can get wrong: field mapping, absent-not-null,
identity scope, and order.

As with the wire and lifecycle corpora, expected records are derived here from the documented
semantics rather than by running the implementation under test.

    python3 tools/gen-telemetry-corpus.py
"""

import json
import pathlib

OUT = pathlib.Path(__file__).resolve().parent.parent / "conformance" / "telemetry"

PROVENANCE = {
    "gpu": "fixture",
    "vllm_version": "0.26.0",
    "event_schema_version": "vllm-0.26.0-map",
}

# Wall-clock milliseconds. The old corpus used ts: 1.0 everywhere, which is how a
# seconds-vs-milliseconds error stayed invisible in two repos at once.
T0 = 1785153670000.0


def record(ev):
    """The record a faithful transducer emits for one event. Written from
    the specification's normative text, not from the reference producer's code."""
    r = dict(PROVENANCE)
    r["instance_id"] = ev["source"]
    # Scope: block events always carry both dimensions (they ride every observed wire
    # event, so absence in a fixture is shorthand for the single-worker zero). A Cleared's
    # shape is ASSUMED -- never observed live -- so its scope is transduced as declared: a
    # dimension the event does not carry is omitted from the record, because the producer
    # holds no scope claim there and an invented zero would read as one.
    if ev["type"] == "Cleared":
        if ev.get("dp_rank") is not None:
            r["dp_rank"] = ev["dp_rank"]
        if ev.get("group_idx") is not None:
            r["group_idx"] = ev["group_idx"]
    else:
        r["dp_rank"] = ev.get("dp_rank", 0)
        r["group_idx"] = ev.get("group_idx", 0)
    r["at_ms"] = ev["at_ms"]

    if ev["type"] == "Stored":
        r["kind"] = "store"
        # identities are STRINGS on the wire, in every mode (spec 2.2): a JSON-number id
        # above 2^53 is silently corrupted by any double-precision reader
        r["block_id"] = str(ev["block_hash"])
        # Three states kept three: a named parent, an explicit unknown, or a root by
        # absence. Collapsing unknown into absent would claim the block begins a chain.
        if ev.get("parent_unknown"):
            r["parent_unknown"] = True
        elif ev.get("parent_hash") is not None:  # absent, not null, at a prefix root
            r["parent_id"] = str(ev["parent_hash"])
        r["n_tokens"] = ev["block_size"]
        r["tier"] = ev.get("medium")
        if ev.get("extra_keys") is not None:
            r["extra_keys"] = ev["extra_keys"]
        if ev.get("lora_id") is not None:
            r["lora_id"] = ev["lora_id"]
        if ev.get("lora_name") is not None:
            r["lora_name"] = ev["lora_name"]
        if ev.get("spec_kind") is not None:
            r["spec_kind"] = ev["spec_kind"]
        # absent where the publisher declared nothing, like spec_kind and unlike tier
        if ev.get("locality") is not None:
            r["locality"] = ev["locality"]
        # the second identity space, emitted beside the engine's, absent where undetermined
        if ev.get("content_id") is not None:
            r["content_id"] = str(ev["content_id"])
    elif ev["type"] == "Removed":
        r["kind"] = "evict"
        r["block_id"] = str(ev["block_hash"])
        r["tier"] = ev.get("medium")
        if ev.get("locality") is not None:
            r["locality"] = ev["locality"]
        if ev.get("content_id") is not None:
            r["content_id"] = str(ev["content_id"])
    elif ev["type"] == "Cleared":
        # ONE scope-level record. The wire does not enumerate the cleared blocks, so neither
        # does the agent; expansion is the consumer's job against its own residency model.
        r["kind"] = "clear"
        r["scope"] = "all"
        # a clear's absent tier is a SCOPE declaration (global over tiers), omitted like an
        # undeclared dp_rank -- unlike a block record's tier, whose unknown VALUE is null
        if ev.get("medium") is not None:
            r["tier"] = ev["medium"]
    else:
        raise ValueError(ev["type"])
    return r


def stored(source, h, at_ms, **kw):
    e = {
        "source": source,
        "type": "Stored",
        "at_ms": at_ms,
        "block_hash": h,
        "block_size": 16,
        "medium": "GPU",
        "spec_kind": "full_attention",
    }
    e.update(kw)
    return e


def removed(source, h, at_ms, **kw):
    e = {"source": source, "type": "Removed", "at_ms": at_ms, "block_hash": h, "medium": "GPU"}
    e.update(kw)
    return e


def cleared(source, at_ms, **kw):
    # Scope explicit by default: the constructed wire shape carries group_idx (and the batch
    # its dp_rank), so the common fixture is a fully scoped clear. Pass dp_rank=None /
    # group_idx=None for the assumed-shape case where the wire declares no scope.
    e = {
        "source": source,
        "type": "Cleared",
        "at_ms": at_ms,
        "medium": "GPU",
        "dp_rank": 0,
        "group_idx": 0,
    }
    e.update(kw)
    return {k: v for k, v in e.items() if v is not None or k == "medium"}


# Real-shaped hashes: above i64::MAX, because that is ordinary traffic.
H1 = 10841253731892115301
H2 = 12955354968414679641
H3 = 16032592773066255487

FIXTURES = [
    ("prefix_chain",
     "a root store and its chained child: parent_id is ABSENT at the root and present on the "
     "child, so the prefix edge reaches the aggregator intact",
     [stored("a", H1, T0), stored("a", H2, T0 + 100.0, parent_hash=H1)]),

    ("evict_and_restore",
     "store, evict, store again. The agent holds no state, so the second store is just a store "
     "-- calling it a recompute is an aggregator-side self-join over this stream",
     [stored("a", H1, T0), removed("a", H1, T0 + 100.0), stored("a", H1, T0 + 200.0)]),

    ("clear_is_scope_level",
     "AllBlocksCleared becomes exactly ONE record with scope=all, never a per-block expansion, "
     "and never synthesized from any local view",
     [stored("a", H1, T0), stored("a", H2, T0 + 10.0), cleared("a", T0 + 20.0)]),

    ("clear_tier_undeclared",
     "a clear whose wire shape named no tier: the record omits it, because an absent tier "
     "on a clear is a scope declaration (global over tiers) like an undeclared dp_rank -- "
     "not an unknown per-block value, which is what a block record's null tier states",
     [stored("a", H1, T0), cleared("a", T0 + 10.0, medium=None)]),

    ("clear_scope_undeclared",
     "a clear whose wire shape declared NO scope: the record omits dp_rank and group_idx, "
     "because the producer holds no scope claim there and a defaulted zero would be one. The "
     "clear's shape is assumed (never observed live), and absence fails toward declared: the "
     "producer releases globally for the named tier, and the reader must close every holder "
     "of this instance and tier -- never just holder zero",
     [stored("a", H1, T0, dp_rank=0), stored("a", H2, T0 + 10.0, dp_rank=1),
      cleared("a", T0 + 20.0, dp_rank=None, group_idx=None)]),

    ("same_hash_distinct_dp_ranks",
     "IDENTITY SCOPE: the same block hash from two data-parallel workers is two different "
     "blocks, because their caches are physically independent. Collapsing them under a bare "
     "hash is what erased cross-worker duplication",
     [stored("a", H1, T0, dp_rank=0), stored("a", H1, T0 + 10.0, dp_rank=1)]),

    ("same_hash_distinct_groups",
     "IDENTITY SCOPE: KV cache groups hash independently, so the same hash in two groups is "
     "two blocks. A hybrid-attention model runs several",
     [stored("a", H1, T0, group_idx=0),
      stored("a", H1, T0 + 10.0, group_idx=1, spec_kind="sliding_window")]),

    ("same_hash_distinct_instances",
     "the same hash on two instances: genuine duplication, and the join the aggregator exists "
     "to make. The agent states the fact and classifies nothing",
     [stored("a", H1, T0), stored("b", H1, T0 + 10.0)]),

    ("salted_partition",
     "cache_salt arrives in extra_keys on the block where it enters the chain, and is carried "
     "as `extra_keys` -- absent on the blocks that follow, exactly as the wire said it",
     [stored("a", H1, T0, extra_keys=["tenant-AAAA"]), stored("a", H2, T0 + 10.0)]),

    ("lora_labelled",
     "a LoRA-served block: both lora_id and lora_name ride the record, the only per-request "
     "tenant key the engine offers besides the salt",
     [stored("a", H1, T0, lora_id=7, lora_name="customer-adapter")]),

    ("tier_absent_stays_null",
     "an event with no medium: tier is null rather than omitted, because the field is always "
     "present on cache records and only its value is unknown",
     [stored("a", H1, T0, medium=None), removed("a", H1, T0 + 10.0, medium=None)]),

    ("remote_locality_is_carried",
     "LOCALITY: a block the publisher reports as REMOTE is not its own copy -- it lives in a "
     "store the publisher can merely reach. Two publishers reporting one remote block are very "
     "likely describing ONE copy, so a consumer that counts remote residency as per-holder "
     "residency invents duplication. Carried as-said on both store and evict; the agent states "
     "which side of the line the engine put the block on and classifies nothing. Never seen in "
     "the capture: KVCacheEvent sets omit_defaults, so a field left at its default is invisible "
     "on the wire, and our single-GPU run left this one unset",
     [stored("a", H1, T0, locality="LOCAL"),
      stored("a", H2, T0 + 10.0, locality="REMOTE"),
      removed("a", H2, T0 + 20.0, locality="REMOTE")]),

    ("parent_unknown_is_not_a_root",
     "an UNKNOWN parent rides its own field and never becomes an absent parent_id. Absence "
     "means 'begins a prefix chain', which the aggregator treats as vacuously proven and "
     "therefore contributing -- so collapsing unknown into absent would fabricate roots and "
     "inflate residual mass. Arises when a stored run has blocks skipped (sliding-window, "
     "Mamba), where list order stops implying parenthood",
     [stored("a", H1, T0, parent_unknown=True)]),

    ("content_id_rides_beside_the_engine_id",
     "TWO IDENTITY SPACES on one record. block_id is the engine's, comparable only inside the "
     "process that computed it, because vLLM seeds every chain from a per-process random root "
     "unless PYTHONHASHSEED is fixed. content_id is derived from what the block contains and is "
     "comparable across the fleet. Both are carried; a consumer must never join across them, "
     "and content_id is ABSENT where the tap could not honestly derive one",
     [stored("a", H1, T0, content_id=11111111111111111111),
      removed("a", H1, T0 + 10.0, content_id=11111111111111111111),
      stored("a", H2, T0 + 20.0)]),

    ("same_content_distinct_engine_ids",
     "THE POINT OF CONTENT IDENTITY. Two instances hold the same prefix, and their ENGINE ids "
     "differ -- which is the normal case, not a corner: vLLM seeds every prefix chain from "
     "os.urandom(32) unless PYTHONHASHSEED is fixed, so two processes serving identical prompts "
     "produce disjoint id spaces. Keyed on block_id this is two unrelated blocks and the "
     "duplication reads as zero; keyed on content_id it is one prefix held twice. The agent "
     "states both ids and joins nothing",
     [stored("a", H1, T0, content_id=9999999999999999999),
      stored("b", H2, T0 + 10.0, content_id=9999999999999999999)]),

    ("order_is_preserved",
     "a mixed sequence across two instances: one record per event, in arrival order, nothing "
     "reordered or coalesced",
     [stored("a", H1, T0), stored("b", H2, T0 + 1.0), removed("a", H1, T0 + 2.0),
      cleared("b", T0 + 3.0), stored("a", H3, T0 + 4.0)]),
]


def main():
    for old in OUT.glob("*.json"):
        old.unlink()
    for name, note, events in FIXTURES:
        records = [record(e) for e in events]
        counts = {}
        for r in records:
            counts[r["kind"]] = counts.get(r["kind"], 0) + 1
        fx = {
            "fixture_version": "v0",
            "provenance": PROVENANCE,
            "name": name,
            "note": note,
            "events": events,
            "expect": {"record_counts": dict(sorted(counts.items())), "records": records},
        }
        (OUT / f"{name}.json").write_text(json.dumps(fx, indent=1) + "\n")
    print(f"wrote {len(FIXTURES)} fixtures to {OUT}")


if __name__ == "__main__":
    main()
