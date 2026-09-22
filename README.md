# inference-events

Event contracts for inference engines: the facts layer, with coverage declared.

Per-instance aggregate metrics destroy four properties of engine state before anything is
exported: identity (which block, not how many), cause, simultaneity, and history. None can be
recovered by sampling more often, because the information is destroyed at the source. The
contracts in this repository preserve all four by specifying per-event facts with stable
identity, explicit scope, and an accounting of what was and was not observed.

## What is here

- **`spec/kv-cache-v2.md`**: KV cache event semantics, v2. The first contract: records for
  cache stores, evictions and clears; producer lifecycle and delivery records; identity and
  pseudonymization rules; and the reader obligations that keep derived figures honest.
- **`conformance/`**: the executable half of the contract. Emission corpora pin what a
  producer emits, byte for byte. The reader corpus pairs input streams with the verdict a
  conforming reader must reach. `CONTRACT_HASH` is a single value that moves when, and only
  when, the contract moves; consumers pin it.
- **`tools/`**: the generators that derive every fixture independently of any implementation,
  and the contract hash tool.
- **`capture/`**: captured engine wire data (synthetic traffic) that the `vllm-wire` fixtures
  derive from, kept so the corpus is reproducible from observed bytes rather than from
  anyone's implementation.

## Where this sits

OpenTelemetry's gen-ai conventions instrument the application that calls a model: requests,
completions, spans around an API. This project is the layer below: what happened inside the
engine while it served. The two are complementary and share no schema.

## Conformance

Conformance is a property of the record stream, not of the process that writes it. An engine
can emit records natively and be the producer; an adapter observing an engine's native
telemetry can be the producer for it. The spec's section 8 carries a checklist for each role,
and every row cites the fixture that fails a violator.

The corpora are derived from the specification's normative text by the generators in
`tools/`, never from a reference implementation. Two independent implementations meeting at
the same fixtures is the arrangement that makes passing mean something.

## Rust model

The `inference-events` crate provides generated wire records and structural validation.
`Record::decode` validates complete JSON records and preserves unknown fields and kinds.
`validate_field` supports projected columnar reads. Stream-level semantics remain defined
in the specification and independently tested by the conformance corpora.

`schema/records.schema.json` is the structural authority. Run `python3 tools/gen-schema.py`
to regenerate Rust types, column definitions and the field reference. Markdown formatting
does not control the schema. To check a contribution:

```sh
python3 -m pip install -r tools/requirements.txt
scripts/preflight.sh
```

## Status

Initial public 1.0 package in preparation. The wire contract is 2.0; the major revision
identifies the 128-bit content construction. Discard pre-release development data before
using the new construction. No package is published by the validation workflow.

 `infertap` is the reference producer; the `vllm-wire` corpus documents its mapping
from vLLM's native events, from captured bytes of synthetic traffic. Additional event
families (scheduler, request lifecycle, tier transfer) are candidates for sibling contracts
in this repository; they will be specified when a second concrete domain exists, not before.

## Governance and license

Changes land under the rules in [GOVERNANCE.md](GOVERNANCE.md). Everything here is
Apache-2.0.
