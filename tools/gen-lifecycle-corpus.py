#!/usr/bin/env python3
"""
Regenerate conformance/lifecycle/records.json.

Same rule as the wire corpus: the expected records are derived here, independently, from the
documented record shapes -- not by running the Rust builders. Two implementations meeting is the
only arrangement in which a passing conformance test means anything.

Nothing here is captured, because lifecycle records describe the tap process rather than the
engine: there is no wire to capture them from. What IS pinned from the capture is the timestamp
SCALE -- wall-clock milliseconds. The previous corpus used `at_ms: 100.0`, and that is precisely
why a 1000x unit error (engine seconds emitted under a millisecond field name) was invisible to
every test in both repos.

    python3 tools/gen-lifecycle-corpus.py
"""

import hashlib
import hmac
import json
import pathlib

OUT = pathlib.Path(__file__).resolve().parent.parent / "conformance" / "lifecycle"

PROVENANCE = {
    "gpu": "fixture",
    "vllm_version": "0.26.0",
    "event_schema_version": "vllm-0.26.0-map",
}
AGENT_VERSION = "0.0.0-fixture"

# Wall-clock milliseconds, from the capture window. Deliberately at real scale.
T0 = 1785153670000.0


def base(kind, at_ms):
    r = {}
    r["kind"] = kind
    r["at_ms"] = at_ms
    return r


def with_stats(rec, s):
    """The envelope stats block, in the order lifecycle.rs writes it. Optionals follow the
    house rule: absent, not null."""
    rec["msgs_seen"] = s["msgs_seen"]
    rec["dropped"] = s["dropped"]
    rec["oversized"] = s["oversized"]
    if s.get("noraw_scanned") is not None:
        rec["noraw_scanned"] = s["noraw_scanned"]
    rec["unknown_types"] = s["unknown_types"]
    rec["events_ingested"] = s["events_ingested"]
    # Content-identity accounting. ALWAYS present, never absent-when-zero: these are
    # completeness figures like dropped, and a consumer must be able to tell "nothing
    # unresolved" from "this build does not report it". Absence would read as the latter.
    rec["content_unresolved"] = s["content_unresolved"]
    rec["content_bridge_entries"] = s["content_bridge_entries"]
    rec["content_bridge_evicted"] = s["content_bridge_evicted"]
    rec["publisher_restarts"] = s["publisher_restarts"]
    # the canary rides heartbeats too: an analysis window need not contain a start record, and
    # the check has to be available wherever the comparison is made
    if s.get("canary") is not None:
        rec["canary"] = s["canary"]
    # What a `store` MEANS on this stream (spec 2.3, 5.9), riding heartbeats for exactly the
    # canary's reason. It describes the ENGINE rather than the traffic, so it never varies
    # within an incarnation -- and its absence is not "none": a producer that declared
    # nothing has not said its stores are insertions.
    if s.get("reuse_reporting") is not None:
        rec["reuse_reporting"] = s["reuse_reporting"]
    if s.get("rss_bytes") is not None:
        rec["rss_bytes"] = s["rss_bytes"]
    rec["endpoints"] = [
        {k: v for k, v in e.items() if v is not None} for e in s["endpoints"]
    ]
    return rec


# The fleet canary. Derived here from the reference construction (pinned by the pseudonym vectors) rather
# than transcribed from the Rust: HMAC over the key file's own nonce, under its key, in the
# pinned canonical form. Two instances provisioned from one key file emit this identically, and
# no other instance can produce it -- which is the only positive proof that a fleet's pseudonyms
# share a space at all.
TEST_KEY = b"infertap-conformance-test-key!!!infertap-conformance-nonce!!!!!!"
CANARY_CONTEXT = b"infertap:canary:v1"


def canary(epoch):
    key, nonce = TEST_KEY[:32], TEST_KEY[32:]
    msg = CANARY_CONTEXT + b"\x00" + epoch.to_bytes(4, "big") + b"\x00" + nonce.hex().encode()
    return hmac.new(key, msg, hashlib.sha256).hexdigest()[:32]


START_CONFIG = {
    "endpoint_count": 2,
    "max_payload_bytes": 16777216,
    "heartbeat_secs": 60,
    "max_segment_secs": 300,
    "egress": "pseudonymized",
    "key_epoch": 3,
    "canary": canary(3),
    # The declaration rides the boot record AND every heartbeat. Here it is "unlabelled":
    # the reference engine announces cache reuse with the same event it uses for a fresh
    # insertion, in a shape nothing distinguishes, so the honest value is the one that
    # forbids an insertion count rather than the one that would flatter it.
    "reuse_reporting": "unlabelled",
}

HEARTBEAT_STATS = {
    "canary": canary(3),
    # rides all three lifecycle kinds, exactly as the canary does and for the same reason
    "reuse_reporting": "unlabelled",
    "msgs_seen": 10,
    "dropped": 1,
    "oversized": 0,
    "noraw_scanned": 42,
    # an engine kind this build does not model: counted, never fatal
    "unknown_types": 2,
    "events_ingested": 37,
    # a tap that started against a warm cache: some runs chained from parents it never saw
    # stored, and those blocks carry no cross-node identity. Falls to zero as the cache turns
    # over, and until it does every duplication figure over this span is a lower bound.
    "content_unresolved": 5,
    "content_bridge_entries": 128,
    "content_bridge_evicted": 0,
    "publisher_restarts": 1,
    "rss_bytes": 20480000,
    "endpoints": [
        {
            "source": "i0",
            "endpoint": "tcp://127.0.0.1:5557",
            "msgs_seen": 10,
            "dropped": 1,
            "last_msg_at_ms": T0 + 1500.0,
            # relayed VERBATIM and unparsed: deployments encode real identity here (several
            # conventions put the served model and the pod in it), but the conventions are
            # the deployment's, so recognizing one is a reader's business and a producer
            # that split it would be publishing an interpretation as a fact
            "topic": "kv@10.0.1.7:8000@meta-llama/Llama-3.1-8B-Instruct",
        },
        # nothing seen yet on this one: last_msg_at_ms is ABSENT, not null
        {
            "source": "i1",
            "endpoint": "tcp://127.0.0.1:5558",
            "msgs_seen": 0,
            "dropped": 0,
            "last_msg_at_ms": None,
        },
    ],
}

# The stop case omits noraw_scanned and rss_bytes: a keyless run on a platform that exposes no
# RSS. Absent-not-null is pinned deliberately on both.
STOP_STATS = dict(
    HEARTBEAT_STATS,
    msgs_seen=12,
    dropped=1,
    events_ingested=44,
    noraw_scanned=None,
    rss_bytes=None,
)

# The capacity signal: instance-scoped, unlike the bracket, because it declares a loss for one
# observed holder -- the identity mechanism's segments_dropped. window_* bound the refused
# stores on the ENGINE clock; at_ms is the producer clock like every record the producer emits
# about itself. Dyadic fractions on the window, so the pin is exact across JSON.
REFUSAL = {
    "instance_id": "i0",
    "dp_rank": 0,
    "group_idx": 1,
    "refused": 2048,
    "window_start_ms": T0 + 1000.25,
    "window_end_ms": T0 + 41000.75,
}


def identity_refused_case(at_ms):
    expect = base("identity_refused", at_ms)
    expect.update(REFUSAL)
    return {
        "kind": "identity_refused",
        "at_ms": at_ms,
        "refusal": REFUSAL,
        "expect": expect,
    }


def main():
    start = base("agent_start", T0)
    start["agent_version"] = AGENT_VERSION
    start.update(START_CONFIG)

    heartbeat = with_stats(base("heartbeat", T0 + 60000.0), HEARTBEAT_STATS)

    stop = base("agent_stop", T0 + 90000.0)
    stop["reason"] = "signal"
    stop = with_stats(stop, STOP_STATS)

    corpus = {
        "corpus": "lifecycle",
        "schema_version": "v0",
        "note": (
            "Pins the three lifecycle record kinds byte-for-byte: agent_start (boot + config "
            "summary), heartbeat (cumulative envelope stats + per-endpoint sub-stats), "
            "agent_stop (reason + closing stats). Absent-not-null is pinned deliberately: the "
            "stop case omits noraw_scanned and rss_bytes, and one heartbeat endpoint omits "
            "last_msg_at_ms (nothing seen yet). Lifecycle records carry no instance_id "
            "(agent-scoped) and no block ids (the pseudonymizer leaves them unmapped). "
            "Timestamps are at real wall-clock scale on purpose -- the previous corpus used "
            "at_ms: 100.0, which is why a seconds-vs-milliseconds error stayed invisible. "
            "capacity_cases pins the identity_refused signal separately: instance-scoped by "
            "design (it declares a loss for one observed holder), with engine-clock window "
            "fields beside a producer-clock at_ms, named apart."
        ),
        "provenance": PROVENANCE,
        "agent_version": AGENT_VERSION,
        "cases": [
            {"kind": "agent_start", "at_ms": T0, "config": START_CONFIG, "expect": start},
            {
                "kind": "heartbeat",
                "at_ms": T0 + 60000.0,
                "stats": HEARTBEAT_STATS,
                "expect": heartbeat,
            },
            {
                "kind": "agent_stop",
                "at_ms": T0 + 90000.0,
                "reason": "signal",
                "stats": STOP_STATS,
                "expect": stop,
            },
        ],
        "capacity_cases": [identity_refused_case(T0 + 60000.0)],
    }
    (OUT / "records.json").write_text(json.dumps(corpus, indent=1) + "\n")
    print(f"wrote {OUT / 'records.json'}")


if __name__ == "__main__":
    main()
