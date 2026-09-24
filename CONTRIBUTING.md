# Contributing

Read the [architecture](docs/architecture.md) and [governance rules](GOVERNANCE.md)
before changing the contract. Submit changes through a pull request with signed-off
commits (`git commit -s`). Keep each commit focused on one change.

## Development

Use the Rust toolchain pinned in `rust-toolchain.toml` and Python 3.9 or newer.
Install development dependencies in a virtual environment:

```sh
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r tools/requirements.txt -r tools/generation-requirements.txt
scripts/preflight.sh
```

The preflight checks all Python formatting, generated artifacts, schema acceptance,
compatibility, corpus consistency, Rust formatting, Clippy, tests, documentation,
and package contents. CI also checks the minimum Rust version and dependency policy.

Edit the canonical schema and run `python3 tools/gen-schema.py` to update bindings
and reference documentation. Change fixtures only with the specification or schema
change that motivates them. Regenerate the contract hash with
`python3 tools/contract-hash.py --write` when corpus bytes change.

Tests must cover observable behavior, including rejected inputs. Keep fixture expectations
independent of consumer implementations. Write comments that explain constraints or intent;
put user-facing behavior in the reference documentation.

## Release review

1. Review wire compatibility against the latest released schema baseline. Add a baseline
   for each released wire version and update the preflight comparison for the next cycle.
2. Review Rust API compatibility separately. Set the package version and record changes
   in `CHANGELOG.md`. Wire and package versions need not match.
3. Run the preflight and inspect CI results for the exact release commit. Confirm the
   conformance checklist has no uncovered requirements. Test consumer integration.
4. Review `cargo package --list -p inference-events` and the packaged crate's documentation.
5. After maintainer approval, publish the crate and create the corresponding release tag.

Publishing is a separate maintainer action. A passing validation workflow does not publish.

## Documentation and comments

Describe current behavior, constraints, and the rationale needed to maintain the code.
Keep user-visible changes in the changelog. Internal audit reports, work plans, debugging
narratives, machine logs, and operational transcripts do not belong in the public tree.
Retain test inputs and concise provenance needed to reproduce conformance fixtures.
