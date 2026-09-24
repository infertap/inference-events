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

    def test_container_and_root_constraints(self):
        for target, key, value in [
            ("root", "not", {}),
            ("store", "type", "array"),
            ("store", "additionalProperties", False),
            ("store", "allOf", [{"not": {}}]),
        ]:
            with self.subTest(target=target, key=key):
                new = copy.deepcopy(self.old)
                node = new if target == "root" else new["$defs"][target]
                node[key] = value
                self.assertTrue(module.breaking_changes(self.old, new))

    def test_version_policy(self):
        self.new["$defs"]["store"]["properties"]["future"] = {"type": "string"}
        with self.assertRaisesRegex(ValueError, "version increase"):
            module.check_version(self.old, self.new)
        major, minor = module.version(self.old)
        self.new["x-contract-version"] = f"{major}.{minor + 1}"
        module.check_version(self.old, self.new)
        self.new["$defs"]["store"]["type"] = "array"
        with self.assertRaisesRegex(ValueError, "major"):
            module.check_version(self.old, self.new)
        self.new["x-contract-version"] = f"{major + 1}.0"
        module.check_version(self.old, self.new)

    def test_version_regression(self):
        self.new["x-contract-version"] = "1.0"
        with self.assertRaisesRegex(ValueError, "decrease"):
            module.check_version(self.old, self.new)

    def test_documentation_does_not_change_contract_shape(self):
        self.new["$defs"]["store"]["description"] = "Updated reference text."
        self.assertEqual(module.classify_changes(self.old, self.new), ([], []))

    def test_unknown_constraint_is_not_ignored(self):
        self.new["$defs"]["store"]["unevaluatedProperties"] = False
        self.assertTrue(module.breaking_changes(self.old, self.new))

    def test_fields_named_like_annotations_are_not_ignored(self):
        self.new["$defs"]["store"]["properties"]["description"] = {"type": "string"}
        breaking, additive = module.classify_changes(self.old, self.new)
        self.assertFalse(breaking)
        self.assertTrue(additive)

    def test_physical_column_change_is_breaking(self):
        self.new["$defs"]["store"]["properties"]["n_tokens"][
            "x-column-type"
        ] = "float64"
        self.assertTrue(module.breaking_changes(self.old, self.new))


if __name__ == "__main__":
    unittest.main()
