#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m black --check tools
python3 tools/gen-schema.py --check
python3 tools/check-schema.py
python3 -m unittest discover -s tools -p 'test_*.py'
python3 tools/check-generation.py
for baseline in schema/baselines/*.json; do
  python3 tools/check-compatibility.py --against "$baseline" schema/records.schema.json
done
python3 tools/check-corpora.py
python3 tools/contract-hash.py --check
cargo fmt --all --check
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --locked
RUSTDOCFLAGS="-D warnings" cargo doc --workspace --no-deps --locked
cargo package -p inference-events --allow-dirty --locked
