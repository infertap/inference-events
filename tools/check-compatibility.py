#!/usr/bin/env python3
"""Conservatively classify structural schema changes against a released baseline."""
import argparse, json
from pathlib import Path


def breaking_changes(old, new):
    reasons = []
    for name, definition in old["$defs"].items():
        target = new["$defs"].get(name)
        if target is None:
            reasons.append(f"{name}: removed definition")
            continue
        for field, rule in definition.get("properties", {}).items():
            other = target.get("properties", {}).get(field)
            structural = lambda value: {
                k: v
                for k, v in value.items()
                if k not in ("description", "title", "x-presence")
            }
            if other is None or structural(rule) != structural(other):
                reasons.append(f"{name}.{field}: changed or removed field constraint")
        if set(target.get("required", [])) - set(definition.get("required", [])):
            reasons.append(f"{name}: added required field")
        for key in ("allOf", "additionalProperties"):
            if definition.get(key) != target.get(key):
                reasons.append(f"{name}: changed {key}")
    if old.get("x-content-construction") != new.get("x-content-construction"):
        reasons.append("content construction changed")
    return reasons


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--against", type=Path, required=True)
    p.add_argument("schema", type=Path)
    args = p.parse_args()
    old = json.loads(args.against.read_text())
    new = json.loads(args.schema.read_text())
    reasons = breaking_changes(old, new)
    old_major = int(old["x-contract-version"].split(".")[0])
    new_major = int(new["x-contract-version"].split(".")[0])
    if reasons and new_major <= old_major:
        raise SystemExit("Contract major must increase:\n" + "\n".join(reasons))
    print(
        "Compatibility check passed"
        + (": declared major change" if reasons else ": no breaking change detected")
    )


if __name__ == "__main__":
    main()
