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
    r["contract_version"] = "1.3"
    # 5.8: the liveness bounds are declared on every header. They are the entire basis on which a
    # reader may call this producer stale, and an analysis window need not contain a start record.
    r["heartbeat_secs"] = 60
    r["max_segment_secs"] = 300
    r["incarnation"] = INCARNATION
    r["segment_seq"] = seq
    return r


def segment_recovered(attributed, dropped_bytes, at_ms):
    """The trailer a recovery appends, stating what happened in-band rather than leaving it to
    be inferred from a filename.

    `attributed` false means the crash took the header before it reached disk, so the file seals
    as `orphan-<ms>.jsonl` and its records belong to an instance and to no sequence. A consumer
    ingests them for measurement and must treat the span as coverage-indeterminate.
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
            "note": "an unattributable orphan: the crash took the header, so it belongs to no "
            "sequence and its span is coverage-indeterminate",
            "expect": segment_recovered(False, 0, T0 + 2000.0),
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
    segment = {
        "note": "one sealed segment as shipped. The header is first and every later record "
        "belongs to its incarnation; that containment is the contract, not a convention of "
        "this fixture.",
        "filename": f"seg-{INCARNATION}-0.jsonl",
        "incarnation": INCARNATION,
        "lines": [
            segment_open(0, T0),
            cache_record("store", "8f2b1c04a7d93e15", T0 + 10.0, n_tokens=16, tier="gpu"),
            cache_record("store", "b3e77a190c4f2d68", T0 + 20.0, n_tokens=16, tier="gpu"),
            cache_record("evict", "8f2b1c04a7d93e15", T0 + 30.0),
        ],
    }

    # An unattributed orphan exactly as a consumer receives it: the recovery marker TAKES
    # THE HEADER POSITION, because the segment claims no identity and a reader dispatching
    # on the first record must learn what the file is without a second pass. Its records
    # remain attributable to an instance and to no sequence.
    orphan = {
        "note": "an unattributed orphan as shipped: segment_recovered first, then the "
        "records that survived. No segment_open, no incarnation, no continuity claim -- "
        "the span it covers is coverage-indeterminate by construction.",
        "filename": "orphan-1785153680000.jsonl",
        "lines": [
            segment_recovered(False, 42, T0 + 2000.0),
            cache_record("store", "8f2b1c04a7d93e15", T0 + 10.0, n_tokens=16, tier="gpu"),
            cache_record("evict", "8f2b1c04a7d93e15", T0 + 30.0),
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
        "orphan_segment": orphan,
    }
    (OUT / "records.json").write_text(json.dumps(corpus, indent=1) + "\n")
    print(f"wrote {OUT / 'records.json'}")


if __name__ == "__main__":
    main()
