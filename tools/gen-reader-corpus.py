#!/usr/bin/env python3
"""
Regenerate conformance/reader/ -- the reader corpus.

Every other corpus pins what a producer EMITS; nothing in them can fail a reader. This one
pins what a conforming reader must CONCLUDE: each fixture is an input stream (sealed
segments, exactly as delivered) paired with the verdict a reader must reach. The spec's
no-covering-fixture table lists the reader obligations waiting on this corpus; fixtures
land here family by family until that table is empty.

Two families so far:

- **audit**: the evict re-derivation audit (spec 2.3). The grading vocabulary is the
  reference reader's, stated in conformance/reader/README.md: every audited evict lands in
  exactly one of {agreed, mismatched, underresolved, indeterminate, unjoined}, and the
  classes partition. The first fixtures are the no-false-alarm flows the audit must NOT
  cry wolf on, then the two defect gradings it exists to catch.
- **identity**: the uniqueness property's announced failure (spec 3.1 property 5). A
  merged identity claims two parents; the verdict is the surfaced conflict count.
- **residual_zero**: the qualified zero (spec 5.7). A cross-instance zero must state what
  kind of zero it is -- a measured absence is a finding, a single-holder zero is not a
  thing that could have been observed, and a zero over blocks with no portable identity
  says nothing at all. The verdict is the qualification a conforming reader attaches.
- **staleness**: the liveness bounds (spec 5.8) and the unexplained-departure rule (spec
  2.4). Per producer run, one of {live, departed, unexplained, no_basis}, judged at the
  stream's knowledge horizon -- the latest producer-clock record anywhere in the stream,
  never wall-clock now (an archive read later must reach the same verdicts). The
  staleness threshold is the LARGER of the two declared bounds; the allowance beyond it
  is implementation-defined, so every fixture places intervals decisively -- an order of
  magnitude inside or beyond -- where no conforming allowance can flip the verdict.
- **coverage**: coverage accompanies every figure (spec 5.7, the conformance floor).
  The fixture carries a producer-clock question span; the verdict is the coverage a
  conforming reader attaches to figures over it -- "complete" (exactly 1.0: a counted
  bracket, start through stop, zero deltas, is full observation and a reader
  under-reporting it manufactures doubt) or "reduced" (strictly below 1.0: inbound
  loss inside the bracket, or a tail no stop record closed -- the crash must cost
  coverage even where staleness against the batch horizon stays silent). The verdict
  deliberately pins the DIRECTION and the two exact endpoints of the obligation, not
  any model's interior arithmetic.
- **holder_register**: the per-holder figure register, as QUESTIONS -- a holder
  (instance, dp_rank, group_idx) and an ENGINE-clock span -- each answered with the
  register a figure over them carries. One form, two obligations: the
  identity_refused lower bound (spec 2.4: "lower_bound" inside the declared window
  for the named holder, "none" for the sibling and outside it, and the declaration's
  producer-clock at_ms MUST NOT confine it per 2.6), and the multi-instance gap
  scope (spec 5.1: a missing segment_seq is a PRODUCER-level loss, so every instance
  the incarnation covered reads "indeterminate" -- including the one with no
  surviving records at all, which is exactly the instance a record-driven reader
  forgets -- while an instance covered by its own intact run reads "none").
- **absence**: the lower-bound rule (spec 5.6). The fixture carries the question --
  a producer-clock span -- and the verdict is the register a conforming reader may
  attach to absence over it: "exact" only within an observed, counted sequence (an
  agent_start through an agent_stop, both observed, with the counters establishing
  nothing was lost), "lower_bound" everywhere else -- before the producer started,
  during a gap, or outside any window it observed, the spec's three MUST-NOT cases
  verbatim.
- **uncovered**: the incarnation boundary (spec 5.3). Per instance, the exact
  uncovered intervals a conforming reader must report, as [from_ms, to_ms] pairs in
  the producer clock: the departing run's agent_stop -- or its last observation where
  no stop was received (the crash case, spec 5.3's own fallback) -- to the arriving
  run's agent_start, or its first observation where the start record was lost (a
  producer is provably running by its first record, so claiming uncovered past it
  would assert a non-observation the records refute -- spec 5.3's principle sentence
  plus 5.6). Overlapping runs leave no moment unobserved and must yield NOTHING, and
  an instance covered continuously expects the empty list -- both anti-fabrication
  pins.
- **gap_degraded**: detected gaps degrade the window (spec 5.4). The verdict is the
  sorted list of detected-gap classes present in the stream, named in the spec's own
  words -- missing_segment_seq (a hole inside an incarnation's observed sequence),
  dropped_delta (a nonzero dropped delta between heartbeats), segments_dropped (a
  declared drop overlapping the window) -- and the empty list for an intact stream,
  which pins that a reader must not fabricate gap evidence. A window whose list is
  nonempty is indeterminate; a fresh incarnation at seq zero is a restart (spec 5.2),
  and a sequence beginning above zero is absence outside observation (spec 5.6), so
  neither may appear in the list.

The clock-domain fixtures (spec 2.6, `clock_*`) declare NO family of their own,
deliberately: 2.6 adds no verdict, it constrains how every other verdict may be
computed, so its fixtures are adversarial streams graded by the families above. The
engine clock displaced a month from the producer clock must flip no staleness or audit
verdict (the domains are not the same clock); a 2 ms cross-instance overlap must not
read as simultaneity (no plausible configured allowance -- the smallest preset in use
is 50 ms -- admits it), while a ten-minute overlap must survive the allowance (an
allowance that kills real overlap is not an allowance).

Expected verdicts are derived HERE, independently, from the spec's semantics -- not by
running the reference reader. Two implementations meeting is the only arrangement in which
a passing conformance test means anything.

    python3 tools/gen-reader-corpus.py
"""

import json
import pathlib

OUT = pathlib.Path(__file__).resolve().parent.parent / "conformance" / "reader"

T0 = 1785153670000.0
RUN1 = "1785153600000-100"
RUN2 = "1785153900000-200"
RUN3 = "1785154200000-300"


def segment(incarnation, seq, records):
    """One sealed segment: the header the delivery contract demands, then the records."""
    header = {
        "kind": "segment_open",
        "at_ms": T0 - 1000.0,
        "contract_version": "1.1",
        "incarnation": incarnation,
        "segment_seq": seq,
    }
    return [header] + records


def store(instance, block, at, content=None, dp_rank=0, seq=None, reused=None):
    r = {"kind": "store", "instance_id": instance, "block_id": block, "n_tokens": 16,
         "tier": "GPU", "dp_rank": dp_rank, "group_idx": 0, "at_ms": at}
    if content is not None:
        r["content_id"] = content
    # The transport sequence of the MESSAGE this event arrived in (spec 2.3): shared by
    # every record derived from one message, monotonic only within one incarnation.
    if seq is not None:
        r["seq"] = seq
    # Only ever emitted under reuse_reporting: "labelled" (spec 2.3).
    if reused is not None:
        r["reused"] = reused
    return r


def evict(instance, block, at, content=None, dp_rank=0):
    r = {"kind": "evict", "instance_id": instance, "block_id": block, "tier": "GPU",
         "dp_rank": dp_rank, "group_idx": 0, "at_ms": at}
    if content is not None:
        r["content_id"] = content
    return r


def agent_start(at, heartbeat_secs, max_segment_secs):
    """The boot record, unkeyed egress: every field spec 2.4 requires, nothing else."""
    return {"kind": "agent_start", "at_ms": at, "agent_version": "0.2.0", "egress": "raw",
            "endpoint_count": 1, "heartbeat_secs": heartbeat_secs,
            "max_segment_secs": max_segment_secs, "max_payload_bytes": 1048576}


def _envelope(at, msgs, sources):
    return {"at_ms": at, "msgs_seen": msgs, "dropped": 0, "oversized": 0,
            "unknown_types": 0, "events_ingested": msgs, "content_unresolved": 0,
            "content_bridge_entries": 0, "content_bridge_evicted": 0,
            "publisher_restarts": 0,
            "endpoints": [{"source": s, "endpoint": f"tcp://{s}:5557",
                           "msgs_seen": msgs, "dropped": 0, "last_msg_at_ms": at}
                          for s in sources]}


def heartbeat(at, msgs, source="i0", dropped=0, sources=None, canary=None,
              reuse_reporting=None, topic=None):
    """The completeness clock: cumulative counters, required-at-zero (spec 2.4).
    `sources` names several observed instances on one producer (spec 2.4:
    endpoints[].source is the incarnation-to-instances mapping 5.1 rests on);
    `canary` is the key identity riding every heartbeat (spec 3.4);
    `reuse_reporting` is what a `store` MEANS on this stream (spec 2.3/5.9), riding every
    heartbeat for the canary's reason -- a window need not contain a start record; `topic`
    is the transport channel name, relayed verbatim and unparsed (spec 2.4)."""
    r = {"kind": "heartbeat", **_envelope(at, msgs, sources or [source])}
    if dropped:
        r["dropped"] = dropped
        r["endpoints"][0]["dropped"] = dropped
    if canary:
        r["canary"] = canary
    if reuse_reporting is not None:
        r["reuse_reporting"] = reuse_reporting
    if topic is not None:
        for e in r["endpoints"]:
            e["topic"] = topic
    return r


def insertions(countable, records=None, tokens=None):
    """The 5.9 verdict: may a reader present a count of stores as a count of insertions,
    and if so what is it. Derived from the declaration, never from the records: under
    "none" every store is an insertion; under "labelled" the reused ones are excluded;
    under "unlabelled", absence, or a value this version does not define, no such figure
    exists and a reader must not present one."""
    return {"countable": countable, "records": records, "tokens": tokens}


def segments_dropped(run, first, last, at):
    """The declared loss (spec 2.5): the producer names what its disk cap reclaimed."""
    return {"kind": "segments_dropped", "at_ms": at, "incarnation": run,
            "count": last - first + 1, "first_seq": first, "last_seq": last,
            "first": f"seg-{run}-{first}.jsonl", "last": f"seg-{run}-{last}.jsonl"}


def agent_stop(at, msgs, source="i0", reason="duration"):
    """The announced departure: silence after this record is expected (spec 2.4)."""
    return {"kind": "agent_stop", "reason": reason, **_envelope(at, msgs, [source])}


# The steady producer whose records place the knowledge horizon 10_000 seconds past the
# quiet producer's last record -- ~33x a 300-second bound, decisive under any conforming
# allowance. Its own declared cadence (heartbeat_secs=7200) is honored by construction:
# gaps of ~5_060 seconds against a 7_200-second bound.
def horizon_producer():
    return segment(RUN2, 0, [
        agent_start(T0, heartbeat_secs=7200, max_segment_secs=14400),
        heartbeat(T0 + 5_060_000.0, 40, source="i1"),
        heartbeat(T0 + 10_120_000.0, 80, source="i1")])


def identity_refused(at, instance, refused, win_start, win_end, dp_rank=0, group_idx=0):
    """The declared capacity loss (spec 2.4): a refusal count over an ENGINE-clock
    window, riding a record whose own at_ms is the PRODUCER clock -- two domains on
    one record, named apart and never compared."""
    return {"kind": "identity_refused", "at_ms": at, "instance_id": instance,
            "dp_rank": dp_rank, "group_idx": group_idx, "refused": refused,
            "window_start_ms": win_start, "window_end_ms": win_end}


def audit_verdict(**per_instance):
    """The audit verdict, derived from the spec's rules: strictly-prior join on the full
    holder scope plus block_id; agreement includes matching absence; a lost promise grades
    underresolved only within one producer run; cross-run and value-less joins are
    indeterminate; no prior store is unjoined. Classes partition the audited count."""
    zero = {"audited": 0, "agreed": 0, "mismatched": 0, "underresolved": 0,
            "indeterminate": 0, "unjoined": 0}
    return {i: {**zero, **v, "audited": sum(v.values())} for i, v in per_instance.items()}


FIXTURES = [
    # --- 5.4: seq narrows a degraded span, and only where the bracket is sound ----------
    ("seq_narrows_the_degraded_span_to_its_bracket",
     "a dropped delta localizes a loss no better than the interval between two "
     "heartbeats. With seq on the records, the discontinuity sits between two observed "
     "numbers in one incarnation, so only that bracket is degraded and the facts outside "
     "it survive a loss they cannot have been part of",
     [segment(RUN1, 0, [
         heartbeat(T0, 10),
         store("i0", "b1", T0 + 100.0, "c1", seq=41),
         store("i0", "b2", T0 + 200.0, "c2", seq=42),
         store("i0", "b3", T0 + 300.0, "c3", seq=44),
         store("i0", "b4", T0 + 400.0, "c4", seq=45),
         heartbeat(T0 + 500.0, 14, dropped=1)])],
     {"gap_degraded": ["dropped_delta"],
      "gap_span": {"narrowed": True, "start_ms": T0 + 200.0, "end_ms": T0 + 300.0}}),

    ("seq_across_an_incarnation_boundary_does_not_narrow",
     "seq is monotonic only within an incarnation, so a bracket spanning a restart "
     "compares numbers drawn from two different sequences. Narrowing on it would "
     "exonerate a span nothing observed -- the whole interval stays degraded",
     [segment(RUN1, 0, [
         heartbeat(T0, 10),
         store("i0", "b1", T0 + 100.0, "c1", seq=41)]),
      segment(RUN2, 0, [
         store("i0", "b2", T0 + 200.0, "c2", seq=3),
         heartbeat(T0 + 300.0, 12, dropped=1)])],
     {"gap_degraded": ["dropped_delta"], "gap_span": {"narrowed": False}}),

    ("a_bracket_missing_seq_does_not_narrow",
     "narrowing needs both sides. One record carrying no seq leaves no bracket to "
     "narrow to, and a reader that narrowed to the nearest numbered pair would be "
     "choosing a span the stream never delimited",
     [segment(RUN1, 0, [
         heartbeat(T0, 10),
         store("i0", "b1", T0 + 100.0, "c1", seq=41),
         store("i0", "b2", T0 + 200.0, "c2"),
         store("i0", "b3", T0 + 300.0, "c3", seq=44),
         heartbeat(T0 + 400.0, 13, dropped=1)])],
     {"gap_degraded": ["dropped_delta"], "gap_span": {"narrowed": False}}),

    # --- 5.9: a store count is an insertion count only where the producer says so -------
    ("reuse_none_makes_every_store_an_insertion",
     "the producer declares its engine never announces reuse as a store, so the records "
     "mean what they appear to mean and the count is available",
     [segment(RUN1, 0, [
         heartbeat(T0, 10, reuse_reporting="none"),
         store("i0", "b1", T0 + 100.0, "c1"),
         store("i0", "b2", T0 + 200.0, "c2")])],
     {"insertions": insertions(True, records=2, tokens=32)}),

    ("reuse_labelled_excludes_the_reused_records",
     "the engine announces reuse and the producer can tell it apart, so the labelled "
     "records are excluded from the insertion figure. They are not discarded: a reuse is "
     "direct evidence a resident block was matched, which nothing else in the stream says",
     [segment(RUN1, 0, [
         heartbeat(T0, 10, reuse_reporting="labelled"),
         store("i0", "b1", T0 + 100.0, "c1"),
         store("i0", "b1", T0 + 200.0, "c1", reused=True),
         store("i0", "b2", T0 + 300.0, "c2")])],
     {"insertions": insertions(True, records=2, tokens=32)}),

    ("reuse_unlabelled_forbids_an_insertion_count",
     "the engine announces reuse in a shape nothing distinguishes. Summing these records "
     "would count a block once per announcement, so the figure would climb with how "
     "EFFECTIVE the cache is -- highest on the fleet with least waste. No such figure "
     "exists, and a reader must not present one",
     [segment(RUN1, 0, [
         heartbeat(T0, 10, reuse_reporting="unlabelled"),
         store("i0", "b1", T0 + 100.0, "c1"),
         store("i0", "b1", T0 + 200.0, "c1")])],
     {"insertions": insertions(False)}),

    ("reuse_undeclared_is_not_none",
     "silence is not the safe-sounding case. A producer that declared nothing has not "
     "said its stores are insertions, and reading absence as a declaration is exactly "
     "how an unknown becomes a measurement",
     [segment(RUN1, 0, [
         heartbeat(T0, 10),
         store("i0", "b1", T0 + 100.0, "c1")])],
     {"insertions": insertions(False)}),

    ("reuse_unrecognized_reads_as_unlabelled",
     "a value this version does not define was added by a later one to describe a case "
     "this reader cannot model, so the one thing known about it is that the reader does "
     "not know. It reads as unlabelled -- never as none, and never by ignoring the field, "
     "which would restore the very miscount the declaration exists to prevent",
     [segment(RUN1, 0, [
         heartbeat(T0, 10, reuse_reporting="sampled_at_source"),
         store("i0", "b1", T0 + 100.0, "c1")])],
     {"insertions": insertions(False)}),

    ("a_window_takes_the_weakest_reuse_declaration_it_contains",
     "declarations are per producer and a window may span several. Mixing them would "
     "apply one producer's none to another's records, which that producer never claimed",
     [segment(RUN1, 0, [
         heartbeat(T0, 10, reuse_reporting="none"),
         store("i0", "b1", T0 + 100.0, "c1")]),
      segment(RUN2, 0, [
         heartbeat(T0 + 200.0, 10, source="i1", reuse_reporting="unlabelled"),
         store("i1", "b2", T0 + 300.0, "c2")])],
     {"insertions": insertions(False)}),

    ("audit_re_store_after_eviction",
     "store, evict, re-store, evict again: both evicts grade against their own store and "
     "agree. The delete-on-evict producer path in miniature, and the first flow a "
     "permanent alarm must never cry wolf on",
     [segment(RUN1, 0, [
         store("i0", "b1", T0, "c1"), evict("i0", "b1", T0 + 100.0, "c1"),
         store("i0", "b1", T0 + 200.0, "c1"), evict("i0", "b1", T0 + 300.0, "c1")])],
     {"audit": audit_verdict(i0={"agreed": 2})}),

    ("audit_evict_before_store_is_unjoined",
     "an evict before any store (a warm cache the producer never saw stored), and a "
     "same-instant store+evict pair (one batch stamps one timestamp, so order is "
     "unknowable): both fall to unjoined rather than being graded against a future or a "
     "guess",
     [segment(RUN1, 0, [
         evict("i0", "b1", T0), store("i0", "b1", T0 + 100.0, "c1"),
         evict("i0", "b2", T0 + 200.0), store("i0", "b2", T0 + 200.0, "c2")])],
     {"audit": audit_verdict(i0={"unjoined": 2})}),

    ("audit_restart_mid_flight_is_indeterminate",
     "store written by one producer run, evict by the next: the fresh run legitimately "
     "resolves nothing it did not see stored, so the absent content_id is expected -- "
     "indeterminate, never a lost promise. An unattributed segment (no run identity) "
     "grades the same way: unknown provenance cannot support a same-run claim",
     [segment(RUN1, 0, [store("i0", "b1", T0, "c1")]),
      segment(RUN2, 0, [evict("i0", "b1", T0 + 100.0)])],
     {"audit": audit_verdict(i0={"indeterminate": 1})}),

    ("audit_offload_and_scope",
     "the same block on two tiers grades both evicts against the latest store (content "
     "identity is tier-invariant), while the same engine hash on another dp_rank is "
     "another cache entirely: rank 1's evict finds no rank-1 store and stays unjoined "
     "rather than borrowing rank 0's resolution",
     [segment(RUN1, 0, [
         store("i0", "b1", T0, "c1"),
         {**store("i0", "b1", T0 + 100.0, "c1"), "tier": "CPU"},
         evict("i0", "b1", T0 + 200.0, "c1"),
         {**evict("i0", "b1", T0 + 300.0, "c1"), "tier": "CPU"},
         evict("i0", "b1", T0 + 400.0, dp_rank=1)])],
     {"audit": audit_verdict(i0={"agreed": 2, "unjoined": 1})}),

    ("audit_contradiction_alarms_naming_the_instance",
     "the defect class the audit exists to catch: an evict carrying an identity the raw "
     "stream contradicts. Graded per instance so the alarm names the offender and only "
     "the offender; the healthy instance's agreement stands beside it",
     [segment(RUN1, 0, [
         store("i0", "b1", T0, "c1"), evict("i0", "b1", T0 + 100.0, "WRONG"),
         store("i1", "b1", T0, "c1"), evict("i1", "b1", T0 + 100.0, "c1")])],
     {"audit": audit_verdict(i0={"mismatched": 1}, i1={"agreed": 1})}),

    ("audit_lost_promise_is_underresolved",
     "same run stored it with an identity; the evict carries none. The producer held the "
     "promise and lost it (a capacity refusal, an over-released clear, a defect) -- "
     "declared-missing rather than silent-wrong, surfaced as underresolved. Matching "
     "absence, by contrast, is agreement: a store that could not chain makes an evict "
     "that cannot resolve",
     [segment(RUN1, 0, [
         store("i0", "b1", T0, "c1"), evict("i0", "b1", T0 + 100.0),
         store("i0", "b2", T0 + 200.0), evict("i0", "b2", T0 + 300.0)])],
     {"audit": audit_verdict(i0={"underresolved": 1, "agreed": 1})}),

    ("audit_unattributed_recovery_supports_no_same_run_claim",
     "an unattributed recovered segment (spec 4.3): the marker takes the header position, "
     "the records belong to an instance and to no sequence, and a store inside one cannot "
     "support a same-run claim -- the later evict without an identity grades "
     "indeterminate, never as a lost promise",
     [[{"kind": "segment_recovered", "at_ms": T0 - 500.0, "attributed": False,
        "dropped_bytes": 42},
       store("i0", "b1", T0, "c1")],
      segment(RUN2, 0, [evict("i0", "b1", T0 + 100.0)])],
     {"audit": audit_verdict(i0={"indeterminate": 1})}),

    ("zero_single_holder_is_not_a_finding",
     "one holder stored everything: cross-cache duplication is not a thing that could "
     "have been observed here at any value, and a reader must say so rather than report "
     "a measured absence",
     [segment(RUN1, 0, [store("i0", "b1", T0, "c1"), store("i0", "b2", T0 + 10.0, "c2")])],
     {"residual_zero": "single_holder"}),

    ("zero_across_comparable_holders_is_measured",
     "two holders, every block carrying a portable identity, nothing shared: a real "
     "measured absence, the zero that IS a finding",
     [segment(RUN1, 0, [store("i0", "b1", T0, "c1"), store("i1", "b2", T0 + 10.0, "c2")])],
     {"residual_zero": "measured"}),

    ("zero_with_no_portable_identity_says_nothing",
     "two holders and not one block with a content_id: the zero carries no information "
     "about duplication at all -- the state a deployment sits in until the cache turns "
     "over past whatever the producer missed by starting late",
     [segment(RUN1, 0, [store("i0", "b1", T0), store("i1", "b2", T0 + 10.0)])],
     {"residual_zero": "not_comparable"}),

    ("shared_content_is_a_positive_residual",
     "the same content on two holders under portable identity: the finding stands on its "
     "own evidence and needs no qualification",
     [segment(RUN1, 0, [store("i0", "b1", T0, "cSHARED"),
                        store("i1", "b9", T0 + 10.0, "cSHARED")])],
     {"residual_zero": "positive"}),

    ("incarnation_is_an_opaque_token",
     "the incarnation is equality-comparable and NOTHING else (spec 4.2): this one has "
     "none of the reference layout's structure, and every verdict must come out exactly "
     "as it would under a well-formed token -- a reader that parses structure out of the "
     "token fails here first",
     [segment("opaque.token=rev.7", 0, [
         store("i0", "b1", T0, "c1"), evict("i0", "b1", T0 + 100.0, "c1")])],
     {"audit": audit_verdict(i0={"agreed": 1})}),

    ("identity_collision_claims_two_parents",
     "the uniqueness property's announced failure (spec 3.1 property 5): one content_id "
     "reached through two chains claims two parents. A conforming reader surfaces the "
     "contradiction as a count -- here exactly one conflicted identity -- and must not "
     "fold the claims into one edge, because the fold is what would make a collision "
     "invisible",
     [segment(RUN1, 0, [
         store("i0", "p1", T0, "cp1"),
         store("i0", "p2", T0 + 10.0, "cp2"),
         {**store("i0", "b1", T0 + 20.0, "cMERGED"), "parent_id": "p1"},
         {**store("i0", "b2", T0 + 30.0, "cMERGED"), "parent_id": "p2"}])],
     {"parent_conflicts": 1}),

    ("staleness_silence_without_a_stop_is_unexplained",
     "a producer declares its bounds (larger: 300 s), heartbeats, then falls silent for "
     "10_000 s of stream knowledge -- ~33x the bound, decisive under any conforming "
     "allowance -- with no agent_stop: unexplained (spec 2.4, the absence IS the signal). "
     "The second producer's records place the horizon; a reader judging against "
     "wall-clock now instead of the stream's knowledge horizon grades IT stale too, and "
     "fails here",
     [segment(RUN1, 0, [
         agent_start(T0, heartbeat_secs=60, max_segment_secs=300),
         heartbeat(T0 + 60_000.0, 10),
         heartbeat(T0 + 120_000.0, 20)]),
      horizon_producer()],
     {"staleness": {RUN1: "unexplained", RUN2: "live"}}),

    ("staleness_a_stop_makes_the_same_silence_a_departure",
     "byte-for-byte the silence of the unexplained fixture, but the last record is an "
     "agent_stop: an announced departure stays departed at any later horizon (spec 2.4). "
     "The pair pins that the verdict turns on the stop record and on nothing else",
     [segment(RUN1, 0, [
         agent_start(T0, heartbeat_secs=60, max_segment_secs=300),
         heartbeat(T0 + 60_000.0, 10),
         agent_stop(T0 + 120_000.0, 20)]),
      horizon_producer()],
     {"staleness": {RUN1: "departed", RUN2: "live"}}),

    ("staleness_is_judged_against_the_larger_bound",
     "heartbeat_secs=60 but max_segment_secs=7200, an OBSERVED 60 s heartbeat cadence, "
     "and then 2_000 s of silence: ~33x past the heartbeat bound and the observed "
     "cadence alike, well inside the larger declared bound. Spec 5.8 makes the declared "
     "bounds the entire basis and sets the threshold at the LARGER one, so the verdict "
     "is live -- a reader alarming on the heartbeat bound, or on the cadence it "
     "observed, fails here. The producer missing its own heartbeat cadence is a "
     "producer defect, and a different fact from staleness",
     [segment(RUN1, 0, [
         agent_start(T0, heartbeat_secs=60, max_segment_secs=7200),
         heartbeat(T0 + 60_000.0, 10),
         heartbeat(T0 + 120_000.0, 20)]),
      segment(RUN2, 0, [
          agent_start(T0, heartbeat_secs=1800, max_segment_secs=3600),
          heartbeat(T0 + 1_060_000.0, 40, source="i1"),
          heartbeat(T0 + 2_120_000.0, 80, source="i1")])],
     {"staleness": {RUN1: "live", RUN2: "live"}}),

    ("canary_split_key_material_is_not_a_measured_zero",
     "two producers, two canaries, and nothing on the wire that relates them -- the "
     "testimony that once could is exactly what 3.4 forbids. Identities under "
     "different keys cannot match at any overlap, so the zero describes the "
     "provisioning, not the traffic: split_key_space. A reader that folds the two "
     "spaces on any heuristic grades this a measured absence and fails -- the fold "
     "is what would let one mis-provisioned node silence the alarm fleet-wide",
     [segment(RUN1, 0, [
         heartbeat(T0 + 1_000.0, 5, canary="c0ffee11c0ffee11c0ffee11c0ffee11"),
         store("i0", "1a2b3c", T0 + 10_000.0, "aa1111")]),
      segment(RUN2, 0, [
          heartbeat(T0 + 1_000.0, 5, source="i1",
                    canary="deadbeefdeadbeefdeadbeefdeadbeef"),
          store("i1", "4d5e6f", T0 + 11_000.0, "bb2222")])],
     {"residual_zero": "split_key_space"}),

    ("clock_the_domains_never_meet",
     "the engine clock sits THIRTY DAYS from the producer clock in one stream -- "
     "legal, because the two domains are not the same clock (spec 2.6). The producer "
     "is live at its own horizon (a reader whose horizon ingests engine stamps grades "
     "this healthy agent a month silent and fails), and the audit still grades the "
     "engine-domain pair agreed (its joins never touch the producer clock)",
     [segment(RUN1, 0, [
         agent_start(T0, heartbeat_secs=300, max_segment_secs=600),
         heartbeat(T0 + 60_000.0, 10),
         heartbeat(T0 + 120_000.0, 20),
         store("i0", "b1", T0 + 2_592_000_000.0, "c1"),
         evict("i0", "b1", T0 + 2_592_000_100.0, "c1")])],
     {"staleness": {RUN1: "live"},
      "audit": audit_verdict(i0={"agreed": 1})}),

    ("clock_a_sliver_overlap_is_not_simultaneity",
     "the same content on two instances with 2 ms of nominal overlap: two unsynced "
     "hosts cannot support a simultaneity claim at that scale, and no plausible "
     "configured skew allowance (the smallest preset in use is 50 ms, twenty-five "
     "times this sliver) admits it -- the zero is a measured absence, and a reader "
     "that omits the allowance manufactures simultaneity and reads it positive "
     "(spec 2.6's own words)",
     [segment(RUN1, 0, [
         store("i0", "bA", T0, "cS"),
         evict("i0", "bA", T0 + 300_000.0, "cS"),
         store("i1", "bB", T0 + 299_998.0, "cS"),
         evict("i1", "bB", T0 + 600_000.0, "cS")])],
     {"residual_zero": "measured"}),

    ("clock_a_robust_overlap_survives_the_allowance",
     "the same content resident on two instances for ten overlapping minutes, "
     "stores 50 ms apart: the allowance exists to weaken positives at the boundary, "
     "never to destroy real overlap -- an allowance that kills ten minutes is not an "
     "allowance, and a reader wielding one fails here (the counter-bracket to the "
     "sliver fixture)",
     [segment(RUN1, 0, [
         store("i0", "bC", T0, "cR"),
         evict("i0", "bC", T0 + 600_000.0, "cR"),
         store("i1", "bD", T0 + 50.0, "cR"),
         evict("i1", "bD", T0 + 600_050.0, "cR")])],
     {"residual_zero": "positive"}),

    ("coverage_a_counted_bracket_is_complete",
     "start through stop, zero deltas, cache facts inside: full observation, and the "
     "coverage beside any figure over the span is exactly 1.0 -- a reader that "
     "under-reports a clean bracket manufactures doubt, which is the mirror image of "
     "the confident-wrong failure 5.7 exists to prevent",
     [segment(RUN1, 0, [
         agent_start(T0, heartbeat_secs=300, max_segment_secs=600),
         store("i0", "b1", T0 + 30_000.0, "c1"),
         heartbeat(T0 + 60_000.0, 10),
         heartbeat(T0 + 120_000.0, 20),
         agent_stop(T0 + 180_000.0, 30)])],
     {"coverage": {"span_ms": [T0, T0 + 180_000.0], "verdict": "complete"}}),

    ("coverage_loss_inside_the_bracket_reduces_it",
     "the same bracket with a nonzero dropped delta: messages arrived unrecorded, "
     "and the coverage beside every figure over the span must fall strictly below "
     "1.0 -- the figure and its qualification travel together or the figure is a "
     "claim, not a measurement (spec 5.7)",
     [segment(RUN1, 0, [
         agent_start(T0, heartbeat_secs=300, max_segment_secs=600),
         store("i0", "b1", T0 + 30_000.0, "c1"),
         heartbeat(T0 + 60_000.0, 10),
         heartbeat(T0 + 120_000.0, 20, dropped=3),
         agent_stop(T0 + 180_000.0, 30)])],
     {"coverage": {"span_ms": [T0, T0 + 180_000.0], "verdict": "reduced"}}),

    ("coverage_an_unclosed_tail_reduces_it",
     "no stop record and the span runs past the last observation: the tail is "
     "unattested, and the crash must cost coverage on every figure even where "
     "staleness against the batch horizon stays silent -- end-of-file is "
     "indistinguishable from end-of-capture, but unmeasured time is unmeasured "
     "either way (spec 5.7 with 2.2's closing rule)",
     [segment(RUN1, 0, [
         agent_start(T0, heartbeat_secs=300, max_segment_secs=600),
         store("i0", "b1", T0 + 30_000.0, "c1"),
         heartbeat(T0 + 60_000.0, 10),
         heartbeat(T0 + 120_000.0, 20)])],
     {"coverage": {"span_ms": [T0, T0 + 180_000.0], "verdict": "reduced"}}),

    ("gap_scope_a_producer_level_loss_degrades_every_covered_instance",
     "one producer watching two instances (endpoints[].source names i0 AND i1), a "
     "hole in ITS sequence, and surviving records mentioning only i0: segments "
     "belong to the incarnation, so the loss belongs to everything it observed -- "
     "i1 degrades despite having no surviving records at all, which is exactly the "
     "instance a record-driven reader forgets (spec 5.1). i9, watched by its own "
     "intact run, stands. This is also the first corpus stream in which one "
     "incarnation covers several instances -- the producer-fixture half of 5.1's "
     "ledger row",
     [segment(RUN1, 0, [
         agent_start(T0, heartbeat_secs=300, max_segment_secs=600),
         heartbeat(T0 + 60_000.0, 10, sources=["i0", "i1"]),
         store("i0", "b1", T0 + 5_000.0, "c1")]),
      segment(RUN1, 2, [store("i0", "b2", T0 + 70_000.0, "c2")]),
      segment(RUN2, 0, [
          agent_start(T0, heartbeat_secs=300, max_segment_secs=600),
          heartbeat(T0 + 60_000.0, 10, source="i9"),
          store("i9", "b3", T0 + 6_000.0, "c3")])],
     {"holder_register": [
         {"instance": "i0", "dp_rank": 0, "group_idx": 0,
          "span_ms": [T0, T0 + 100_000.0], "register": "indeterminate"},
         {"instance": "i1", "dp_rank": 0, "group_idx": 0,
          "span_ms": [T0, T0 + 100_000.0], "register": "indeterminate"},
         {"instance": "i9", "dp_rank": 0, "group_idx": 0,
          "span_ms": [T0, T0 + 100_000.0], "register": "none"}]}),

    ("refused_degrades_exactly_the_named_holder_over_its_window",
     "a declared capacity loss for i0's worker 0 over [T+10s, T+20s]: figures over "
     "that holder in that window are lower bounds (spec 2.4) -- and nothing else "
     "moves. The sibling worker on the same instance stands inside the window, and "
     "the named holder stands outside it: the signal is scoped precisely so the rest "
     "of the fleet's figures can",
     [segment(RUN1, 0, [
         identity_refused(T0 + 500_000.0, "i0", 5, T0 + 10_000.0, T0 + 20_000.0),
         store("i0", "b1", T0 + 12_000.0),
         store("i0", "b2", T0 + 15_000.0, dp_rank=1)])],
     {"holder_register": [
         {"instance": "i0", "dp_rank": 0, "group_idx": 0,
          "span_ms": [T0 + 10_000.0, T0 + 20_000.0], "register": "lower_bound"},
         {"instance": "i0", "dp_rank": 1, "group_idx": 0,
          "span_ms": [T0 + 10_000.0, T0 + 20_000.0], "register": "none"},
         {"instance": "i0", "dp_rank": 0, "group_idx": 0,
          "span_ms": [T0 + 30_000.0, T0 + 40_000.0], "register": "none"}]}),

    ("refused_is_confined_by_its_window_not_its_stamp",
     "the declaration's engine-clock window is [T+10s, T+20s] while its own producer "
     "at_ms sits at T+35s, inside an innocent span: the two domains ride one record "
     "and MUST NOT be compared (spec 2.6), so the loss lives where the window says "
     "and not where the stamp does -- a reader placing the refusal by at_ms degrades "
     "the wrong span and fails both questions",
     [segment(RUN1, 0, [
         identity_refused(T0 + 35_000.0, "i0", 2, T0 + 10_000.0, T0 + 20_000.0),
         store("i0", "b1", T0 + 12_000.0)])],
     {"holder_register": [
         {"instance": "i0", "dp_rank": 0, "group_idx": 0,
          "span_ms": [T0 + 10_000.0, T0 + 20_000.0], "register": "lower_bound"},
         {"instance": "i0", "dp_rank": 0, "group_idx": 0,
          "span_ms": [T0 + 30_000.0, T0 + 40_000.0], "register": "none"}]}),

    ("absence_is_exact_within_a_counted_bracket",
     "start through stop, every counter delta zero: the producer's own accounting "
     "establishes that nothing arrived unrecorded over the span, so absence within "
     "it is a measurement, not a guess -- the one shape where 'none' may be stated "
     "exactly (spec 5.6)",
     [segment(RUN1, 0, [
         agent_start(T0, heartbeat_secs=300, max_segment_secs=600),
         heartbeat(T0 + 60_000.0, 10),
         heartbeat(T0 + 120_000.0, 20),
         agent_stop(T0 + 180_000.0, 30)])],
     {"absence": {"span_ms": [T0, T0 + 180_000.0], "register": "exact"}}),

    ("absence_before_the_producer_started_is_a_lower_bound",
     "the same counted bracket, but the question span begins 300 s before the "
     "agent_start: a reader MUST NOT state what occurred before a producer started "
     "(spec 5.6), so absence over the span is a lower bound however clean the "
     "bracket after it",
     [segment(RUN1, 0, [
         agent_start(T0, heartbeat_secs=300, max_segment_secs=600),
         heartbeat(T0 + 60_000.0, 10),
         heartbeat(T0 + 120_000.0, 20),
         agent_stop(T0 + 180_000.0, 30)])],
     {"absence": {"span_ms": [T0 - 300_000.0, T0 + 180_000.0],
                  "register": "lower_bound"}}),

    ("absence_during_a_gap_is_a_lower_bound",
     "a nonzero dropped delta inside the bracket: messages arrived that were never "
     "recorded, so 'none was lost' is exactly what the counters refuse to establish "
     "-- absence during a gap is a lower bound (spec 5.6, second MUST-NOT case)",
     [segment(RUN1, 0, [
         agent_start(T0, heartbeat_secs=300, max_segment_secs=600),
         heartbeat(T0 + 60_000.0, 10),
         heartbeat(T0 + 120_000.0, 20, dropped=3),
         agent_stop(T0 + 180_000.0, 30)])],
     {"absence": {"span_ms": [T0, T0 + 180_000.0], "register": "lower_bound"}}),

    ("absence_outside_observation_is_a_lower_bound",
     "no stop record and the question span runs 280 s past the last observation: "
     "the tail is outside any window the producer observed, and a run missing its "
     "closing endpoint cannot vouch for its own edge (spec 5.6, third MUST-NOT "
     "case)",
     [segment(RUN1, 0, [
         agent_start(T0, heartbeat_secs=300, max_segment_secs=600),
         heartbeat(T0 + 60_000.0, 10),
         heartbeat(T0 + 120_000.0, 20)])],
     {"absence": {"span_ms": [T0, T0 + 400_000.0], "register": "lower_bound"}}),

    ("uncovered_the_bracket_runs_stop_to_start",
     "the canonical 5.3 bracket: run-1 stops at T+120s, run-2 starts at T+400s, and "
     "the 280 s between are an uncovered window for i0 -- a producer observes nothing "
     "while it is not running. i1, watched continuously by its own run across the "
     "whole span, expects the empty list: coverage elsewhere is not evidence of a "
     "blind spot",
     [segment(RUN1, 0, [
         agent_start(T0, heartbeat_secs=300, max_segment_secs=600),
         heartbeat(T0 + 60_000.0, 10),
         agent_stop(T0 + 120_000.0, 20)]),
      segment(RUN2, 0, [
          agent_start(T0 + 400_000.0, heartbeat_secs=300, max_segment_secs=600),
          heartbeat(T0 + 460_000.0, 10)]),
      segment(RUN3, 0, [
          agent_start(T0, heartbeat_secs=7200, max_segment_secs=14400),
          heartbeat(T0 + 230_000.0, 40, source="i1"),
          heartbeat(T0 + 460_000.0, 80, source="i1")])],
     {"uncovered": {"i0": [[T0 + 120_000.0, T0 + 400_000.0]], "i1": []}}),

    ("uncovered_a_crash_opens_the_bracket_at_the_last_observation",
     "run-1 dies without a stop record, so the bracket opens at its LAST OBSERVATION "
     "-- spec 5.3's own fallback for the crash case. The uncovered window is exactly "
     "what nobody watched: last heartbeat to next start",
     [segment(RUN1, 0, [
         agent_start(T0, heartbeat_secs=300, max_segment_secs=600),
         heartbeat(T0 + 60_000.0, 10),
         heartbeat(T0 + 120_000.0, 20)]),
      segment(RUN2, 0, [
          agent_start(T0 + 400_000.0, heartbeat_secs=300, max_segment_secs=600),
          heartbeat(T0 + 460_000.0, 10)])],
     {"uncovered": {"i0": [[T0 + 120_000.0, T0 + 400_000.0]]}}),

    ("uncovered_a_lost_start_closes_the_bracket_at_the_first_observation",
     "run-2's segment carrying its agent_start was never delivered (a mid-run "
     "segment at seq 1 is all that survives), so the bracket closes at run-2's FIRST "
     "OBSERVATION: a producer is provably running by its first record, and claiming "
     "uncovered past it would assert a non-observation the records refute (spec "
     "5.3's principle sentence, plus 5.6)",
     [segment(RUN1, 0, [
         agent_start(T0, heartbeat_secs=300, max_segment_secs=600),
         heartbeat(T0 + 60_000.0, 10),
         agent_stop(T0 + 120_000.0, 20)]),
      segment(RUN2, 1, [
          heartbeat(T0 + 400_000.0, 10),
          heartbeat(T0 + 460_000.0, 20)])],
     {"uncovered": {"i0": [[T0 + 120_000.0, T0 + 400_000.0]]}}),

    ("uncovered_overlapping_runs_leave_no_blind_spot",
     "a blue-green handover: run-2 starts at T+150s, BEFORE run-1 stops at T+200s. "
     "No moment went unobserved, so a conforming reader reports no uncovered window "
     "-- a reader keying on 'a boundary happened' rather than 'nobody was watching' "
     "fabricates one and fails here",
     [segment(RUN1, 0, [
         agent_start(T0, heartbeat_secs=300, max_segment_secs=600),
         heartbeat(T0 + 60_000.0, 10),
         agent_stop(T0 + 200_000.0, 20)]),
      segment(RUN2, 0, [
          agent_start(T0 + 150_000.0, heartbeat_secs=300, max_segment_secs=600),
          heartbeat(T0 + 210_000.0, 10)])],
     {"uncovered": {"i0": []}}),

    ("gap_a_missing_segment_seq_degrades_the_window",
     "segments 0 and 2 of one incarnation, seq 1 never delivered: a hole inside the "
     "observed sequence is a detected gap (spec 5.4), and the window containing it is "
     "indeterminate -- the facts inside must not be classified as though the window "
     "were complete",
     [segment(RUN1, 0, [store("i0", "b1", T0, "c1")]),
      segment(RUN1, 2, [store("i0", "b2", T0 + 20_000.0, "c2")])],
     {"gap_degraded": ["missing_segment_seq"]}),

    ("gap_a_dropped_delta_between_heartbeats_degrades_the_window",
     "the completeness clock catches inbound loss: cumulative dropped moves from 0 to "
     "3 between two heartbeats, so the span lost messages and the loss cannot be "
     "localized inside it (spec 5.4). The store rides along so the stream carries "
     "cache facts the gap taints",
     [segment(RUN1, 0, [
         agent_start(T0, heartbeat_secs=60, max_segment_secs=300),
         heartbeat(T0 + 60_000.0, 10),
         store("i0", "b1", T0 + 90_000.0, "c1"),
         heartbeat(T0 + 120_000.0, 20, dropped=3)])],
     {"gap_degraded": ["dropped_delta"]}),

    ("gap_a_declared_drop_overlapping_the_window_degrades_it",
     "the producer names what its disk cap reclaimed (spec 2.5): segments 0..2 are "
     "gone by declaration, and a declared loss a reader ignores is worse than an "
     "undetected one -- the window it overlaps is indeterminate (spec 5.4)",
     [segment(RUN1, 3, [
         segments_dropped(RUN1, 0, 2, T0),
         store("i0", "b1", T0 + 10_000.0, "c1")])],
     {"gap_degraded": ["segments_dropped"]}),

    ("gap_an_intact_stream_is_not_degraded",
     "contiguous sequence, zero counter deltas, no declarations: no detected gap "
     "exists, and a conforming reader must not fabricate one -- a restart at seq zero "
     "(spec 5.2) in a second incarnation rides along and is not a gap either",
     [segment(RUN1, 0, [
         agent_start(T0, heartbeat_secs=60, max_segment_secs=300),
         heartbeat(T0 + 60_000.0, 10),
         heartbeat(T0 + 120_000.0, 20)]),
      segment(RUN1, 1, [store("i0", "b1", T0 + 130_000.0, "c1")]),
      segment(RUN2, 0, [store("i1", "b2", T0 + 140_000.0, "c9")])],
     {"gap_degraded": []}),

    ("staleness_without_declared_bounds_has_no_basis",
     "a mid-run segment (seq 1; the segment carrying the agent_start is not in the "
     "stream): heartbeats, then silence past any bound a reader might guess. The two "
     "declared bounds are the ENTIRE basis for calling a producer stale (spec 5.8), and "
     "unobserved declarations are outside the stream's knowledge (spec 5.6) -- so a "
     "conforming reader refuses the staleness verdict rather than inventing a threshold",
     [segment(RUN1, 1, [
         heartbeat(T0 + 60_000.0, 10),
         heartbeat(T0 + 120_000.0, 20)]),
      horizon_producer()],
     {"staleness": {RUN1: "no_basis", RUN2: "live"}}),
]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.json"):
        old.unlink()
    for name, note, segments, expect in FIXTURES:
        fx = {
            "fixture_version": "v0",
            "name": name,
            "note": note,
            "segments": segments,
            "expect": expect,
        }
        (OUT / f"{name}.json").write_text(json.dumps(fx, indent=1) + "\n")
    print(f"wrote {len(FIXTURES)} reader fixtures to {OUT}")


if __name__ == "__main__":
    main()
