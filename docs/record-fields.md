# Record fields

Generated from `schema/records.schema.json`. See the specification for stream semantics.

## Endpoint

| Field | JSON type | Presence | Description |
|---|---|---|---|
| `dropped` | `integer` | required |  |
| `endpoint` | `string` | required |  |
| `last_msg_at_ms` | `number` | optional |  |
| `msgs_seen` | `integer` | required |  |
| `publisher_restarts` | `integer` | optional |  |
| `source` | `string` | required |  |
| `topic` | `string` | optional |  |

## agent_start

| Field | JSON type | Presence | Description |
|---|---|---|---|
| `kind` | `string` | required |  |
| `at_ms` | `number` | required | producer clock |
| `agent_version` | `string` | required | producer version |
| `egress` | `string` | required | one of `pseudonymized` or `raw`. `raw` means identities are emitted unprotected and §3's key-space rules do not apply |
| `endpoint_count` | `integer` | required | subscriptions configured |
| `max_payload_bytes` | `integer` | required | largest inbound engine message accepted |
| `canary` | `string` | conditional | present when identities are keyed (§3.4) |
| `reuse_reporting` | `string` | optional | as `heartbeat` |

## agent_stop

| Field | JSON type | Presence | Description |
|---|---|---|---|
| `kind` | `string` | required |  |
| `at_ms` | `number` | required | producer clock |
| `reason` | `string` | required | why the run ended |
| `msgs_seen` | `integer` | required | as `heartbeat` |
| `dropped` | `integer` | required | as `heartbeat` |
| `oversized` | `integer` | required | as `heartbeat` |
| `unknown_types` | `integer` | required | as `heartbeat` |
| `events_ingested` | `integer` | required | as `heartbeat` |
| `content_unresolved` | `integer` | required | as `heartbeat` |
| `content_bridge_entries` | `integer` | required | as `heartbeat` |
| `content_bridge_evicted` | `integer` | required | as `heartbeat` |
| `publisher_restarts` | `integer` | required | as `heartbeat` |
| `reuse_reporting` | `string` | optional | as `heartbeat` |
| `endpoints` | `array` | required | as `heartbeat` |
| `canary` | `string` | conditional | present when identities are keyed (§3.4) |

## clear

| Field | JSON type | Presence | Description |
|---|---|---|---|
| `kind` | `string` | required |  |
| `at_ms` | `number` | required | engine clock |
| `instance_id` | `string` | required | the engine process holding this cache, named by the operator (§3.2) |
| `scope` | `string` | required | what was cleared, for example `all` |
| `dp_rank` | `integer` | optional | the data parallel worker the clear applies to; **absent means the wire declared none and the clear is global across workers** (§3.2 and the note below) |
| `group_idx` | `integer` | optional | as `dp_rank`, for cache groups |
| `tier` | `string` | optional | storage tier the clear applied to; **absent means the clear is global across tiers** |
| `seq` | `integer` | optional | as `store` |

## evict

| Field | JSON type | Presence | Description |
|---|---|---|---|
| `kind` | `string` | required |  |
| `at_ms` | `number` | required | engine clock |
| `instance_id` | `string` | required | the engine process whose cache the block left (§3.2) |
| `block_id` | `string` | required | engine-local identity (§3.1), the same value its `store` carried |
| `tier` | `['string', 'null']` | optional | storage tier the block left. A block offloaded to another tier is evicted from the one it left |
| `dp_rank` | `integer` | optional | the data parallel worker within that instance (§3.2) |
| `group_idx` | `integer` | optional | the cache group within that worker (§3.2) |
| `content_id` | `string` | optional | portable identity (§3.1), resolved by the producer as described below |
| `locality` | `string` | optional | `LOCAL` or `REMOTE`, relative to the publishing holder |
| `seq` | `integer` | optional | transport sequence of the message that carried this event |
| `epoch` | `integer` | optional | Pseudonymization key epoch. |

## heartbeat

| Field | JSON type | Presence | Description |
|---|---|---|---|
| `kind` | `string` | required |  |
| `at_ms` | `number` | required | producer clock |
| `msgs_seen` | `integer` | required | inbound messages observed on this subscription |
| `dropped` | `integer` | required | inbound messages known lost on this subscription |
| `oversized` | `integer` | required | inbound messages refused for size |
| `unknown_types` | `integer` | required | inbound messages of unmodelled type |
| `events_ingested` | `integer` | required | events that reached the record model |
| `content_unresolved` | `integer` | required | records emitted with no `content_id`, one per omission (§3.1) |
| `content_bridge_entries` | `integer` | required | identity-derivation state size (the producer's view of the resident set) |
| `content_bridge_evicted` | `integer` | required | identity promises refused at the declared capacity — nonzero means some evicts will not resolve, each window also declared via `identity_refused` |
| `publisher_restarts` | `integer` | required | sequence regressions observed on this subscription; the envelope's `publisher_restarts` is their sum, and `holder_reset` (§2.3) is the record a reader acts on |
| `endpoints` | `array` | required | per-subscription statistics, below |
| `canary` | `string` | conditional | present when identities are keyed (§3.4) |
| `reuse_reporting` | `string` | optional | `none` \| `labelled` \| `unlabelled` — whether this producer's engine announces cache reuse as a `store`, and whether it can be told apart (§2.3) |
| `noraw_scanned` | `integer` | optional | values checked by the producer's egress guard |
| `rss_bytes` | `integer` | optional | producer resident memory |

## holder_reset

| Field | JSON type | Presence | Description |
|---|---|---|---|
| `kind` | `string` | required |  |
| `at_ms` | `number` | required | producer clock at detection (§2.6) |
| `instance_id` | `string` | required | the engine the regressed source observes (§3.2) |
| `dp_rank` | `integer` | optional | the worker whose publisher regressed; **absent means the source hosts every rank and the reset is global across workers** |
| `group_idx` | `integer` | optional | as `dp_rank`; a producer deriving the reset from a sequence regression MUST omit it, because a process restart is never group-scoped |
| `boundary_ms` | `number` | required | **engine clock**: the earliest event timestamp in the regressed message — the instant the reset is ordered at |
| `seq` | `integer` | optional | the regressed sequence number, as the wire carried it |

## identity_refused

| Field | JSON type | Presence | Description |
|---|---|---|---|
| `kind` | `string` | required |  |
| `at_ms` | `number` | required | producer clock |
| `instance_id` | `string` | required | the affected instance (§3.2) |
| `dp_rank` | `integer` | required | the affected worker |
| `group_idx` | `integer` | required | the affected cache group |
| `refused` | `integer` | required | stores denied an identity in the window |
| `window_start_ms` | `number` | required | **engine clock**: first refused store |
| `window_end_ms` | `number` | required | **engine clock**: last refused store |

## segment_open

| Field | JSON type | Presence | Description |
|---|---|---|---|
| `kind` | `string` | required |  |
| `at_ms` | `number` | required | producer clock |
| `incarnation` | `string` | required | identifies one run of one producer (§4.2) |
| `segment_seq` | `integer` | required | position in that incarnation's sequence, from zero |
| `contract_version` | `string` | required | the version of this contract the segment conforms to (§6.1) |
| `workload_class` | `string` | optional | what this producer's traffic is FOR, in the operator's vocabulary (§2.7). Since 1.2 |
| `heartbeat_secs` | `integer` | required | declared heartbeat interval (§5.8). Since 1.3 |
| `max_segment_secs` | `integer` | required | declared maximum segment age (§5.8). Since 1.3 |
| `key_epoch` | `integer` | conditional | present when identities are keyed (§3.3). Since 1.5 |

## segment_recovered

| Field | JSON type | Presence | Description |
|---|---|---|---|
| `kind` | `string` | required |  |
| `at_ms` | `number` | required | producer clock |
| `attributed` | `boolean` | required | whether the unfinished segment's own identity was readable |
| `dropped_bytes` | `integer` | required | bytes discarded: the trailing incomplete record of an attributed recovery, or the whole unattributable file |

## segments_dropped

| Field | JSON type | Presence | Description |
|---|---|---|---|
| `kind` | `string` | required |  |
| `at_ms` | `number` | required | producer clock |
| `incarnation` | `string` | required | the run whose data is gone, not the run that reclaimed it |
| `count` | `integer` | required | segments reclaimed |
| `first_seq` | `integer` | required | lowest `segment_seq` reclaimed |
| `last_seq` | `integer` | required | highest `segment_seq` reclaimed |
| `first` | `string` | required | filename of the first segment reclaimed |
| `last` | `string` | required | filename of the last segment reclaimed |

## store

| Field | JSON type | Presence | Description |
|---|---|---|---|
| `kind` | `string` | required |  |
| `at_ms` | `number` | required | engine clock |
| `instance_id` | `string` | required | the engine process holding this cache, named by the operator (§3.2) |
| `block_id` | `string` | required | engine-local identity (§3.1) |
| `n_tokens` | `integer` | required | tokens the block holds |
| `tier` | `['string', 'null']` | required | storage tier, for example `GPU` |
| `dp_rank` | `integer` | optional | the data parallel worker within that instance, which holds its own independent cache (§3.2) |
| `group_idx` | `integer` | optional | the cache group within that worker. Groups hash independently (§3.2) |
| `content_id` | `string` | optional | portable identity (§3.1). Absent where the producer could not derive one |
| `parent_id` | `string` | optional | the preceding block in this block's prefix chain |
| `parent_unknown` | `boolean` | optional | see below |
| `locality` | `string` | optional | `LOCAL` or `REMOTE`, relative to the publishing holder |
| `extra_keys` | `array` | optional | additional inputs to this block's identity beyond its tokens, for example a cache salt or a multimodal content hash. Operator controlled text, so each element is pseudonymized independently |
| `lora_id` | `integer` | optional | adapter identifier |
| `lora_name` | `string` | optional | adapter name |
| `spec_kind` | `string` | optional | attention kind, for example `full_attention` |
| `spec_sliding_window` | `integer` | optional | the sliding-window size of this block's cache group, where the engine declares one |
| `reused` | `boolean` | optional | this record reports a block already cached rather than a fresh insertion. Only under `reuse_reporting: "labelled"` (§2.4) |
| `seq` | `integer` | optional | transport sequence of the message that carried this event (below) |
| `epoch` | `integer` | optional | Pseudonymization key epoch. |
