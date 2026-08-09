# Changelog

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
