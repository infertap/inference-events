# Changelog

## Unreleased

- Reject extension fields that collide with reserved wire fields during serialization.
- Add producer validation that rejects unknown event kinds.
- Replace string-only validation errors with structured paths and error categories.
- Generate field documentation and run the crate example as a doctest.
- Enforce schema-generation constraints, compatibility versioning, and corpus regeneration.

These changes do not alter the wire format. The validation error representation changes
Rust source compatibility; callers should use `ValidationError.path` and `.kind`.

## Contract 2.1

Add optional, pseudonymized backend identity to store and eviction records. Clarify
incomplete offload identity inputs and repeated residency announcements.

## Contract 2.0

- Define 128-bit content identities with the `sha256-chain-128-v2` construction.
- Provide a canonical JSON Schema, generated Rust types, and a physical column catalog.

## Contract 1.x

| Version | Contract change |
|---|---|
| 1.11 | Discard headerless recovered files and report their dropped bytes. |
| 1.10 | Add `holder_reset` for publisher sequence regressions. |
| 1.9 | Require Parquet for shipped segments. |
| 1.8 | Remove the reader torn-tail counter requirement. |
| 1.7 | Define Parquet segments and JSON Lines write-ahead records. |
| 1.6 | Complete eviction field definitions and corpus/schema checks. |
| 1.5 | Declare `key_epoch` on segment headers. |
| 1.4 | Add a machine-readable column catalog. |
| 1.3 | Declare liveness bounds on segment headers. |
| 1.2 | Declare provenance and workload classification on segment headers. |

Use the current specification for requirements. This changelog records contract changes;
it does not define additional requirements.
