#!/usr/bin/env python3
"""Classify schema changes and enforce the wire contract's version policy."""
import argparse
import json
import re
from pathlib import Path

ANNOTATIONS = {"$id", "title", "description", "x-section"}


def structural(value):
    """Remove documentation without discarding validation or physical layout rules."""
    if not isinstance(value, dict):
        return value
    result = {}
    for key, child in value.items():
        if key in ANNOTATIONS:
            continue
        if key in {"properties", "$defs"}:
            result[key] = {name: structural(rule) for name, rule in child.items()}
        elif key in {"allOf", "oneOf"}:
            result[key] = [structural(rule) for rule in child]
        elif key in {"items", "if", "then", "not"}:
            result[key] = structural(child)
        else:
            result[key] = child
    return result


def classify_changes(old, new):
    """Return breaking and additive changes; unknown rule changes are breaking."""
    breaking, additive = [], []

    def compare(left, right, path, mapping=False):
        if left == right:
            return
        if not isinstance(left, dict) or not isinstance(right, dict):
            breaking.append(f"{path}: changed constraint")
            return
        for key in left.keys() | right.keys():
            location = f"{path}.{key}"
            if key not in right:
                breaking.append(f"{location}: removed rule or field")
            elif key not in left:
                if mapping:
                    additive.append(f"{location}: added definition or field")
                else:
                    breaking.append(f"{location}: added constraint")
            elif key == "required" and not mapping:
                if set(left[key]) != set(right[key]):
                    breaking.append(f"{location}: changed required fields")
            elif key == "oneOf" and path == "schema":
                # The generation profile permits only unique local references here.
                refs = lambda entries: {
                    json.dumps(entry, sort_keys=True) for entry in entries
                }
                before, after = refs(left[key]), refs(right[key])
                if before - after:
                    breaking.append(f"{location}: removed record kind")
                if after - before:
                    additive.append(f"{location}: added record kind")
            else:
                compare(
                    left[key],
                    right[key],
                    location,
                    key in {"properties", "$defs"} and not mapping,
                )

    before, after = structural(old), structural(new)
    before.pop("x-contract-version", None)
    after.pop("x-contract-version", None)
    compare(before, after, "schema")
    return sorted(breaking), sorted(additive)


def breaking_changes(old, new):
    return classify_changes(old, new)[0]


def version(schema):
    value = schema.get("x-contract-version", "")
    if not isinstance(value, str) or not re.fullmatch(
        r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", value
    ):
        raise ValueError("Contract version must be MAJOR.MINOR")
    return tuple(map(int, value.split(".")))


def check_version(old, new):
    before, after = version(old), version(new)
    breaking, additive = classify_changes(old, new)
    if after < before:
        raise ValueError("Contract version must not decrease")
    if breaking and after[0] <= before[0]:
        raise ValueError("Contract major must increase:\n" + "\n".join(breaking))
    if additive and after <= before:
        raise ValueError("Additive changes require a contract version increase")
    return breaking, additive


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--against", type=Path, required=True)
    parser.add_argument("schema", type=Path)
    args = parser.parse_args()
    old = json.loads(args.against.read_text())
    new = json.loads(args.schema.read_text())
    try:
        breaking, additive = check_version(old, new)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    classification = "breaking" if breaking else "additive" if additive else "unchanged"
    print(f"Compatibility check passed: {classification}")


if __name__ == "__main__":
    main()
