# inference-events

Event contracts and Rust wire types for inference telemetry.

The KV cache contract defines stores, evictions, clears, producer lifecycle, and segment
delivery. Records carry identity, scope, and observation coverage so readers can interpret
cache history across engines and storage tiers.

## Rust model

The `inference-events` crate provides generated types and checked JSON boundaries.
`Record::decode` validates known records and preserves future kinds and extension fields.
`validate_producer_record` rejects kinds outside the current schema. `validate_field`
supports projected columnar reads.

See the [crate example](crates/model/README.md) and [validation boundaries](docs/architecture.md).
The model validates individual records. Stream semantics are defined by the specification
and conformance corpus.

## Reference

- [KV cache specification](spec/kv-cache-v2.md): wire contract 2.1, identity, delivery, and reader obligations.
- [Record fields](docs/record-fields.md): generated field reference.
- [Architecture](docs/architecture.md): schema generation, validation, and compatibility.
- [Conformance corpus](conformance/): producer and reader expectations, identity vectors, and encoding fixtures.
- [Captured inputs](capture/): engine wire data from synthetic traffic used by the wire corpus.

`schema/records.schema.json` is the structural authority. JSON Lines and Parquet carry the
same record model. The wire contract uses 128-bit content identities; pseudonymized
identities are 32 hexadecimal characters.

The Rust package follows semantic versioning independently of the wire contract.
Validation workflows do not publish packages.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development and release checks, and
[GOVERNANCE.md](GOVERNANCE.md) for contract changes. Security reports go through
[SECURITY.md](SECURITY.md).

Licensed under Apache-2.0.
