# Production data-model implementation

## Scope and acceptance

Ship a reusable, machine-validated contract for the existing JSONL and Parquet pipeline.
Use 128-bit content identities before the initial public release. Preserve 128-bit emitted
pseudonyms, the tap's typed privacy boundary, and the analyzer's complete identity strings.
Existing development artifacts must not be mixed with the new identity generation.
Deployment acceptance is verified separately from model conformance.

## Work sequence

1. Establish an authoritative JSON Schema in inference-events. Express record kinds,
   required fields, omitted versus null values, numeric bounds, nested endpoints, extensions,
   and record-local conditional constraints. Generate the physical column catalog and field
   reference from this source. Retain prose for stream semantics.
2. Add a versioned Rust wire-model crate with reproducible generated record types and
   structural validation. Keep raw/pseudonymized internal state outside this wire package.
   Preserve unknown records/fields for forward-compatible readers.
3. Add upstream gates: schema validation, positive and negative examples, deterministic
   generation, package checks, compatibility classification, and independent conformance.
   Correct the claim that all identity collisions are detectable.
4. Define the 128-bit content construction, byte order, root, context and pseudonym input.
   Add independent vectors and update affected upstream corpora. Record the identity
   generation explicitly so development streams cannot silently mix constructions.
5. Integrate the pinned model into the tap. Separate engine u64 identities from content
   u128 identities, update resident-state budgeting and pseudonymization, retain existing
   output width, and verify the full producer suite.
6. Integrate the shared wire model into the analyzer's segment boundary through its segment boundary. Preserve projected Parquet reads, schema evolution and full
   identity grouping. Verify decoding, analyzer semantics and generation separation.
7. Run cross-repository JSONL/Parquet round trips, all required local gates, and review
   diffs. Use pull requests for review. Publishing packages is a separate release action.

## Decisions

- JSON Schema is the structural authority. Markdown describes behavior and includes a
  generated field reference; parsing Markdown no longer determines the wire schema.
- Rust bindings provide wire types and validation. They do not replace the tap's sealed
  raw/pseudonymized phases or the analyzer's execution-specific internal model.
- Generator tests must not be the only evidence: independent vectors and negative cases
  verify the meaning, not merely agreement between generated files.

## Completion record

Pending implementation and verification. No release-readiness claim is made by this plan.
