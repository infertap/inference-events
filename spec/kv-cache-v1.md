# KV cache event semantics, v1

A wire and file contract for observing key/value cache behaviour in inference engines.

- [1. Scope and status](#1-scope-and-status): [Terms](#11-terms)
- [2. Record format](#2-record-format): [encoding](#21-encoding) · [common fields](#22-common-fields) · [cache records](#23-cache-records) · [lifecycle records](#24-producer-lifecycle-records) · [delivery records](#25-delivery-records) · [clock domains](#26-clock-domains)
- [3. Identity](#3-identity): [two spaces](#31-two-identity-spaces) · [scope](#32-scope) · [key epochs](#33-key-epochs) · [the canary](#34-the-canary-and-fleet-key-consistency)
- [4. Delivery layout](#4-delivery-layout): [sealed segments](#41-sealed-segments) · [incarnations](#42-incarnations) · [orphans](#43-orphans)
- [5. Continuity and coverage](#5-continuity-and-coverage): the reader's conformance floor, §5.1–§5.9
- [6. Versioning](#6-versioning): [`contract_version`](#61-contract_version) · [the mixed-fleet law](#62-the-mixed-fleet-law)
- [7. Out of scope](#7-out-of-scope)
- [8. Conformance checklists](#8-conformance-checklists-informative) (informative)
- [Non-normative notes](#non-normative-notes): fixture citations, verification

## 1. Scope and status

This document standardizes the facts a **producer** emits about an inference engine's KV cache, and
the rules a **reader** must follow to interpret them without inventing figures the data does not
support.

Per-instance cache metrics discard four properties inside the serving process, before anything is
exported: **identity** (which block, not how many), **cause** (why a miss occurred), **simultaneity**
(what other caches held at that moment), and **history** (the events rather than a pre-aggregated
summary). None can be recovered by sampling more often, because the information is destroyed at the
source. This contract preserves all four by emitting per-block facts with a stable identity, an
explicit scope, and an accounting of what was and was not observed.

**Boundary.** This contract governs the **facts layer**: records, identity, delivery, and
continuity. It stops before **classification**, which is the interpretation of those facts into
categories and costs. Classification is governed separately and versioned separately, under a
`semantics_version` that this contract does not define. A reader may change how it classifies
without any change here, and must be able to reclassify stored facts when it does.

**Who the producer is.** Conformance is a property of the record stream, not of the process that
writes it. An engine MAY emit records natively and be the producer; an adapter observing an
engine's native telemetry MAY be the producer for it. The `vllm-wire` corpus documents one such
adapter mapping, from a real engine's native events to conforming records.

**Status.** v1.1 draft. Verified against a reference producer's code and conformance corpora on
2026-08-06.

**Conventions.** Normative requirements use the key words of BCP 14 (RFC 2119, as clarified by
RFC 8174); they are normative only in uppercase. A reference written `§4.2` is to a numbered
section of this document. Section anchors are derived from heading text, so headings are stable
identifiers: renaming one breaks inbound citations and is treated with the care of a field
rename. Footnotes marked *non-normative* are commentary; each cites the conformance fixture that
would fail an implementation violating the requirement it hangs from.

### 1.1 Terms

| term | meaning |
|---|---|
| **producer** | the process that writes the record stream (either shape above) |
| **reader** | any consumer interpreting the stream; bound by §5 |
| **record** | one JSON object on one line (§2.1) |
| **segment** | the unit of exchange; only a *sealed* segment is complete (§4.1) |
| **incarnation** | one run of one producer, an opaque token (§4.2) |
| **instance** | one engine process, named by the operator as `instance_id` (§3.2) |
| **holder** | `(instance_id, dp_rank, group_idx)` — the scope within which a `block_id` is an identity (§3.2) |
| **window** | a time span, in one clock domain (§2.6), that a figure is computed over |
| **figure** | any derived number a reader emits; every figure carries its coverage (§5.7) |
| **coverage** | the fraction of a window the stream demonstrably observed (§5.7) |

## 2. Record format

### 2.1 Encoding

A record stream is **JSON Lines**: one JSON object per line, UTF-8 encoded, each line terminated by
a single newline. There is no envelope and no framing.

A producer MUST NOT emit a record larger than **1 MiB**. A reader MAY reject a longer line as
malformed and MUST be able to bound its parser accordingly. [^size]

A producer MUST emit exactly one JSON object per line. A reader MUST treat an unparseable line as
described in §5.5.

### 2.2 Common fields

Every record carries:

| field | type | presence | meaning |
|---|---|---|---|
| `kind` | string | required | which record this is (§2.3 to §2.5) |
| `at_ms` | number | required | epoch milliseconds. See §2.6 for clock domains |

Every record carries **provenance**: an operator-supplied set of top-level fields identifying the
source in the operator's own vocabulary. Provenance keys are not specified here. Conventionally a
stream carries the engine version and a hardware label. A reader MUST carry unrecognized provenance
fields rather than discarding them, and MUST NOT validate them against anything.

**Provenance is a property of the producer RUN and is declared once.** A producer MUST emit
provenance on the segment's `segment_open` record and MUST NOT emit provenance keys on any other
record. A reader MUST apply a segment's `segment_open` provenance to every record in that segment.

**This reads a 1.1 segment without special handling, which is why it can be a MUST.** Under 1.1 a
producer stamped provenance onto every record — including `segment_open`, because the header is a
record like any other. The header therefore already carries it in every segment ever written, so a
reader that takes provenance from the header alone is correct on 1.1 and 1.2 alike and simply
ignores the copies 1.1 repeats. Retention makes this concrete: a reader meets segments written by
the previous producer for as long as it keeps them, and it needs no second code path to read them.

The reason is measured, not aesthetic. Provenance is byte-identical on every record of a run, and
on the published corpus it is **32% of the record stream** at 80 bytes on a 251-byte mean record.
`--max-disk-bytes`-style local retention bounds a producer's own buffer, so a constant repeated per
record trades directly against the completeness that bound exists to protect. This is the same
reasoning that keeps `incarnation` in the header (§4.2) rather than on every record it describes.

**Absent is not null.** An optional field that does not apply is omitted. A reader MUST distinguish
*absent* from *present with a zero or empty value*. Several fields below mean different things in
those two states. [^absent]

**Type vocabulary.** JSON has a single numeric type, so this document distinguishes two:

- **`integer`** is a whole number. A reader MAY parse it into an integer type of the stated width.
  Counters, sizes, ranks and sequence numbers are integers.
- **`number`** may carry a fractional part and MUST be parsed as a floating point value. Only
  timestamps are numbers: `at_ms` and `last_msg_at_ms`. An engine that publishes fractional
  seconds yields fractional milliseconds after conversion, so a reader that parses a timestamp as
  an integer truncates it.

A field is one type. This document contains no field that is one type in some circumstances and
another in others.

**Identity fields are always strings**, in every mode, and a producer MUST NOT emit one as a JSON
number. Engine block identities are 64-bit values, and many real ones exceed what an IEEE 754
double represents exactly, so any reader whose JSON numbers are doubles (including every
JavaScript reader) silently corrupts them. A single type also keeps the field expressible as a
schema; a field typed as number-or-string pushes a branch into every reader and cannot be
validated. [^idtype]

### 2.3 Cache records

#### `store`

A block entered a cache.

| field | type | presence | meaning |
|---|---|---|---|
| `kind` | `"store"` | required | |
| `at_ms` | number | required | engine clock |
| `instance_id` | string | required | the engine process holding this cache, named by the operator (§3.2) |
| `block_id` | string | required | engine-local identity (§3.1) |
| `n_tokens` | integer | required | tokens the block holds |
| `tier` | string | required | storage tier, for example `GPU` |
| `dp_rank` | integer | optional | the data parallel worker within that instance, which holds its own independent cache (§3.2) |
| `group_idx` | integer | optional | the cache group within that worker. Groups hash independently (§3.2) |
| `content_id` | string | optional | portable identity (§3.1). Absent where the producer could not derive one |
| `parent_id` | string | optional | the preceding block in this block's prefix chain |
| `parent_unknown` | boolean | optional | see below |
| `locality` | string | optional | `LOCAL` or `REMOTE`, relative to the publishing holder |
| `extra_keys` | array of string | optional | additional inputs to this block's identity beyond its tokens, for example a cache salt or a multimodal content hash. Operator controlled text, so each element is pseudonymized independently |
| `lora_id` | integer | optional | adapter identifier |
| `lora_name` | string | optional | adapter name |
| `spec_kind` | string | optional | attention kind, for example `full_attention` |
| `spec_sliding_window` | integer | optional | the sliding-window size of this block's cache group, where the engine declares one |
| `reused` | boolean | optional | this record reports a block already cached rather than a fresh insertion. Only under `reuse_reporting: "labelled"` (§2.4) |
| `seq` | integer | optional | transport sequence of the message that carried this event (below) |

**Parent has three states, and a reader MUST distinguish all three.** `parent_id` present names the
parent. `parent_id` absent asserts that this block is a **root**, meaning it begins a prefix chain.
`parent_unknown: true` asserts that the producer could not determine the parent, and is neither of
the above. A reader MUST NOT treat `parent_unknown` as equivalent to an absent `parent_id`. [^parent]

A root has no parent by definition, so treating unknown ancestry as a root invents chain structure
the producer never claimed and inflates any figure built on it.

**Locality.** A `REMOTE` block is reachable by the publishing holder, not held by it. A reader MUST
NOT count a `REMOTE` block as that holder's own copy. Absent means the producer declared nothing
about locality. [^locality]

**Runs.** An engine event MAY describe a contiguous run of consecutive blocks in which each block's
parent is its predecessor. A producer MUST emit one `store` record per block with the chain already
resolved. A reader never observes runs. [^run]

**`seq` localizes a loss.** Where the producer's transport numbers its messages, `seq` carries that
number for the message this record's event arrived in. It is monotonic within
`(instance_id, incarnation)` and shared by every record derived from one message, so it identifies
a message rather than a record. A producer that has no sequenced transport MUST omit it rather than
synthesize one. Its use is §5.4.

**A `store` does not always mean an insertion, and only the producer knows which.** Some engines
announce a block *reused* from cache with the same event they use to announce one newly inserted,
and emit them in a shape a consumer cannot tell apart. A reader that sums `n_tokens` over `store`
records on such a stream is not measuring inserted tokens — it is measuring inserted tokens plus
every reuse of them, which climbs with cache *effectiveness*.

The producer declares which case it is in, once, via `reuse_reporting` (§2.4), and the three states
are not collapsible:

- **`"none"`** — this engine does not announce reuse as a `store`. Every `store` is an insertion.
- **`"labelled"`** — it does, and the producer can tell them apart. Each such record carries
  `reused: true`, and a producer MUST NOT emit `reused` under any other declaration.
- **`"unlabelled"`** — it does, and the producer cannot tell them apart. No record can say which it
  is, because no fact distinguishes them.

The set is closed. Like every closed set here it is carried as a string, because JSON has no enum
type and a field is one type (§2.2) — the same shape as `egress`.

**Absence of the declaration is not `"none"`, and neither is a value a reader does not recognize.**
A producer that does not declare has not told the reader that its stores are insertions, and a
reader MUST NOT assume the safe-sounding case from silence — that is the one reading that turns an
unknown into a measurement. A reader MUST treat an unrecognized `reuse_reporting` value exactly as
it treats `"unlabelled"`, never as `"none"` and never by ignoring the field: a value this contract
does not define was added by a later version to describe a case the reader cannot model, so the
one thing known about it is that the reader does not know. This is the rule §5.3 already applies to
an unknown `scope`, one field over. §5.9 states the obligation under each state. [^reuse]

*Example (informative), from `telemetry/lora_labelled`. The `gpu`, `vllm_version` and
`event_schema_version` fields are provenance (§2.2) and ride every record in these examples:*

```json
{"kind": "store", "at_ms": 1785153670000.0, "instance_id": "a", "dp_rank": 0, "group_idx": 0,
 "block_id": "10841253731892115301", "n_tokens": 16, "tier": "GPU",
 "lora_id": 7, "lora_name": "customer-adapter", "spec_kind": "full_attention"}
```

#### `evict`

A block left a cache.

| field | type | presence | meaning |
|---|---|---|---|
| `kind` | `"evict"` | required | |
| `at_ms` | number | required | engine clock |
| `instance_id` | string | required | the engine process whose cache the block left (§3.2) |
| `block_id` | string | required | engine-local identity (§3.1), the same value its `store` carried |
| `tier` | string | optional | storage tier the block left. A block offloaded to another tier is evicted from the one it left |
| `dp_rank` | integer | optional | the data parallel worker within that instance (§3.2) |
| `group_idx` | integer | optional | the cache group within that worker (§3.2) |
| `content_id` | string | optional | portable identity (§3.1), resolved by the producer as described below |
| `locality` | string | optional | `LOCAL` or `REMOTE`, relative to the publishing holder |
| `seq` | integer | optional | transport sequence of the message that carried this event |

`content_id` on an evict is resolved by the producer at capture time, through state built when
the block was stored. Because `block_id` rides both stores and evicts, the stream also lets a
reader re-derive that resolution independently — join each evict to its most recent prior
`store` on the full holder scope plus `block_id` and compare. A reader SHOULD run that audit
continuously and surface any disagreement naming the instance; it MUST NOT be required to (the
join is an audit, not the identity mechanism, and a reader without it still conforms). [^audit]

*Example (informative), from `telemetry/content_id_rides_beside_the_engine_id`:*

```json
{"kind": "evict", "at_ms": 1785153670010.0, "instance_id": "a", "dp_rank": 0, "group_idx": 0,
 "block_id": "10841253731892115301", "tier": "GPU", "content_id": "11111111111111111111"}
```

#### `clear`

Every block in a named scope left at once.

| field | type | presence | meaning |
|---|---|---|---|
| `kind` | `"clear"` | required | |
| `at_ms` | number | required | engine clock |
| `instance_id` | string | required | the engine process holding this cache, named by the operator (§3.2) |
| `scope` | string | required | what was cleared, for example `all` |
| `dp_rank` | integer | optional | the data parallel worker the clear applies to; **absent means the wire declared none and the clear is global across workers** (§3.2 and the note below) |
| `group_idx` | integer | optional | as `dp_rank`, for cache groups |
| `tier` | string | optional | storage tier the clear applied to; **absent means the clear is global across tiers** |
| `seq` | integer | optional | as `store` |

An absent scope field on a `clear` **declares the clear unbounded** in that dimension; it is not
an unknown value. (A block record's absent `tier` is the opposite: a per-block fact the producer
did not state.) A reader MUST treat each absent dimension as covering all its values. [^cleartier]

A `clear` carries no block identity. A reader MUST close every residency it is tracking for the
named holder and scope at `at_ms`, rather than matching identities. [^clear]

> **This record's shape is constructed, not observed — but no longer by analogy.** The reference
> engine exposes no route that triggers a cache reset, so no live instance has been captured.
> Until 2026-08-09 the fields here were inferred from the two observed record kinds, and the
> companion wire fixtures accordingly gave the engine's clear event a tier and a group. Reading
> the reference producer's own event definition settles it: that event declares **no fields at
> all**, so on that engine a clear is global over every dimension except the data-parallel rank,
> which rides the batch envelope rather than the event.
>
> The record schema above keeps `tier` and `group_idx` optional regardless: another engine may
> declare them, and this contract is not one engine's. What narrowed is the companion corpus,
> not the requirement — and the requirement was already pointing this way. A producer that finds
> a scope dimension absent MUST treat the clear as global over it rather than defaulting it:
> over-releasing fails visibly into the unresolved counter, under-releasing fails silently.
> [^constructed]
>
> The general rule this instance illustrates: a capture bounds what may be **asserted**, not what
> exists. Where an event cannot be captured at all, the producer's definition is the next-best
> evidence, and it beats analogy with a neighbouring event every time.

*Example (informative), from `telemetry/clear_is_scope_level`:*

```json
{"kind": "clear", "at_ms": 1785153670020.0, "instance_id": "a", "dp_rank": 0, "group_idx": 0,
 "scope": "all", "tier": "GPU"}
```

### 2.4 Producer lifecycle records

These describe the producer process, not a cache. They carry no `instance_id`, because one producer
MAY observe several instances.

#### `agent_start`

| field | type | presence | meaning |
|---|---|---|---|
| `kind` | `"agent_start"` | required | |
| `at_ms` | number | required | producer clock |
| `agent_version` | string | required | producer version |
| `egress` | string | required | one of `pseudonymized` or `raw`. `raw` means identities are emitted unprotected and §3's key-space rules do not apply |
| `endpoint_count` | integer | required | subscriptions configured |
| `max_payload_bytes` | integer | required | largest inbound engine message accepted |
| `canary` | string | conditional | present when identities are keyed (§3.4) |
| `reuse_reporting` | string | optional | as `heartbeat` |

*Example (informative), from `lifecycle/records`:*

```json
{"kind": "agent_start", "at_ms": 1785153670000.0, "agent_version": "0.0.0-fixture",
 "egress": "pseudonymized", "endpoint_count": 2, "max_payload_bytes": 16777216,
 "canary": "2a0d53e8a23631a0e8ab966069f98f3c"}
```

#### `heartbeat`

The completeness clock. Counters are cumulative for the producer's run, so the difference between
two heartbeats describes the span between them.

| field | type | presence | meaning |
|---|---|---|---|
| `kind` | `"heartbeat"` | required | |
| `at_ms` | number | required | producer clock |
| `msgs_seen` | integer | required | inbound messages observed |
| `dropped` | integer | required | inbound messages known lost |
| `oversized` | integer | required | inbound messages refused for size |
| `unknown_types` | integer | required | inbound messages of unmodelled type |
| `events_ingested` | integer | required | events that reached the record model |
| `content_unresolved` | integer | required | records emitted with no `content_id`, one per omission (§3.1) |
| `content_bridge_entries` | integer | required | identity-derivation state size (the producer's view of the resident set) |
| `content_bridge_evicted` | integer | required | identity promises refused at the declared capacity — nonzero means some evicts will not resolve, each window also declared via `identity_refused` |
| `publisher_restarts` | integer | required | engine-side restarts observed |
| `endpoints` | array | required | per-subscription statistics, below |
| `canary` | string | conditional | present when identities are keyed (§3.4) |
| `reuse_reporting` | string | optional | `none` \| `labelled` \| `unlabelled` — whether this producer's engine announces cache reuse as a `store`, and whether it can be told apart (§2.3) |
| `noraw_scanned` | integer | optional | values checked by the producer's egress guard |
| `rss_bytes` | integer | optional | producer resident memory |

Each `endpoints` element carries:

| field | type | presence | meaning |
|---|---|---|---|
| `source` | string | required | the instance this subscription observes |
| `endpoint` | string | required | the transport address subscribed to |
| `msgs_seen` | integer | required | inbound messages observed on this subscription |
| `dropped` | integer | required | inbound messages known lost on this subscription |
| `last_msg_at_ms` | number | optional | producer clock at the last message, absent where none has arrived |
| `topic` | string | optional | the channel name the transport supplied, relayed verbatim (below) |

**`reuse_reporting` rides all three lifecycle kinds**, exactly as the canary does and for the
same reason (§3.4): an analysis window need not contain a start record, and a declaration a
reader cannot reach is one it cannot apply. A producer MUST NOT vary it within an incarnation — it describes the
engine, not the traffic.

**`topic` is relayed verbatim and unparsed.** Where the transport names a channel, a producer MUST
carry that name exactly as received and MUST NOT interpret, normalize or split it. Deployments
encode real identity there — several conventions put the served model and the pod in the topic —
but the conventions are the deployment's, not this contract's, so recognizing one is a reader's
business and a producer that parsed it would be publishing an interpretation as a fact.

A reader MAY recognize a topic under a **named, versioned convention** matched at exact arity, and
MUST refuse rather than extract heuristically: a convention that does not match yields nothing, and
a partial match yields nothing. Refusal is the only failure mode. A reader that recognizes nothing
still conforms. Verbatim relay makes recognition retroactive — a convention added later re-derives
its labels over archived records by ordinary re-analysis. [^topic]

`endpoints[].source` MUST equal the `instance_id` that the producer emits for that subscription's
cache records. It is the only link between a lifecycle record and the instances a producer covers.

The counters above are **required even at zero**. A producer MUST emit them at zero rather than
omit them: an absent counter means the producer does not report the quantity at all, which is a
different claim from reporting zero. [^counters]

*Example (informative), from `lifecycle/records`. The second endpoint has no `last_msg_at_ms`:
nothing seen yet, so nothing is stamped:*

```json
{"kind": "heartbeat", "at_ms": 1785153730000.0,
 "msgs_seen": 10, "dropped": 1, "oversized": 0, "unknown_types": 2, "events_ingested": 37,
 "content_unresolved": 5, "content_bridge_entries": 128, "content_bridge_evicted": 0,
 "publisher_restarts": 1, "noraw_scanned": 42, "rss_bytes": 20480000,
 "canary": "2a0d53e8a23631a0e8ab966069f98f3c",
 "endpoints": [
   {"source": "i0", "endpoint": "tcp://127.0.0.1:5557", "msgs_seen": 10, "dropped": 1,
    "last_msg_at_ms": 1785153671500.0},
   {"source": "i1", "endpoint": "tcp://127.0.0.1:5558", "msgs_seen": 0, "dropped": 0}]}
```

#### `agent_stop`

| field | type | presence | meaning |
|---|---|---|---|
| `kind` | `"agent_stop"` | required | |
| `at_ms` | number | required | producer clock |
| `reason` | string | required | why the run ended |
| `msgs_seen` | integer | required | as `heartbeat` |
| `dropped` | integer | required | as `heartbeat` |
| `oversized` | integer | required | as `heartbeat` |
| `unknown_types` | integer | required | as `heartbeat` |
| `events_ingested` | integer | required | as `heartbeat` |
| `content_unresolved` | integer | required | as `heartbeat` |
| `content_bridge_entries` | integer | required | as `heartbeat` |
| `content_bridge_evicted` | integer | required | as `heartbeat` |
| `publisher_restarts` | integer | required | as `heartbeat` |
| `reuse_reporting` | string | optional | as `heartbeat` |
| `endpoints` | array | required | as `heartbeat` |
| `canary` | string | conditional | present when identities are keyed (§3.4) |

An `agent_stop` record carries no `noraw_scanned` and no `rss_bytes`.

An `agent_stop` record is a producer announcing an expected departure. A reader MUST treat staleness
**without** a preceding `agent_stop` as unexplained rather than as an ordinary departure. A kill or
a crash leaves none, and that absence is the signal. [^stop]

*Example (informative), from `lifecycle/records`:*

```json
{"kind": "agent_stop", "at_ms": 1785153760000.0, "reason": "signal",
 "msgs_seen": 12, "dropped": 1, "oversized": 0, "unknown_types": 2, "events_ingested": 44,
 "content_unresolved": 5, "content_bridge_entries": 128, "content_bridge_evicted": 0,
 "publisher_restarts": 1, "canary": "2a0d53e8a23631a0e8ab966069f98f3c",
 "endpoints": [
   {"source": "i0", "endpoint": "tcp://127.0.0.1:5557", "msgs_seen": 10, "dropped": 1,
    "last_msg_at_ms": 1785153671500.0},
   {"source": "i1", "endpoint": "tcp://127.0.0.1:5558", "msgs_seen": 0, "dropped": 0}]}
```

#### `identity_refused`

A declared, holder-scoped identity loss: the producer's identity-derivation state reached its
declared capacity and refused new entries, so the named holder's evicts over the window carry no
`content_id`. This record is to identity what `segments_dropped` is to delivery: a loss the
producer declares instead of leaving the reader to infer it.

Unlike the lifecycle bracket, this record carries an `instance_id`: it declares a loss for one
observed instance, not a fact about the producer process as a whole.

| field | type | presence | meaning |
|---|---|---|---|
| `kind` | `"identity_refused"` | required | |
| `at_ms` | number | required | producer clock |
| `instance_id` | string | required | the affected instance (§3.2) |
| `dp_rank` | integer | required | the affected worker |
| `group_idx` | integer | required | the affected cache group |
| `refused` | integer | required | stores denied an identity in the window |
| `window_start_ms` | number | required | **engine clock**: first refused store |
| `window_end_ms` | number | required | **engine clock**: last refused store |

The window fields are the engine's clock domain while `at_ms` is the producer's (§2.6); the two
ride one record and MUST NOT be compared with each other. A reader MUST treat any figure over the
named holder within `[window_start_ms, window_end_ms]` as a lower bound, and SHOULD degrade only
that holder over that window: the signal is scoped precisely so the rest of the fleet's figures
stand. [^refused]

*Example (informative), from `lifecycle/records` (`capacity_cases`). `at_ms` is the producer
clock; the window fields are the engine clock:*

```json
{"kind": "identity_refused", "at_ms": 1785153730000.0, "instance_id": "i0",
 "dp_rank": 0, "group_idx": 1, "refused": 2048,
 "window_start_ms": 1785153671000.25, "window_end_ms": 1785153711000.75}
```

### 2.5 Delivery records

These describe the files records arrive in. See §4.

#### `segment_open`

The first record of every segment, written before any other record in that segment.

| field | type | presence | meaning |
|---|---|---|---|
| `kind` | `"segment_open"` | required | |
| `at_ms` | number | required | producer clock |
| `incarnation` | string | required | identifies one run of one producer (§4.2) |
| `segment_seq` | integer | required | position in that incarnation's sequence, from zero |
| `contract_version` | string | required | the version of this contract the segment conforms to (§6.1) |
| `workload_class` | string | optional | what this producer's traffic is FOR, in the operator's vocabulary (§2.7). Since 1.2 |
| `heartbeat_secs` | integer | required | declared heartbeat interval (§5.8). Since 1.3 |
| `max_segment_secs` | integer | required | declared maximum segment age (§5.8). Since 1.3 |
| `key_epoch` | integer | conditional | present when identities are keyed (§3.3). Since 1.5 |

*Example (informative), from `delivery/records`:*

```json
{"gpu": "fixture", "vllm_version": "0.26.0", "event_schema_version": "vllm-0.26.0-map",
 "kind": "segment_open", "at_ms": 1785153670000.0, "contract_version": "1.2",
 "workload_class": "agentic",
 "incarnation": "1785153670000-4242", "segment_seq": 0}
```

#### `segment_recovered`

Written when a producer recovers a segment left unfinished by a predecessor.

| field | type | presence | meaning |
|---|---|---|---|
| `kind` | `"segment_recovered"` | required | |
| `at_ms` | number | required | producer clock |
| `attributed` | boolean | required | whether the recovered segment's own identity was readable |
| `dropped_bytes` | integer | required | trailing bytes discarded as incomplete |

*Example (informative), from `delivery/records`:*

```json
{"kind": "segment_recovered", "at_ms": 1785153671000.0, "attributed": true, "dropped_bytes": 137}
```

#### `segments_dropped`

A declared loss. A producer that reclaims sealed segments to stay within a storage bound MUST say so.

| field | type | presence | meaning |
|---|---|---|---|
| `kind` | `"segments_dropped"` | required | |
| `at_ms` | number | required | producer clock |
| `incarnation` | string | required | the run whose data is gone, not the run that reclaimed it |
| `count` | integer | required | segments reclaimed |
| `first_seq` | integer | required | lowest `segment_seq` reclaimed |
| `last_seq` | integer | required | highest `segment_seq` reclaimed |
| `first` | string | required | filename of the first segment reclaimed |
| `last` | string | required | filename of the last segment reclaimed |

A producer MUST emit one `segments_dropped` record per **incarnation** reclaimed. One reclamation
pass MAY span several incarnations, and across two incarnations the reclaimed set is not contiguous,
so a single record could not describe it as a range. [^dropped]

*Example (informative), from `delivery/records`:*

```json
{"kind": "segments_dropped", "at_ms": 1785153673000.0, "incarnation": "1785153670000-4242",
 "count": 3, "first_seq": 4, "last_seq": 6,
 "first": "seg-1785153670000-4242-4.jsonl", "last": "seg-1785153670000-4242-6.jsonl"}
```

### 2.6 Clock domains

`at_ms` is epoch milliseconds on every record. Two clock domains exist:

- the **engine** clock, on cache records
- the **producer** clock, on lifecycle and delivery records

A reader MUST NOT compare timestamps across the two domains as though they were the same clock, and
MUST apply a configured skew allowance when comparing engine-domain timestamps originating from
different instances. Without an allowance, a reader can report two events as simultaneous when the
data cannot support that. [^clock]

### 2.7 Workload class

**Since 1.2.** A producer MAY declare a `workload_class` on its `segment_open` record: a name, in
the operator's own vocabulary, for what this producer's traffic is FOR. Conventionally a stream
declares something like `agentic` or `batch`. The vocabulary is not specified here, exactly as
provenance keys are not.

A reader MUST apply a segment's declared `workload_class` to every record in that segment, and MUST
treat its absence as a bucket rather than a null: **a producer that declares nothing has not
declared "no workload", it has said nothing**, and a reader that collapsed the two would report a
fleet whose traffic is uncategorized as a fleet whose traffic is categorized as none.

**It is declared, not observed, and it is declared HERE because this is where the truth is.** A
producer runs beside one engine, configured by whoever knows what that engine serves. Nothing in
the record stream reveals intent, and no reader can derive it. A reader that instead matched
producer identifiers against a centrally-configured pattern would be pattern-matching over a naming
convention: rename an instance and the label silently changes, or silently stops matching, with no
error anywhere.

**It rides the header for the same reason provenance does** (§2.2): it is constant for a producer
run, so stating it per record would repeat a constant. A producer MUST NOT emit `workload_class` on
any record other than `segment_open`.

**A reader MUST NOT treat it as a fact about the records.** It is testimony from the producer about
its own configuration, and it is admissible as exactly that. Two producers declaring the same class
are making the same claim, not being observed to be alike.

## 3. Identity

### 3.1 Two identity spaces

**`block_id` is engine-local.** It identifies a block only within the process that computed it.
Engines commonly seed prefix-hash chains from a per-process random value, so identical content
yields unrelated `block_id` values in sibling workers, after a restart, and on other nodes.

A reader MUST NOT compare `block_id` values originating from different `instance_id` values, or from
the same instance across a producer-observed restart. The comparison yields no matches no matter how
much identical content exists, and the result looks like a measured absence instead of an error.

**`content_id` is portable.** It is defined here by its properties, not its construction:

1. **Deterministic** under a key the operator holds. Two producers holding the same key emit the
   same `content_id` for the same block content.
2. **Stable** across processes, restarts, nodes, and engine versions.
3. **Non-invertible.** A `content_id` does not reveal the content it identifies.
4. **Not comparable across keys or epochs.** Values derived under different key material, or under
   different `key_epoch` values, are unrelated and MUST NOT be compared. [^identity]
5. **Unique, with its failure announced.** Distinct content yields distinct `content_id` values up
   to a stated collision bound, and a collision is detectable rather than silent: a merged
   identity is reached through more than one prefix chain and therefore claims more than one
   parent. A reader MUST surface contradictory parent claims for one identity — count them and
   report the count beside any figure computed over that identity space — and MUST NOT fold them
   into one edge, because the fold is what would make a collision invisible. [^unique]

**`extra_keys` participates in identity.** Engines admit inputs beyond the token sequence that
partition a cache: a salt that separates tenants, a hash of non text content. Two blocks with
identical tokens and different `extra_keys` are different blocks, and a producer MUST derive
`content_id` so that they do not collide. A reader MUST NOT treat two blocks as the same block on
token equivalence alone. [^extrakeys]

A producer MUST omit `content_id` where it could not derive one satisfying every property above,
and MUST count each omission in `content_unresolved`. A reader MUST treat a window in which
`content_unresolved` is nonzero as producing a lower bound for any figure computed across instances.

**The two spaces MUST NOT be joined.** A reader MUST NOT treat a `block_id` and a `content_id` as
interchangeable, and MUST NOT match one against the other. A conforming producer separates them so
that one underlying value yields unrelated values in each space, which makes an accidental join
match nothing rather than match wrongly. [^spaces]

### 3.2 Scope

A `block_id` identifies a block only within a **holder**:

```
holder = (instance_id, dp_rank, group_idx)
```

`instance_id` is **operator-assigned**, not derived from anything observable. A reader MUST NOT infer
relationships between instances from their identifiers.

`dp_rank` distinguishes data-parallel workers, which hold physically independent caches and commonly
publish to a shared endpoint. `group_idx` distinguishes cache groups, which hash independently.

A reader MUST scope block identity to the full holder. Collapsing `dp_rank` or `group_idx` under a
bare instance treats independent caches as one and under-reports duplication between them. Absent
`dp_rank` or `group_idx` means the producer declared no such scope; a reader MAY group such records
together but MUST NOT read absence as an assertion that the engine has a single rank or group.
[^holder]

### 3.3 Key epochs

`key_epoch` scopes an identity space. Identities carrying different `key_epoch` values were derived
under different key material or a different generation of it, and are unrelated.

**A producer declares it on every `segment_open`** (since 1.5), for the reason §5.8 gives for the
liveness bounds and §2.2 for provenance: it is constant for a producer run, a reader needs it to
interpret every record behind it, and a declaration reachable only through a start record is one a
retention policy can take away. It is the operator's, set alongside the key material it counts
generations of.

**The epoch is already folded into each pseudonym**, so identities across a rotation cannot match
whether or not a reader reads this field. Declaring it is what lets a reader SAY which epoch a
figure belongs to, and check a boundary it would otherwise only infer from identities ceasing to
match — which is indistinguishable from a fleet with nothing in common.

A reader MUST NOT compare identities across `key_epoch` values, and MUST treat an epoch boundary as
a discontinuity in block-level accounting rather than as continuous history. Figures on either side
of the boundary are sound. Figures spanning it are lower bounds for any question about individual
blocks. Aggregates carrying no identity cross the boundary unaffected. [^epoch]

### 3.4 The canary and fleet key consistency

Producers holding different key material emit identities that cannot match at any overlap. From the
records alone this is indistinguishable from a fleet with no content in common.

The **canary** resolves it positively. Every producer provisioned from the same key material at the
same `key_epoch` emits an identical `canary` value, and a producer without that key material cannot
emit it. A producer MUST emit the canary of the key currently in force, and MUST NOT emit any other
key's canary. [^canary]

A reader MUST compare canaries before reporting any figure computed across producers. Producers
whose canaries differ are not comparable, and a figure computed across them describes the
provisioning rather than the cache behaviour.

The check is asymmetric, and a reader MUST treat it as such. Matching canaries **prove** shared key
material. Absence proves nothing: a producer emitting no canary MAY be unkeyed, or MAY be keyed with
its lifecycle records not yet received, and the records cannot distinguish these.

**Convergence.** A reader MUST infer rotation state from fleet-wide convergence, and MUST NOT infer
it from any single producer's testimony. Concretely: a rotation in progress is recognized by most
holders moving from one canary value to another within a window, while a single holder on a canary
value no other holder has emitted is a provisioning fault. A reader MUST NOT accept a producer's own
assertion that two key spaces are related, because a mis-provisioned producer would make the same
assertion and thereby suppress the fault this section exists to surface.

## 4. Delivery layout

### 4.1 Sealed segments

The **sealed segment** is the only unit of exchange. A sealed segment is **immutable and complete**:
the producer that wrote it will not write to it again, and it contains no partial record.

A producer MUST NOT present a segment as sealed until both properties hold. A reader MUST NOT ingest
a segment that is still being written. Ingesting an in-progress segment is not merely incomplete: its
content will change, so a reader keyed on content will store every overlapping record twice.
[^active]

The filename convention is **informative**. A conforming reader derives nothing it needs from a
filename. The `segment_open` header record is **normative**: it carries the segment's identity in
the segment, so continuity survives any transport that preserves file contents, including transports
that rename. [^header]

A sealed segment MUST begin with either a `segment_open` record or a `segment_recovered` record.
A reader MUST reject a segment beginning with neither, and MAY dispatch on that first record. [^first]

### 4.2 Incarnations

An **incarnation** identifies one run of one producer. It is opaque to a reader, which MUST treat it
only as an equality-comparable token, and MUST NOT parse structure out of it.

Within one incarnation, `segment_seq` increases from zero without gaps. A missing `segment_seq`
within an incarnation is loss. A fresh incarnation beginning at `segment_seq` zero is a restart.
[^incarnation]

### 4.3 Orphans

A producer that recovers a segment left unfinished by a predecessor MUST mark it with a
`segment_recovered` record. The two cases differ:

**Attributed** (`attributed: true`). The segment's own `segment_open` survived, so the segment
retains its original identity. It begins with that `segment_open`, keeps its original `incarnation`
and `segment_seq`, and **participates in continuity normally**. A reader MUST treat it as an
ordinary sealed segment of the incarnation that wrote it, not of the producer that recovered it.

**Unattributed** (`attributed: false`). The segment's header did not survive, so the segment claims
no identity. It MUST begin with the `segment_recovered` record, which takes the header position for
this segment class.

A reader MUST treat the records of an unattributed segment as **attributable to an instance and
excluded from continuity accounting**. They are complete and measurable, but belong to no sequence,
so a reader MUST NOT count their presence or absence toward any continuity claim, and MUST treat the
span they cover as indeterminate. [^orphan]

## 5. Continuity and coverage

This section states the reader's obligations. It is the conformance floor.

### 5.1 Continuity scope

A reader MUST scope segment continuity to `(instance_id, incarnation)`. [^continuity]

**One producer MAY observe several instances** (§2.4), while segments and `segment_seq` belong to
the producer's incarnation rather than to any one instance. A single sequence therefore carries the
cache records of several instances interleaved.

It follows that a missing `segment_seq` is a **producer-level** loss, and a reader MUST degrade the
window of **every instance that incarnation covered**, not only of instances whose records happen to
appear in the surviving segments. The mapping from incarnation to covered instances is
`endpoints[].source` on that incarnation's lifecycle records (§2.4).

A deployment running one producer per instance makes this indistinguishable from per-instance
scoping. The contract permits the multi-instance shape, so a reader MUST implement the general
rule. [^multi]

### 5.2 Restart is not a gap

A reader MUST treat a fresh incarnation beginning at `segment_seq` zero as a **restart**, and MUST
NOT report it as a gap. [^restart]

### 5.3 The incarnation boundary is uncovered

A reader MUST treat the interval between one incarnation's last observation and the next
incarnation's first as an **uncovered window**, computed from the lifecycle bracket: the previous
incarnation's `agent_stop`, or its last observation where no `agent_stop` was received, to the
following `agent_start`.

A producer observes nothing while it is not running. A reader that carries a figure across that
interval as though it were observed is reporting an absence it did not measure. [^bracket]

### 5.4 Detected gaps degrade the window

A reader MUST degrade any window containing a detected gap to **indeterminate**, and MUST NOT
classify the facts within it as though the window were complete. Detected gaps include a missing
`segment_seq` within an incarnation, a nonzero `dropped` delta between heartbeats, and a
`segments_dropped` record overlapping the window. [^gap]

**`seq` may narrow the degraded span, and only under both conditions.** A `dropped` delta localizes
a loss no better than the interval between two heartbeats, so a single lost message degrades every
fact in that interval. Where records carry `seq` (§2.3), a reader MAY instead degrade only the span
between the two records bracketing the discontinuity — but only where **both** bracketing records
carry `seq` and share the same `(instance_id, incarnation)`. Otherwise it degrades the whole
interval as before.

Narrowing is the only weakening this section permits, and the conditions are what make it safe: a
`seq` is monotonic only within an incarnation, so a bracket spanning a restart compares numbers from
two different sequences and would silently exonerate a window nothing observed. Absent `seq` on
either side, the reader has no bracket at all. A reader MUST NOT narrow past the observed bracket to
the message itself: the records derived from one message share its `seq`, so the bracket is the
finest resolution the stream carries. [^seq]

### 5.5 Malformed input

A reader MUST accept an unparseable **final** line of a segment as an expected artifact of a producer
that stopped mid-write, discard it, and count it.

An unparseable line in any other position indicates corruption rather than truncation, and a reader
MUST fail closed on it. **Failing closed means the segment is not ingested and none of its records
commit**: ingestion is all-or-nothing per segment, so a reader MUST NOT commit the records preceding
a corrupt line. [^tail]

### 5.6 The lower-bound rule

A reader MUST treat absence as **exact only within an observed, counted sequence**, and as a **lower
bound** everywhere else.

A reader may state that a given number of messages arrived and none was lost, where the producer's
counters establish it. A reader MUST NOT state what occurred before a producer started, during a
gap, or outside any window it observed. [^lowerbound]

### 5.7 Coverage accompanies every figure

**A reader MUST NOT emit a derived figure without the coverage over which it was computed.**

This is the floor. A figure without its coverage is a claim rather than a measurement, however the
figure was computed.

A reader MUST additionally qualify any zero it reports for a cross-instance question. A positive
result carries its own evidence, because the records that matched demonstrate they were comparable.
A zero does not, and cannot distinguish "none existed" from "none could have been observed". Before
reporting such a zero a reader MUST establish that at least two holders had residency, that records
carried portable identity (§3.1), and that the holders shared a key space (§3.4). [^coverage]

### 5.8 Liveness bounds

A producer MUST emit a `heartbeat` at least every `heartbeat_secs`, and MUST seal a segment at least
every `max_segment_secs`, both as declared on every `segment_open` it writes. A producer MUST
declare both.

**They moved off `agent_start` in 1.3, for the reason §3.4 already gives for the canary and §2.4
for `reuse_reporting`: an analysis window need not contain a start record, and a declaration a
reader cannot reach is one it cannot apply.** The bounds were the last declaration still reachable
only through `agent_start`, which is written once per run while the records it qualifies outlive
that segment — so whether a reader could judge staleness depended on a retention policy rather than
on the data. A producer that runs longer than a reader keeps records became permanently
unjudgeable, which is exactly the producer worth judging.

The header carries them rather than the other lifecycle kinds, because §4 already requires every
segment to begin with one: a segment containing no lifecycle record at all still declares.

Those two bounds are the entire basis on which a reader can call a producer stale. Without them,
silence from a producer is indistinguishable from a producer with nothing to report, and the
unexplained-departure rule in §2.4 is unspecifiable.

A reader MUST treat a producer as **stale** when the interval since its last record exceeds the
larger of the two declared bounds, plus an implementation-defined allowance. How a producer decides
to seal within `max_segment_secs` is out of scope (§7); the bound itself is contract. [^liveness]

### 5.9 A store count is an insertion count only where the producer says so

`reuse_reporting` (§2.4) tells a reader what a `store` record means on this stream. The obligation
follows the declaration, per holder and per window:

- **`"none"`** — a reader MAY treat every `store` as an insertion: count them, and sum `n_tokens`
  over them as inserted tokens.
- **`"labelled"`** — a reader MUST exclude records carrying `reused: true` from any count of
  insertions and from any sum of inserted tokens. They remain facts, and a reader MAY use them —
  a reuse is direct evidence that a resident block was matched, which nothing else in this stream
  states.
- **`"unlabelled"`**, **absent**, or **unrecognized** — a reader MUST NOT present an
  **unqualified** count of `store` records, or an unqualified sum of `n_tokens` over them, as a
  quantity of insertions or of inserted tokens. It MAY still report residency, identity and
  duplication, none of which counts a record twice for being announced twice.

The failure this forbids is not a small one and it does not look like an error. Summing `store`
records gives tokens inserted only where reuse is not announced. Where it is announced and
unlabelled the sum gives inserted plus reused, with nothing separating them: a block that stops
being recomputed starts being announced as a hit instead, and contributes the same tokens either
way. **The total barely moves while insertions fall.** A reader that reports it as inserted
tokens has inverted the measurement while every input was correct, and nothing in the figure
looks wrong.

**"Unqualified" is doing work, and the two qualified cases fall on opposite sides.** A reuse
announcement describes a block the engine found **resident**. That single fact decides both:

- **Conditioning on an observed prior close is SAFE, and a reader MAY do it under any
  declaration.** A figure counting only those stores that follow an observed `evict` or `clear`
  of the same block — a recomputation figure — cannot admit a reuse announcement, because a
  reuse describes a resident block and residency ended at that close. For the announcement to
  qualify, the residency would have had to reopen unobserved, which is a lost record and
  therefore a detected gap under §5.4. Either the store is a genuine recomputation or the window
  is already degraded. [^reuseclose]

- **Conditioning on ABSENT prior residency is UNSAFE, and a reader MUST NOT do it.** A store for
  a block whose residency this reader never observed is exactly where a reuse announcement and a
  first insertion are indistinguishable: the block may have been resident since before
  observation began. A reader MUST NOT treat the absence of prior residency as evidence that the
  block was not already cached, and MUST NOT count such a store as a first insertion or a cold
  miss. It is indeterminate, not cold. [^reusecold]

  This is §5.6's lower-bound rule reaching one field further: absence is exact only within an
  observed sequence. It is worth stating separately because the error does not decay. A reader
  might expect it to expire once the cache has turned over — but a block that is never evicted is
  never re-announced, and the hottest shared prefix in a fleet is precisely the block least likely
  to be evicted. Left unstated, the miscount would concentrate on the traffic that matters most,
  and would report a cache as **less** effective than it is.

**A window MUST take the weakest declaration it contains.** Declarations are per producer, a window
may span several, and a reader that mixed them would apply `"none"` to records from a producer that
never claimed it. [^reuseread]

## 6. Versioning

### 6.1 `contract_version`

Each segment carries `contract_version` once, in its `segment_open` record. It identifies the version
of **this contract** that the segment conforms to.

**An unattributed recovered segment (§4.3) declares no `contract_version`, and MUST NOT.** Its
records were written by a predecessor whose version the recovering producer does not know, so any
value it supplied would be a guess presented as a fact. A reader MUST parse such a segment under the
mixed-fleet law (§6.2), which a conforming reader implements regardless. [^unversioned]

`contract_version` is distinct from `semantics_version`, which governs classification (§1) and does
not appear in this contract. A reader MUST NOT conflate them: the same facts may be reclassified
under a new `semantics_version` without any change to `contract_version`.

Additive changes, meaning new record kinds and new optional fields, increment the minor version.
Anything else, including any change in the meaning of an existing field, increments the major
version. A change in meaning MUST NOT be made without a major version increment. [^contractver]

**1.2 is minor by decision, not by the law above, and the difference is recorded rather than
disguised.** Requiring provenance on `segment_open` alone makes a 1.1 producer that repeats it
non-conforming, and a producer-breaking change is a major version under the paragraph above.

It is taken as a minor version because this contract currently has exactly one producer and one
reader, both in this organisation, with no third party holding either. There is no fleet to skew
and no consumer to strand. **The reader side does not break at all** — the header has carried
provenance in every segment ever written, so a 1.2 reader reads 1.1 segments with no second code
path.

**This exemption expires the moment a producer exists that we do not ship.** At that point the
paragraph above governs without exception, and a change of this shape takes a major version. A
contract that keeps granting itself exemptions is not a contract, so this one is written down with
its expiry rather than left as precedent.

### 6.2 The mixed-fleet law

**Producer version skew is steady state, not an error condition.** A fleet is upgraded gradually, so
a reader will routinely receive several contract versions at once.

A reader MUST count and skip record kinds it does not recognize, and MUST carry fields it does not
recognize rather than discarding them. A reader MUST NOT error on either. [^unknown]

A reader that refuses an unrecognized kind cannot receive an additive change, which makes every
future minor version a breaking one.

## 7. Out of scope

These are deliberately out of scope, stated here so they are not re-added later:

- **Transport.** How segments travel from producer to reader. This contract specifies a directory
  and a naming convention, not a protocol. Any mechanism preserving file contents satisfies it.
- **Sealing thresholds.** When a producer chooses to seal a segment, by size, age, or otherwise.
- **Storage-bound mechanics.** How a producer bounds its local storage, beyond the requirement to
  declare reclamation (§2.5).
- **Durability ordering.** When a producer flushes or synchronizes, beyond the requirement that a
  sealed segment is complete (§4.1).
- **`content_id` construction.** Only the properties in §3.1 are normative. Any construction
  satisfying them conforms.
- **Reader internals.** Storage, query, and presentation, beyond the obligations in §5.
- **Classification.** Governed by `semantics_version` (§1).

## 8. Conformance checklists (informative)

Navigation, not new requirements: every row cites the section whose normative text governs and
the fixture (or named reference-producer test) that fails a violator. An implementation is
conformant when the cited sections hold; these tables exist so an implementer can find them.

### 8.1 Producer

| obligation | where | pinned by |
|---|---|---|
| One JSON object per line; no record over 1 MiB | §2.1 | named producer test ([^size]) |
| Identity fields are strings, never JSON numbers | §2.2 | every `telemetry/` fixture ([^idtype]) |
| Absent means omitted — never null, never a sentinel | §2.2 | `telemetry/tier_absent_stays_null` |
| One `store` per block, prefix chains resolved; runs never reach the wire | §2.3 | `telemetry/prefix_chain` |
| An absent `clear` scope is treated as global, never defaulted | §2.3 | `vllm-wire/cleared_scope_undeclared` |
| Lifecycle counters emitted at zero, not omitted | §2.4 | `lifecycle/records` |
| Both liveness bounds declared on every `segment_open` and honored | §2.4, §5.8 | `lifecycle/records`; named producer tests ([^liveness]) |
| Identity-capacity losses declared per holder and window | §2.4 | `lifecycle/records` (`capacity_cases`) |
| Reclamation declared, one `segments_dropped` per incarnation | §2.5 | `delivery/records` |
| `content_id` satisfies every §3.1 property, or is omitted and counted | §3.1 | `pseudonym/vectors`, `telemetry/` |
| `extra_keys` folded into identity derivation | §3.1 | `telemetry/salted_partition` |
| The two identity spaces cannot be joined | §3.1 | `telemetry/content_id_rides_beside_the_engine_id` |
| The canary of the key in force, and no other key's | §3.4 | `lifecycle/records` |
| Segments sealed immutable and complete, header record first | §4.1 | `delivery/records` |
| `segment_seq` from zero without gaps within an incarnation | §4.2 | `delivery/layout` |
| Recovered segments marked; attributed keeps its identity, unattributed claims none | §4.3 | `delivery/records` (`orphan_segment`) |
| `contract_version` in every `segment_open`; never on an unattributed recovery | §6.1 | `delivery/records` |

### 8.2 Reader

| obligation | where | pinned by |
|---|---|---|
| Carry unrecognized fields; count and skip unrecognized kinds | §2.2, §6.2 | `vllm-wire/unknown_*` ([^unknown]) |
| Distinguish absent from empty or zero | §2.2 | `telemetry/tier_absent_stays_null` |
| Distinguish parent's three states; unknown is not a root | §2.3 | `telemetry/parent_unknown_is_not_a_root` |
| A `REMOTE` block is not the holder's own copy | §2.3 | `telemetry/remote_locality_is_carried` |
| A `clear` closes residencies; absent scope dimensions cover all values | §2.3 | `telemetry/clear_*` |
| Never compare across clock domains; skew allowance within the engine domain | §2.6 | `reader/clock_*` |
| Never compare `block_id` across holders or restarts; never join the two spaces | §3.1 | `telemetry/same_hash_*` |
| Surface parent-conflict counts; never fold a collision | §3.1 | `reader/identity_collision_claims_two_parents` |
| Identity scoped to the full holder | §3.2 | `telemetry/same_hash_distinct_dp_ranks`, `_groups` |
| Never compare identities across key epochs | §3.3 | `pseudonym/vectors` |
| Canaries compared before any cross-producer figure; rotation from convergence, never testimony | §3.4 | `reader/canary_split_key_material_is_not_a_measured_zero` |
| Only sealed segments, ingested whole-file or not at all | §4.1, §5.5 | `delivery/layout`; `vllm-wire` malformed rows |
| Unattributed recoveries measurable but outside continuity | §4.3 | `reader/audit_unattributed_recovery_supports_no_same_run_claim` |
| Continuity scoped to (instance, incarnation); a producer-level loss degrades every covered instance | §5.1 | `reader/gap_scope_*` |
| A restart is not a gap | §5.2 | `reader/gap_an_intact_stream_is_not_degraded` |
| Incarnation boundaries are uncovered windows, from the lifecycle bracket | §5.3 | `reader/uncovered_*` |
| Detected gaps degrade the window to indeterminate | §5.4 | `reader/gap_*` |
| Absence exact only within a counted bracket; a lower bound everywhere else | §5.6 | `reader/absence_*` |
| Coverage beside every figure; cross-instance zeros qualified | §5.7 | `reader/coverage_*`, `reader/zero_*` |
| Staleness judged only against declared bounds, at the knowledge horizon | §5.8 | `reader/staleness_*` |

---

## Non-normative notes

### Known implementations

`infertap` is the reference producer for this contract, and the corpora cited below are its
conformance fixtures. This is the only place in this document where an implementation is named.

### Fixture citations

Each note names the fixture that would fail an implementation violating the requirement.

[^size]: Enforced by the reference producer at its egress choke point: an oversized record is
    refused and counted, never emitted and never fatal, pinned by a named test in the
    producer's own suite. That test is the covering artifact: a megabyte corpus blob would
    prove nothing it does not.

[^absent]: `telemetry/tier_absent_stays_null`.

[^parent]: `telemetry/parent_unknown_is_not_a_root`.

[^locality]: `telemetry/remote_locality_is_carried`, with producer-side inputs
    `vllm-wire/locality_local`, `vllm-wire/locality_remote`, `vllm-wire/locality_on_remove`.

[^run]: `vllm-wire/stored_fanout` and `vllm-wire/run_with_skipped_blocks` for the input shape,
    `telemetry/prefix_chain` for the resolved output.

[^seq]: `telemetry/seq_rides_every_cache_record` pins the field on all three cache kinds and
    pins that records from one message share its number; `telemetry/seq_absent_where_the_transport_does_not_number`
    pins the omission. The reader half is `reader/seq_narrows_the_degraded_span_to_its_bracket`,
    against the two fixtures that must NOT narrow —
    `reader/seq_across_an_incarnation_boundary_does_not_narrow` and
    `reader/a_bracket_missing_seq_does_not_narrow` — which together fail a reader that
    narrows on an unsound bracket, the only direction in which narrowing is unsafe.

[^reuse]: `lifecycle/records` carries the declaration on all three kinds;
    `telemetry/reuse_labelled_rides_the_store_it_describes` pins the per-record field.
    `telemetry/sliding_window_is_carried_where_the_group_declares_one` pins
    `spec_sliding_window` beside its `spec_kind`.

[^reuseclose]: `reader/reuse_unlabelled_still_permits_a_recompute_figure`: an unlabelled
    stream whose unqualified count is refused while the figure conditioned on an observed close
    is computed. It fails a reader that reads §5.9 as forbidding every aggregate over `store`
    records — which would surrender the one recomputation figure the stream still supports.

[^reusecold]: `reader/reuse_unlabelled_forbids_a_first_insertion_figure`, against
    `reader/first_insertion_is_countable_where_reuse_is_not_announced`: the same shape of stream
    under the two declarations, so a reader that answers both alike fails one of them.

[^reuseread]: `reader/reuse_*`: one fixture per declaration state —
    `reuse_none_makes_every_store_an_insertion`,
    `reuse_labelled_excludes_the_reused_records`,
    `reuse_unlabelled_forbids_an_insertion_count` — beside the three that fail a reader
    which treats silence or novelty as permission: `reuse_undeclared_is_not_none`,
    `reuse_unrecognized_reads_as_unlabelled`, and
    `a_window_takes_the_weakest_reuse_declaration_it_contains`.

[^topic]: `lifecycle/records` carries a topic on the endpoint that has seen traffic and none
    on the endpoint that has not, so a producer that synthesized one fails. No fixture pins a
    recognition convention, deliberately: recognition is a reader's business and this contract
    defines none.

[^clear]: `telemetry/clear_is_scope_level`, with producer-side input `vllm-wire/cleared_all`.

[^counters]: `lifecycle/records` pins all three lifecycle kinds byte for byte, including counters at
    zero.

[^stop]: `lifecycle/records`.

[^dropped]: `delivery/records` pins two `segments_dropped` records under different incarnations from
    one reclamation pass.

[^identity]: `pseudonym/vectors` pins values across four epochs and three separation contexts,
    demonstrating that differing epochs and differing contexts yield unrelated values.
    `telemetry/same_content_distinct_engine_ids` demonstrates property 2.

[^spaces]: `telemetry/content_id_rides_beside_the_engine_id`.

[^holder]: `telemetry/same_hash_distinct_instances`, `telemetry/same_hash_distinct_dp_ranks`,
    `telemetry/same_hash_distinct_groups`.

[^epoch]: `pseudonym/vectors`.

[^canary]: `lifecycle/records` pins the canary on all three lifecycle kinds.
    `reader/canary_split_key_material_is_not_a_measured_zero` is the two-producer,
    two-canary stream this section demanded: nothing on the wire relates the key spaces, and a
    reader that folds them on any heuristic grades the zero a measured absence and fails —
    the fold is what would let one mis-provisioned producer silence the alarm fleet-wide.

[^active]: `delivery/layout` states the in-progress segment name and the exclusion rule.

[^header]: `delivery/records` pins one sealed segment whole, header first.

[^orphan]: `delivery/records` pins `segment_recovered` in both the attributed and unattributed
    forms.

[^continuity]: `delivery/layout`.

[^restart]: `delivery/layout`.

[^gap]: `reader/gap_*`: one fixture per detected-gap class — a missing `segment_seq`, a nonzero
    `dropped` delta between heartbeats, a `segments_dropped` declaration — each expecting the
    window degraded, beside an intact stream expecting no degradation, which fails a reader
    that fabricates gap evidence. A restart at sequence zero rides the intact fixture and is
    not a gap (§5.2).

[^tail]: `vllm-wire/truncated_payload`, `vllm-wire/trailing_garbage`, `vllm-wire/garbage_bytes`.

[^unknown]: `vllm-wire/unknown_event_type`, `vllm-wire/unknown_alongside_known`.

[^clock]: `reader/clock_*`, deliberately declaring no verdict family of their own: this section
    adds no verdict, it constrains how every other verdict may be computed, so its fixtures are
    adversarial streams graded by the existing families. The engine clock displaced a month from
    the producer clock flips no staleness or audit verdict; a 2 ms cross-instance overlap reads
    as a measured absence under any plausible configured allowance, and a reader that omits the
    allowance manufactures simultaneity and fails; a ten-minute overlap survives, or the
    allowance is not one. The stamp-confinement half also rides
    `reader/refused_is_confined_by_its_window_not_its_stamp`.

[^incarnation]: `delivery/layout` states that continuity is scoped to instance and incarnation and
    that a fresh incarnation at sequence zero is a restart. `delivery/records` pins the incarnation
    token's presence in the header. `reader/incarnation_is_an_opaque_token` fails a reader that
    parses structure out of the token: a structureless incarnation must change no verdict.

[^bracket]: `reader/uncovered_*`: the stop-to-start bracket beside a continuously covered
    bystander; the crash case (no stop — the bracket opens at the last observation, this
    section's own fallback); the lost start (the bracket closes at the successor's first
    observation — it is provably running by its first record, and uncovered past that point
    would assert a non-observation the records refute); and the overlapping handover, which
    must yield no window at all.

[^lowerbound]: `reader/absence_*`: each fixture pairs a stream with a question span and the
    register a conforming reader may attach to absence over it — exact within a counted
    start-to-stop bracket with zero counter deltas, and a lower bound in each of this
    section's three MUST-NOT shapes: before the producer started, during a gap, outside
    any observed window.

[^coverage]: Both halves are covered. The qualified zero: `reader/zero_*` fixtures pin the
    qualification a conforming reader attaches (measured absence vs single holder vs no portable
    identity vs a positive finding). The coverage floor: `reader/coverage_*` fixtures pin the
    coverage attached to figures over a question span — exactly 1.0 over a counted bracket,
    strictly below it under inbound loss or under a tail no stop record closed.

[^contractver]: `delivery/records` pins `contract_version` in the sealed segment's header, and
    pins the unattributed orphan carrying none (`orphan_segment`), per §6.1. The reference
    producer emits it on every `segment_open`.

[^first]: `delivery/records` pins a sealed segment beginning with `segment_open`, pins
    `segment_recovered` in both forms, and pins a whole unattributed orphan beginning with the
    marker (`orphan_segment`).

[^multi]: `reader/gap_scope_*`: one incarnation covering two instances, a hole in its sequence,
    surviving records mentioning only one — both degrade, including the instance with no
    surviving records at all, while an instance covered by its own intact run stands. The
    fixture's stream is itself the first corpus artifact in which one incarnation covers
    several instances, so it discharges both halves of this requirement at once.

[^liveness]: `lifecycle/records` pins both declared bounds (`heartbeat_secs`,
    `max_segment_secs`). `reader/staleness_*` pins the verdict side: silence past the larger
    bound without a stop is unexplained, the same silence behind an `agent_stop` is a
    departure, the threshold is the larger bound and not the heartbeat bound alone, and a
    producer with no observed declaration supports no staleness verdict at all — each judged
    at the stream's knowledge horizon, never wall-clock now. The producer honours both bounds
    by pinned construction, covered by named tests in the producer's own suite: one holds
    the segment-age bound even on an event-quiet stream; the other sets the heartbeat deadline
    early by the poll loop's wake jitter, so the emitted gap never exceeds the declared bound.

[^unversioned]: `delivery/records` pins the unattributed orphan whole (`orphan_segment`): its
    marker takes the header position and carries no `contract_version`, byte-for-byte.
    `reader/audit_unattributed_recovery_supports_no_same_run_claim` ingests such an orphan
    through the shipped delivery path and reaches its verdict — a reader parsing the
    versionless segment under the mixed-fleet law, demonstrated rather than asserted.

[^idtype]: `telemetry/` fixtures ARE the unkeyed path — raw identities, pre-pseudonymization —
    and carry every identity as a decimal string; a producer emitting numbers fails all of them.
    Keyed output is hex strings by construction (`pseudonym/vectors`).

[^cleartier]: `telemetry/clear_tier_undeclared` (absent tier omitted) beside
    `telemetry/tier_absent_stays_null` (a block record's unknown tier stays null), and
    `telemetry/clear_scope_undeclared` for the scope dimensions.

[^extrakeys]: `telemetry/salted_partition` carries a salt on the block where it enters the chain
    and not on the blocks that follow, as the engine emitted it. Producer side input:
    `vllm-wire/stored_salted`.

[^constructed]: `vllm-wire/cleared_all` is marked constructed in the corpus itself, and
    `vllm-wire/cleared_scope_undeclared` pins the absent-scope handling. A captured clear would
    convert the assumption into an observation and re-cut the fixtures; until one exists, they pin
    this document's handling of an assumed shape rather than the shape.

[^audit]: `reader/audit_*`: six fixtures pairing input streams with the audit verdict a
    conforming reader reaches — the four no-false-alarm flows (re-store after eviction, evict
    before any store, restart mid-flight, offload and scope) and the two defect gradings
    (contradiction, lost promise).

[^unique]: `telemetry/same_content_distinct_engine_ids` demonstrates the identity matching where
    it must; `reader/identity_collision_claims_two_parents` fails a reader that folds
    contradictory parent claims instead of surfacing the count. For scale: a 64-bit identity's
    birthday bound is `N²/2^65` — negligible at 10⁶ distinct blocks, ~3% odds of a single merged
    pair somewhere at 10⁹ — and one merged pair contributes one block's tokens of error, orders
    below the coverage stated beside every figure.

[^refused]: `lifecycle/records` pins the record shape (`capacity_cases`), derived independently
    of the producer's builder. `reader/refused_*` pins the reader obligation: the named holder's
    figures read as lower bounds over exactly the declared window, the sibling worker and the
    out-of-window spans stand, and the record's own producer-clock `at_ms` — placed inside an
    innocent span in one fixture — must not confine the loss.

### Requirements with no covering fixture

**Empty as of 2026-08-01.** Every reader obligation in this specification is pinned by the
reader corpus (`conformance/reader/`: an input stream paired with the verdict a conforming
reader must reach), and every producer requirement by an emission corpus or by the named
producer test cited in the footnote beside it. The ledger this section carried is discharged
row by row in those footnotes, which is where the evidence lives.

The discipline that emptied it stands for anything new: a requirement enters this
specification **with** its covering fixture or named test, or it enters this table — and a
non-empty table gates publication of any release claiming conformance.

### Verification

Field names, types and presence rules in §2 were extracted from the conformance corpora and checked
against them, not transcribed. Last re-verified 2026-08-06, by recursive field-union extraction
across every corpus fixture compared against the §2 tables (provenance fields and fixture-harness
keys excluded). The inline examples in §2 are extracted from the fixtures they cite, never
composed by hand, and are covered by the same rule. The stamp refreshes whenever §2 or a corpus
changes; a stale stamp is a review finding.
