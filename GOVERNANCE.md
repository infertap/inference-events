# Contract governance

## Requirements and conformance

Submit normative requirements with a fixture that rejects a violating implementation.
For producer behavior a fixture cannot express, identify the covering test. Record any
uncovered requirement in the specification's conformance table. A release claiming
conformance must have no uncovered requirements.

## Corpus changes

Change corpus expectations in this repository with the specification change that motivates
them. Consumers pin and verify the corpus; they must not edit vendored expectations to
make an implementation pass. Derive expectations from the specification independently
of the implementation under test.

Documentation-only edits may update fixture descriptions without changing inputs or
expected results. Regenerate affected artifacts and update `CONTRACT_HASH` in the same
commit. The hash covers corpus bytes, including documentation.

## Versioning

New record kinds and optional fields require a wire minor increase. Changes to existing
meaning or requirements require a wire major increase. Review Rust package compatibility
separately. Readers must handle producer version skew as specified by the mixed-fleet rules.

## Review

Submit changes through a pull request with the relevant specification, fixtures, tests,
and contract hash together. See [CONTRIBUTING.md](CONTRIBUTING.md) for validation and
release procedures.
