# Record fields

Generated from `schema/records.schema.json`. See the specification for stream semantics.

## Endpoint

| Field | JSON type | Presence | Description |
|---|---|---|---|
| `dropped` | `integer` | required | Inbound messages known lost on this subscription. |
| `endpoint` | `string` | required | Configured subscription endpoint. |
| `last_msg_at_ms` | `number` | optional | Producer-clock timestamp of the last observed message, in milliseconds. |
| `msgs_seen` | `integer` | required | Inbound messages observed on this subscription. |
| `publisher_restarts` | `integer` | optional | Sequence regressions observed on this subscription. |
| `source` | `string` | required | Operator-defined source name for this subscription. |
| `topic` | `string` | optional | Configured subscription topic. |

## agent_start

| Field | JSON type | Presence | Description |
|---|---|---|---|
| `kind` | `string` | required | Record discriminator: `agent_start`. |
| `at_ms` | `number` | required | Producer clock. |
| `agent_version` | `string` | required | Producer version. |
| `egress` | `string` | required | One of `pseudonymized` or `raw`. `raw` means identities are emitted unprotected and §3's key-space rules do not apply. |
| `endpoint_count` | `integer` | required | Subscriptions configured. |
| `max_payload_bytes` | `integer` | required | Largest inbound engine message accepted. |
| `canary` | `string` | conditional | Present when identities are keyed (§3.4). |
| `reuse_reporting` | `string` | optional | `none` \| `labelled` \| `unlabelled`; whether this producer's engine announces cache reuse as a `store`, and whether it can be told apart (§2.3). |

## agent_stop

| Field | JSON type | Presence | Description |
|---|---|---|---|
| `kind` | `string` | required | Record discriminator: `agent_stop`. |
| `at_ms` | `number` | required | Producer clock. |
| `reason` | `string` | required | Why the run ended. |
| `msgs_seen` | `integer` | required | Inbound messages observed on this subscription. |
| `dropped` | `integer` | required | Inbound messages known lost on this subscription. |
| `oversized` | `integer` | required | Inbound messages refused for size. |
| `unknown_types` | `integer` | required | Inbound messages of unmodelled type. |
| `events_ingested` | `integer` | required | Events that reached the record model. |
| `content_unresolved` | `integer` | required | Records emitted with no `content_id`, one per omission (§3.1). |
| `content_bridge_entries` | `integer` | required | Identity-derivation state size (the producer's view of the resident set). |
| `content_bridge_evicted` | `integer` | required | Identity promises refused at the declared capacity; nonzero means some evicts will not resolve, each window also declared via `identity_refused`. |
| `publisher_restarts` | `integer` | required | Sequence regressions observed on this subscription; the envelope's `publisher_restarts` is their sum, and `holder_reset` (§2.3) is the record a reader acts on. |
| `reuse_reporting` | `string` | optional | `none` \| `labelled` \| `unlabelled`; whether this producer's engine announces cache reuse as a `store`, and whether it can be told apart (§2.3). |
| `endpoints` | `array` | required | Per-subscription statistics. |
| `canary` | `string` | conditional | Present when identities are keyed (§3.4). |

## clear

| Field | JSON type | Presence | Description |
|---|---|---|---|
| `kind` | `string` | required | Record discriminator: `clear`. |
| `at_ms` | `number` | required | Engine clock. |
| `instance_id` | `string` | required | The engine process holding this cache, named by the operator (§3.2). |
| `scope` | `string` | required | What was cleared, for example `all`. |
| `dp_rank` | `integer` | optional | The data parallel worker the clear applies to; **absent means the wire declared none and the clear is global across workers** (§3.2 and the note below). |
| `group_idx` | `integer` | optional | Cache group affected by the clear. Omission applies the clear across all groups. |
| `tier` | `string` | optional | Storage tier the clear applied to; **absent means the clear is global across tiers**. |
| `seq` | `integer` | optional | Transport sequence of the message that carried this event. |

## evict

| Field | JSON type | Presence | Description |
|---|---|---|---|
| `kind` | `string` | required | Record discriminator: `evict`. |
| `at_ms` | `number` | required | Engine clock. |
| `instance_id` | `string` | required | The engine process whose cache the block left (§3.2). |
| `block_id` | `string` | required | Engine-local identity (§3.1), the same value its `store` carried. |
| `tier` | `['string', 'null']` | optional | Storage tier the block left. A block offloaded to another tier is evicted from the one it left. |
| `dp_rank` | `integer` | optional | The data parallel worker within that instance (§3.2). |
| `group_idx` | `integer` | optional | The cache group within that worker (§3.2). |
| `content_id` | `string` | optional | Portable identity (§3.1), resolved from the producer’s identity state. |
| `locality` | `string` | optional | `LOCAL` or `REMOTE`, relative to the publishing holder. |
| `seq` | `integer` | optional | Transport sequence of the message that carried this event. |
| `epoch` | `integer` | optional | Pseudonymization key epoch. |
| `backend_id` | `string` | optional | Optional engine-emitted backend identity, scoped to publisher incarnation, rank, group and tier. Pseudonymized at egress. |

## heartbeat

| Field | JSON type | Presence | Description |
|---|---|---|---|
| `kind` | `string` | required | Record discriminator: `heartbeat`. |
| `at_ms` | `number` | required | Producer clock. |
| `msgs_seen` | `integer` | required | Inbound messages observed on this subscription. |
| `dropped` | `integer` | required | Inbound messages known lost on this subscription. |
| `oversized` | `integer` | required | Inbound messages refused for size. |
| `unknown_types` | `integer` | required | Inbound messages of unmodelled type. |
| `events_ingested` | `integer` | required | Events that reached the record model. |
| `content_unresolved` | `integer` | required | Records emitted with no `content_id`, one per omission (§3.1). |
| `content_bridge_entries` | `integer` | required | Identity-derivation state size (the producer's view of the resident set). |
| `content_bridge_evicted` | `integer` | required | Identity promises refused at the declared capacity; nonzero means some evicts will not resolve, each window also declared via `identity_refused`. |
| `publisher_restarts` | `integer` | required | Sequence regressions observed on this subscription; the envelope's `publisher_restarts` is their sum, and `holder_reset` (§2.3) is the record a reader acts on. |
| `endpoints` | `array` | required | Per-subscription statistics. |
| `canary` | `string` | conditional | Present when identities are keyed (§3.4). |
| `reuse_reporting` | `string` | optional | `none` \| `labelled` \| `unlabelled`; whether this producer's engine announces cache reuse as a `store`, and whether it can be told apart (§2.3). |
| `noraw_scanned` | `integer` | optional | Values checked by the producer's egress guard. |
| `rss_bytes` | `integer` | optional | Producer resident memory. |

## holder_reset

| Field | JSON type | Presence | Description |
|---|---|---|---|
| `kind` | `string` | required | Record discriminator: `holder_reset`. |
| `at_ms` | `number` | required | Producer clock at detection (§2.6). |
| `instance_id` | `string` | required | The engine the regressed source observes (§3.2). |
| `dp_rank` | `integer` | optional | The worker whose publisher regressed; **absent means the source hosts every rank and the reset is global across workers**. |
| `group_idx` | `integer` | optional | Cache group affected by the reset. Omit this field for a publisher sequence regression, which resets all groups. |
| `boundary_ms` | `number` | required | **engine clock**: the earliest event timestamp in the regressed message; the instant the reset is ordered at. |
| `seq` | `integer` | optional | The regressed sequence number, as the wire carried it. |

## identity_refused

| Field | JSON type | Presence | Description |
|---|---|---|---|
| `kind` | `string` | required | Record discriminator: `identity_refused`. |
| `at_ms` | `number` | required | Producer clock. |
| `instance_id` | `string` | required | The affected instance (§3.2). |
| `dp_rank` | `integer` | required | The affected worker. |
| `group_idx` | `integer` | required | The affected cache group. |
| `refused` | `integer` | required | Stores denied an identity in the window. |
| `window_start_ms` | `number` | required | **engine clock**: first refused store. |
| `window_end_ms` | `number` | required | **engine clock**: last refused store. |

## segment_open

| Field | JSON type | Presence | Description |
|---|---|---|---|
| `kind` | `string` | required | Record discriminator: `segment_open`. |
| `at_ms` | `number` | required | Producer clock. |
| `incarnation` | `string` | required | Identifies one run of one producer (§4.2). |
| `segment_seq` | `integer` | required | Position in that incarnation's sequence, from zero. |
| `contract_version` | `string` | required | The version of this contract the segment conforms to (§6.1). |
| `workload_class` | `string` | optional | Purpose of this producer’s traffic, in the operator's vocabulary (§2.7). |
| `heartbeat_secs` | `integer` | required | Declared heartbeat interval (§5.8). |
| `max_segment_secs` | `integer` | required | Declared maximum segment age (§5.8). |
| `key_epoch` | `integer` | conditional | Present when identities are keyed (§3.3). |

## segment_recovered

| Field | JSON type | Presence | Description |
|---|---|---|---|
| `kind` | `string` | required | Record discriminator: `segment_recovered`. |
| `at_ms` | `number` | required | Producer clock. |
| `attributed` | `boolean` | required | Whether the unfinished segment's own identity was readable. |
| `dropped_bytes` | `integer` | required | Bytes discarded: the trailing incomplete record of an attributed recovery, or the whole unattributable file. |

## segments_dropped

| Field | JSON type | Presence | Description |
|---|---|---|---|
| `kind` | `string` | required | Record discriminator: `segments_dropped`. |
| `at_ms` | `number` | required | Producer clock. |
| `incarnation` | `string` | required | The run whose data is gone, not the run that reclaimed it. |
| `count` | `integer` | required | Segments reclaimed. |
| `first_seq` | `integer` | required | Lowest `segment_seq` reclaimed. |
| `last_seq` | `integer` | required | Highest `segment_seq` reclaimed. |
| `first` | `string` | required | Filename of the first segment reclaimed. |
| `last` | `string` | required | Filename of the last segment reclaimed. |

## store

| Field | JSON type | Presence | Description |
|---|---|---|---|
| `kind` | `string` | required | Record discriminator: `store`. |
| `at_ms` | `number` | required | Engine clock. |
| `instance_id` | `string` | required | The engine process holding this cache, named by the operator (§3.2). |
| `block_id` | `string` | required | Engine-local identity (§3.1). |
| `n_tokens` | `integer` | required | Tokens the block holds. |
| `tier` | `['string', 'null']` | required | Storage tier, for example `GPU`. |
| `dp_rank` | `integer` | optional | The data parallel worker within that instance, which holds its own independent cache (§3.2). |
| `group_idx` | `integer` | optional | The cache group within that worker. Groups hash independently (§3.2). |
| `content_id` | `string` | optional | Portable identity (§3.1). Absent where the producer could not derive one. |
| `parent_id` | `string` | optional | The preceding block in this block's prefix chain. |
| `parent_unknown` | `boolean` | optional | True when the parent exists but its portable identity could not be resolved. Omit `parent_id` in this case. |
| `locality` | `string` | optional | `LOCAL` or `REMOTE`, relative to the publishing holder. |
| `extra_keys` | `array` | optional | Additional inputs to this block's identity beyond its tokens, for example a cache salt or a multimodal content hash. Operator controlled text, so each element is pseudonymized independently. |
| `lora_id` | `integer` | optional | Adapter identifier. |
| `lora_name` | `string` | optional | Adapter name. |
| `spec_kind` | `string` | optional | Attention kind, for example `full_attention`. |
| `spec_sliding_window` | `integer` | optional | The sliding-window size of this block's cache group, where the engine declares one. |
| `reused` | `boolean` | optional | This record reports a block already cached rather than a fresh insertion. Only under `reuse_reporting: "labelled"` (§2.4). |
| `seq` | `integer` | optional | Transport sequence of the message that carried this event. |
| `epoch` | `integer` | optional | Pseudonymization key epoch. |
| `backend_id` | `string` | optional | Optional engine-emitted backend identity, scoped to publisher incarnation, rank, group and tier. Pseudonymized at egress. |
