#!/usr/bin/env python3
"""Reject schema constructs that cannot be represented by generated bindings."""
import copy
import json
import unittest
from pathlib import Path
from schema_profile import validate_profile

ROOT = Path(__file__).resolve().parent.parent


class SchemaProfile(unittest.TestCase):
    def setUp(self):
        self.schema = json.loads((ROOT / "schema/records.schema.json").read_text())

    def test_current_schema(self):
        validate_profile(self.schema)

    def test_inconsistent_column_type(self):
        self.schema["$defs"]["store"]["properties"]["extra_keys"]["items"] = {
            "type": "integer"
        }
        with self.assertRaisesRegex(ValueError, "column types"):
            validate_profile(self.schema)

    def test_unsupported_assertions(self):
        for key, value in [("not", {}), ("unevaluatedProperties", False)]:
            with self.subTest(key=key):
                schema = copy.deepcopy(self.schema)
                schema[key] = value
                with self.assertRaisesRegex(ValueError, "unsupported root"):
                    validate_profile(schema)

    def test_reference_sibling_constraints(self):
        self.schema["$defs"]["heartbeat"]["properties"]["endpoints"]["items"][
            "not"
        ] = {}
        with self.assertRaisesRegex(ValueError, "reference siblings"):
            validate_profile(self.schema)

    def test_presence_must_agree_with_required(self):
        self.schema["$defs"]["store"]["properties"]["block_id"][
            "x-presence"
        ] = "optional"
        with self.assertRaisesRegex(ValueError, "presence annotations"):
            validate_profile(self.schema)

    def test_discriminator_must_match_definition(self):
        self.schema["$defs"]["store"]["properties"]["kind"]["const"] = "other"
        with self.assertRaisesRegex(ValueError, "discriminator"):
            validate_profile(self.schema)

    def test_unbounded_integer(self):
        del self.schema["$defs"]["store"]["properties"]["n_tokens"]["maximum"]
        with self.assertRaisesRegex(ValueError, "int64 bounds"):
            validate_profile(self.schema)

    def test_duplicate_dispatch(self):
        self.schema["oneOf"].append(self.schema["oneOf"][0])
        with self.assertRaisesRegex(ValueError, "unique"):
            validate_profile(self.schema)

    def test_recursive_reference(self):
        self.schema["$defs"]["Endpoint"]["allOf"] = [{"$ref": "#/$defs/Endpoint"}]
        with self.assertRaisesRegex(ValueError, "recursive"):
            validate_profile(self.schema)

    def test_reserved_rust_identifier(self):
        properties = self.schema["$defs"]["store"]["properties"]
        properties["type"] = copy.deepcopy(properties["backend_id"])
        with self.assertRaisesRegex(ValueError, "reserved field"):
            validate_profile(self.schema)

    def test_nullable_integer_profile(self):
        self.schema["$defs"]["store"]["properties"]["n_tokens"]["type"] = [
            "integer",
            "null",
        ]
        validate_profile(self.schema)


if __name__ == "__main__":
    unittest.main()
