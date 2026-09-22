#!/usr/bin/env python3
"""Compatibility classifications from independent schema mutations."""
import copy, importlib.util, json, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location(
    "compatibility", ROOT / "tools/check-compatibility.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Compatibility(unittest.TestCase):
    def setUp(self):
        self.old = json.loads((ROOT / "schema/records.schema.json").read_text())
        self.new = copy.deepcopy(self.old)

    def test_optional_addition(self):
        self.new["$defs"]["store"]["properties"]["future"] = {"type": "string"}
        self.assertEqual(module.breaking_changes(self.old, self.new), [])

    def test_required_addition(self):
        self.new["$defs"]["store"]["required"].append("future")
        self.assertTrue(module.breaking_changes(self.old, self.new))

    def test_identity_change(self):
        self.new["x-content-construction"] = "different"
        self.assertTrue(module.breaking_changes(self.old, self.new))

    def test_removal(self):
        del self.new["$defs"]["store"]["properties"]["block_id"]
        self.assertTrue(module.breaking_changes(self.old, self.new))

    def test_record_kind_removal(self):
        self.new["oneOf"].pop()
        self.assertTrue(module.breaking_changes(self.old, self.new))

    def test_constraint_change(self):
        self.new["$defs"]["store"]["properties"]["n_tokens"]["maximum"] = 10
        self.assertTrue(module.breaking_changes(self.old, self.new))


if __name__ == "__main__":
    unittest.main()
