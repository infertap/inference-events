#!/usr/bin/env python3
"""Regenerate artifacts in isolation and compare them with the committed corpus."""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pyarrow.parquet as parquet

ROOT = Path(__file__).resolve().parent.parent
GENERATORS = (
    "schema",
    "identity-corpus",
    "backend-corpus",
    "delivery-corpus",
    "lifecycle-corpus",
    "reader-corpus",
    "telemetry-corpus",
    "parquet-twin",
)
ARTIFACTS = (
    "conformance",
    "crates/model/src/generated.rs",
    "crates/model/schema",
    "crates/model/tests/structure.json",
    "docs/record-fields.md",
)


def snapshot(root):
    paths = []
    for name in ARTIFACTS:
        path = root / name
        paths.extend(path.rglob("*") if path.is_dir() else [path])
    return {path.relative_to(root): path for path in paths if path.is_file()}


def equivalent(before, after):
    if before.suffix == ".parquet":
        # Encoder metadata may vary by platform; column types and values must not.
        return parquet.read_table(before).equals(
            parquet.read_table(after), check_metadata=True
        )
    return before.read_bytes() == after.read_bytes()


def main():
    with tempfile.TemporaryDirectory(
        prefix="inference-events-generation-"
    ) as temporary:
        root = Path(temporary)
        for directory in (
            "tools",
            "schema",
            "conformance",
            "capture",
            "crates",
            "docs",
        ):
            shutil.copytree(ROOT / directory, root / directory)
        shutil.copy2(ROOT / "rust-toolchain.toml", root)
        for name in GENERATORS:
            subprocess.run(
                [sys.executable, f"tools/gen-{name}.py"], cwd=root, check=True
            )
        manifest = json.loads(
            (ROOT / "conformance/vllm-wire/manifest.json").read_text()
        )
        subprocess.run(
            [sys.executable, "tools/gen-vllm-wire-corpus.py", *manifest["captures"]],
            cwd=root,
            check=True,
        )
        before, after = snapshot(ROOT), snapshot(root)
        changed = [
            str(path)
            for path in before.keys() | after.keys()
            if path not in before
            or path not in after
            or not equivalent(before[path], after[path])
        ]
        if changed:
            raise SystemExit(
                "Generated artifacts differ:\n" + "\n".join(sorted(changed))
            )
    print("All generated artifacts are current")


if __name__ == "__main__":
    main()
