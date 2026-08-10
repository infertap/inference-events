# Changelog

## v1.1 draft 6, 2026-08-10

Prose correction, one fixture note among it. §5.9's justification claimed the wrong
thing about the failure it forbids.

It said summing `store` records under an unlabelled declaration makes the figure "rise
with how effective the cache is." Holding a workload fixed, it does not. A block that
stops being recomputed starts being announced as a hit instead and contributes the same
tokens either way, so the sum is inserted plus reused and stays roughly flat whatever
the cache does. What rises is the error, not the figure.

The correction matters in the direction of the argument, not against it. A number that
climbs suspiciously invites a second look; one that quietly goes flat while the quantity
it is read as falls does not. The obligation in §5.9 is unchanged, and no MUST moves.

`reader/reuse_unlabelled_forbids_an_insertion_count`'s note carried the same claim, so
`CONTRACT_HASH` moves even though no fixture's input or expected verdict changes.

## v1.1 draft 5, 2026-08-09

One fixture re-cut. It did not test what it claimed, which makes it worse than no fixture:
a reader could drop the rule it exists to pin and still pass.

`reader/seq_across_an_incarnation_boundary_does_not_narrow` put `seq` 41 in the first
incarnation and 3 in the second. A *backwards* jump, which §5.4's forward-jump condition
already rejects on its own — so the incarnation guard the fixture was written for never had
to fire. Confirmed by deleting that guard from a reader and watching the corpus still pass.

The realistic shape is the opposite, and it is the ordinary case rather than a corner: an
incarnation is a **producer** run, and the engine publishing underneath it goes on numbering
straight through a producer restart. So the second run resumes at a much HIGHER number, and
the distance across the boundary is the uncovered window itself (§5.3) rather than a loss
inside an observed sequence. The fixture now runs 41 → 100, and a reader that narrows on it
exonerates precisely the span nothing observed.

No text changes and no field changes; `contract_version` stays `1.1`.

## v1.1 draft 4, 2026-08-09

Corrects §5.9, which was published over-broad. No field changes, no new fields, so
`contract_version` stays `1.1`.

- **The prohibition is on UNQUALIFIED counts.** As written, §5.9 forbade presenting "a count
  of `store` records, or a sum of `n_tokens` over them" as insertions — which reads as
  forbidding *every* aggregate over store records, including the one figure an `unlabelled`
  stream still fully supports. A reuse announcement describes a block the engine found
  **resident**, so it cannot follow an observed close of that block: the residency would have
  had to reopen unobserved, which is a lost record and therefore already a detected gap under
  §5.4. A recomputation figure — stores conditioned on an observed prior `evict` or `clear` —
  is safe under any declaration, and a reader MAY compute it.

- **The converse case gains its own MUST NOT.** Conditioning on *absent* prior residency is
  exactly where a reuse announcement and a first insertion are indistinguishable, because the
  block may have been resident since before observation began. A reader MUST NOT count such a
  store as a first insertion or a cold miss.

  Stated separately because the error does not decay. It is tempting to expect it to expire
  once the cache has turned over — but a block that is never evicted is never re-announced,
  and the hottest shared prefix in a fleet is the block least likely to be evicted. Left
  unstated, the miscount concentrates on exactly the traffic that matters most, and reports a
  cache as **less** effective than it is.

Three fixtures land with them, and the two declarations are pinned against each other on the
same shape of stream so a reader that answers both alike fails one.

**Verified across two engines.** The reference producer declares `unlabelled`: it builds a
prefix-cache hit and a fresh insertion through one shared builder, deliberately, so both
"emit identical event shapes for downstream consumers". A second engine's radix cache emits
`BlockStored` only for the newly inserted tail — its matched prefix increments an internal
counter and reaches no wire — which is `none`. Two engines, two states, from source. The
declaration is a real cross-engine axis rather than one engine's wart.

## v1.1 draft, 2026-08-09

Additive: four new optional fields, so the minor version increments and
`contract_version` becomes `1.1` (§6.1). No existing field changes meaning.

- **`seq` on cache records** — the transport sequence of the message an event arrived in,
  shared by every record derived from one message. §5.4 gains the narrowing rule it
  enables: a `dropped` delta localizes a loss no better than one heartbeat interval, and
  `seq` puts the discontinuity between two observed numbers. Narrowing is permitted only
  where **both** bracketing records carry `seq` in one incarnation — a bracket spanning a
  restart compares two different sequences, and would exonerate a span nothing observed.

- **`reuse_reporting` on the lifecycle records, `reused` on `store`, and §5.9.** Some
  engines announce a block *reused* from cache with the same event they use for one newly
  inserted, in a shape a consumer cannot tell apart. Summing `store` records on such a
  stream gives inserted plus reused with nothing separating them, so a block that stops
  being recomputed starts being announced as a hit instead and contributes the same tokens
  either way: the total barely moves while insertions fall. The producer declares which of
  three states it is in; §5.9 states the reader's obligation under each. Absence is not
  `"none"`, and neither is a value a later version defines: both read as `"unlabelled"`.

- **`spec_sliding_window` on `store`** — the group's window size beside its `spec_kind`.
  It is the geometry deciding which blocks an engine skips, which a consumer reasoning
  about a non-contiguous run needs.

- **`topic` on `endpoints[]`** — the transport channel name, relayed verbatim and unparsed.
  Deployments encode real identity there, but the conventions are the deployment's, so
  recognition is a reader's business, matched at exact arity with refusal as its only
  failure mode. Verbatim relay makes recognition retroactive over archived records.

## v1 draft, 2026-08-09

Corrections, no version change: nothing here alters a requirement or the meaning of a
field, so rule 3 asks for neither a minor nor a major increment.

- **`vllm-wire/cleared_all` and `cleared_scope_undeclared` re-cut.** Both gave the engine's
  clear event a `medium` and a `group_idx`, inferred from the two observed event kinds
  because a clear cannot be triggered on demand and so cannot be captured. The reference
  producer's own event definition declares **no fields at all**, so neither value can ride
  that event and both fixtures pinned a wire shape the engine cannot emit. The only scope a
  real clear carries is the data-parallel rank, from the batch envelope.

  The `clear` **record** schema is unchanged: `tier` and `group_idx` stay optional, because
  another engine may declare them and the telemetry corpus still pins that path. What
  narrowed is the companion corpus, toward what the reference engine actually does.

  §2.3 gains the general rule this instance illustrates: a capture bounds what may be
  *asserted*, not what exists, and where an event cannot be captured at all the producer's
  definition beats analogy with a neighbouring event.

- **§2.4's `content_unresolved` row corrected** from "lookups for which no honest
  `content_id` existed" to "records emitted with no `content_id`, one per omission". §3.1
  has always required a producer to "count each omission", and the two sentences described
  different quantities: one lookup can seed a run of many records, and a run whose shape
  denies it a lookup emits nothing identifiable while counting nothing at all. §3.1 was the
  normative statement; the table row was inconsistent with it.

## v1 draft, 2026-08-06

Initial public cut: KV cache event semantics v1, with its full conformance corpora
(telemetry, lifecycle, delivery, pseudonym, reader), the `vllm-wire` companion corpus with
its captured source data, the fixture generators, and the contract hash tool.
