#!/usr/bin/env python3
"""Validate the canonical schema and independent structural acceptance cases."""
import json
from pathlib import Path
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent
schema = json.loads((ROOT / "schema/records.schema.json").read_text())
Draft202012Validator.check_schema(schema)
validator = Draft202012Validator(schema)
cases = json.loads((ROOT / "conformance/structure/cases.json").read_text())
for case in cases:
    valid = validator.is_valid(case["record"])
    if valid != case["valid"]:
        raise SystemExit(f"Unexpected structural result: {case['name']}")
print(f"JSON Schema: {len(cases)} acceptance cases passed")
