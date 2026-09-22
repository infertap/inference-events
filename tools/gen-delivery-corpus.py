#!/usr/bin/env python3
"""Regenerate conformance/delivery/records.json.

`layout.json` states the delivery contract as a directory and a naming convention. This pins the
other half: the RECORDS that describe the delivery layer -- `segment_open`, `segment_recovered`,
`segments_dropped` -- byte-for-byte, plus one realistic sealed segment as a consumer receives it.

They were contractual and unpinned, which is a combination that costs something. The analyzer
modelled two record families, cache and lifecycle, and all three of these fell to its unknown
branch: counted as contract drift, their fields flattened into a leftovers map, and in the case
of `segments_dropped` -- a DECLARED data loss -- readable by nothing. That was possible because
no fixture either repo tests against had ever contained one. Prose in `layout.json` said the
identity of a segment lives in its first record; nothing made a consumer read one.

The tap's own writer is asserted against this file by `tests/delivery_records.rs`, so the
fixture is what the producer actually emits rather than what this script believes it emits.

    python3 tools/gen-delivery-corpus.py
"""

import json
import pathlib

OUT = pathlib.Path(__file__).resolve().parent.parent / "conformance" / "delivery"

PROVENANCE = {
    "gpu": "fixture",
    "vllm_version": "0.26.0",
    "event_schema_version": "vllm-0.26.0-map",
}

# Wall-clock milliseconds, at real scale, matching the lifecycle corpus's window.
T0 = 1785153670000.0

# `<run_start_unix_ms>-<pid>`, per layout.json's `incarnation_pattern`. Fixed here; the real
# writer mints it from the clock and the pid, and the conformance test asserts the SHAPE of what
# it mints rather than this literal -- a fixture cannot pin a pid.
INCARNATION = "1785153670000-4242"


def base(kind, at_ms):
    """The two fields every record carries (spec 2.2).

    Provenance is not among them: it is stated once on the segment header, which builds itself
    from PROVENANCE directly."""
    r = {}
    r["kind"] = kind
    r["at_ms"] = at_ms
    return r


def segment_open(seq, at_ms):
    """The first record of every segment, fsync'd before any data record.

    Identity lives here rather than in the filename: a crash leaves `active.jsonl` behind, and
    the recovering process must file it under the incarnation that WROTE it, not the one that
    FOUND it. Filing it under the finder corrupts both sequences, and because both outcomes
    produce well-formed files nothing downstream would ever notice.
    """
    r = base("segment_open", at_ms)
    # the header states everything the segment declares once: the contract it conforms to, its
    # identity, and the producer's provenance, which a reader applies to every record in it
    r.update(PROVENANCE)
    r["contract_version"] = json.loads((pathlib.Path(__file__).resolve().parent.parent / "schema/records.schema.json").read_text())["x-contract-version"]
    # 5.8: the liveness bounds are declared on every header. They are the entire basis on which a
    # reader may call this producer stale, and an analysis window need not contain a start record.
    r["heartbeat_secs"] = 60
    r["max_segment_secs"] = 300
    # 3.3, since 1.5: the epoch scoping this segment's identity space, declared where every other
    # run-constant fact is
    r["key_epoch"] = 3
    # 2.7: what the producer's traffic is for, in the operator's vocabulary, declared once
    # here; a reader applies it to every record in the segment.
    r["workload_class"] = "agentic"
    r["incarnation"] = INCARNATION
    r["segment_seq"] = seq
    return r


def segment_recovered(attributed, dropped_bytes, at_ms):
    """What a recovery states in-band rather than leaving it to be inferred from a filename.

    `attributed` true is a trailer inside the recovered segment: the header survived, the torn
    tail was discarded, and the segment ships under its own identity. `attributed` false means
    the header did not survive: the file was never durably written (a conforming producer
    fsyncs the header before any record), so the producer unlinks it and declares the discard
    -- the whole file's size -- in the first segment of its OWN incarnation (spec 4.3, since
    1.11). Nothing headerless ships.
    """
    r = base("segment_recovered", at_ms)
    r["attributed"] = attributed
    r["dropped_bytes"] = dropped_bytes
    return r


def segments_dropped(first_seq, last_seq, at_ms, incarnation=INCARNATION):
    """Declared loss: past its disk cap the tap drops the oldest sealed segments.

    Recorded twice on purpose -- here in-band with the range, and structurally as a gap in
    `segment_seq` among the segments that did arrive. The second matters because sustained
    pressure can consume the very segment carrying the first, and a bounded declared loss that
    erases its own evidence is an unbounded silent one.

    ONE RECORD PER INCARNATION whose segments were dropped. The ring scans the whole directory,
    so one enforcement pass can reclaim a previous run's segments too -- and `incarnation` here
    names the run whose DATA IS GONE, not the process that did the dropping. The dropper is
    readable from the enclosing segment's own header. Grouping is also what makes a range
    meaningful: within one incarnation the dropped set is contiguous, and across incarnations it
    never is.

    Both representations ride along. `first`/`last` are the FILENAMES unlinked -- the faithful
    record, and what reconciles against a shipper's logs. `first_seq`/`last_seq` are the same
    range as integers, because layout.json's own principle is that correctness must not bind to
    filenames, and a consumer computing a gap from names alone has to parse one.
    """
    r = base("segments_dropped", at_ms)
    r["incarnation"] = incarnation
    r["count"] = last_seq - first_seq + 1
    r["first"] = f"seg-{incarnation}-{first_seq}.jsonl"
    r["last"] = f"seg-{incarnation}-{last_seq}.jsonl"
    r["first_seq"] = first_seq
    r["last_seq"] = last_seq
    return r


def heartbeat(at_ms):
    """The envelope, mid-stream, exactly where a real segment carries it.

    Here for the ENDPOINTS COLUMN above all. `endpoints` is the record model's ONLY nested
    column -- a list of the closed element -- and this segment's Parquet twin is therefore
    the only place the corpus can pin its SHIPPED shape. Until this line existed it pinned
    nothing: no delivery fixture carried a heartbeat, and the reference analyzer shipped a
    reader that spoke endpoints in a form no real Parquet carries -- every conformance suite
    green, every real capture's roster empty. The two elements are shaped to exercise the
    element's optionals in both directions: one entry with `last_msg_at_ms` and `topic`
    present, one silent entry with both absent.
    """
    r = base("heartbeat", at_ms)
    r["msgs_seen"] = 3
    r["dropped"] = 0
    r["oversized"] = 0
    r["unknown_types"] = 0
    r["events_ingested"] = 3
    r["content_unresolved"] = 0
    r["content_bridge_entries"] = 2
    r["content_bridge_evicted"] = 0
    r["publisher_restarts"] = 0
    r["endpoints"] = [
        {"source": "i0", "endpoint": "tcp://127.0.0.1:5557", "msgs_seen": 3, "dropped": 0,
         "last_msg_at_ms": at_ms - 5.0, "publisher_restarts": 0, "topic": "kv@pod-a@model-x"},
        {"source": "i0", "endpoint": "tcp://127.0.0.1:5558", "msgs_seen": 0, "dropped": 0},
    ]
    return r


def cache_record(kind, block_id, at_ms, **extra):
    r = base(kind, at_ms)
    r["instance_id"] = "i0"
    r["block_id"] = block_id
    r.update(extra)
    return r


def main():
    cases = [
        {
            "note": "opens every segment; carries the identity the filename merely echoes",
            "expect": segment_open(0, T0),
        },
        {
            "note": "an attributable orphan: header survived, tail torn and discarded",
            "expect": segment_recovered(True, 137, T0 + 1000.0),
        },
        {
            "note": "an unattributable file: the header did not survive, so the whole file "
            "(4096 bytes here) is discarded and declared by the recovering incarnation in its "
            "own first segment; the span it covered was already uncovered",
            "expect": segment_recovered(False, 4096, T0 + 2000.0),
        },
        {
            "note": "declared loss -- segments 4 through 6 dropped under the disk cap. The "
            "magnitudes are illustrative; the shapes are the contract.",
            "expect": segments_dropped(4, 6, T0 + 3000.0),
        },
        {
            "note": "the same pass reclaiming a PREVIOUS run's segments: a second record, under "
            "that run's incarnation rather than the dropping process's. One record per "
            "incarnation is what keeps a range describable.",
            "expect": segments_dropped(11, 14, T0 + 3000.0, incarnation="1785153600000-1817"),
        },
    ]

    # One sealed segment exactly as a consumer receives it: the header first, then a mixed
    # record stream. Consumers need this shape and not just the record shapes, because the
    # property that matters at ingest is FILE-scoped -- every row in this file was written by
    # the incarnation its first record names, and that is what makes the identity joinable.
    # The records after the first five exist to make reader defects REACHABLE (2026-08-22):
    # a clear carries no block id, a holder_reset is not a cache fact, an evict carries a
    # resolved content_id beside one that carries none, and a second instance carries
    # dp_rank and group_idx. A corpus that omits a kind cannot fail a reader that
    # mishandles it.
    i1 = {"instance_id": "i1", "dp_rank": 1, "group_idx": 2}
    segment = {
        "note": "one sealed segment as shipped. The header is first and every later record "
        "belongs to its incarnation; that containment is the contract, not a convention of "
        "this fixture. parquet_twin names the same records in the shipped Parquet form "
        "(spec 2.1), generated from this object by tools/gen-parquet-twin.py. The records "
        "after the first five exist to make reader defects REACHABLE: a clear (a cache fact "
        "with no block id), a holder_reset (not a cache fact at all), an evict with a "
        "resolved content_id beside one without, and a second instance carrying dp_rank and "
        "group_idx. A corpus that omits a kind cannot fail a reader that mishandles it.",
        "filename": f"seg-{INCARNATION}-0.jsonl",
        "parquet_twin": f"seg-{INCARNATION}-0.parquet",
        "incarnation": INCARNATION,
        "lines": [
            segment_open(0, T0),
            cache_record("store", "8f2b1c04a7d93e15", T0 + 10.0, n_tokens=16, tier="gpu"),
            cache_record("store", "b3e77a190c4f2d68", T0 + 20.0, n_tokens=16, tier="gpu"),
            heartbeat(T0 + 25.0),
            cache_record("evict", "8f2b1c04a7d93e15", T0 + 30.0),
            {**cache_record("store", "c41d9f8a2b6e0357", T0 + 40.0, n_tokens=16, tier="gpu"),
             **i1, "content_id": "11111111111111111111",
             "parent_id": "8f2b1c04a7d93e15", "spec_kind": "full_attention"},
            {**cache_record("evict", "c41d9f8a2b6e0357", T0 + 50.0, tier="gpu"),
             **i1, "content_id": "11111111111111111111"},
            {**base("clear", T0 + 60.0), **i1, "scope": "all", "tier": "gpu"},
            {**base("holder_reset", T0 + 70.0), **i1, "boundary_ms": T0 + 65.0},
        ],
    }

    # The recovering incarnation's first segment exactly as a consumer receives it: its own
    # header first, then the declaration of the headerless file it discarded, then its
    # ordinary records. Nothing of the discarded file ships; the declaration is all a reader
    # gets, and all it can act on.
    recovering = {
        "note": "the first segment of an incarnation that found and discarded a headerless "
        "file: segment_open first, the unattributed segment_recovered second, then the "
        "run's own records. The discarded span was already uncovered; the declaration "
        "changes no coverage figure.",
        "filename": "seg-1785153900000-200-0.jsonl",
        "incarnation": "1785153900000-200",
        "lines": [
            {**segment_open(0, T0 + 230_000.0), "incarnation": "1785153900000-200"},
            segment_recovered(False, 4096, T0 + 230_001.0),
            cache_record("store", "8f2b1c04a7d93e15", T0 + 230_010.0, n_tokens=16, tier="gpu"),
        ],
    }

    corpus = {
        "corpus": "delivery-records",
        "schema_version": "v0",
        "note": (
            "The records that describe the DELIVERY layer rather than the cache. layout.json "
            "pins the directory and the naming convention; this pins the records, which were "
            "contractual and unpinned -- so a consumer modelled two record families, counted "
            "all three of these as unknown drift, and could not read a declared data loss. "
            "Every kind here must be a kind a consumer models."
        ),
        "provenance": PROVENANCE,
        "incarnation_pattern": "<run_start_unix_ms>-<pid>",
        "cases": cases,
        "segment": segment,
        "recovering_segment": recovering,
    }
    (OUT / "records.json").write_text(json.dumps(corpus, indent=1) + "\n")
    print(f"wrote {OUT / 'records.json'}")


if __name__ == "__main__":
    main()
