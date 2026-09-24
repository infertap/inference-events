"""Validate the deliberately narrow schema profile supported by the Rust model."""

import re

ANNOTATIONS = {"$id", "title", "description"}
KEYWORDS = {
    "type",
    "properties",
    "required",
    "additionalProperties",
    "const",
    "minimum",
    "maximum",
    "items",
    "$ref",
    "allOf",
    "if",
    "then",
    "not",
}
COLUMN_TYPES = {
    "string": "utf8",
    "integer": "int64",
    "number": "float64",
    "boolean": "bool",
}
RUST_RESERVED = set(
    "as break const continue crate else enum extern false fn for if impl in let loop match mod move mut pub ref return self Self static struct super trait true type unsafe use where while async await dyn abstract become box do final macro override priv typeof unsized virtual yield try gen".split()
)
IDENTIFIER = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*$")


def require(condition, path, message):
    if not condition:
        raise ValueError(f"{path}: {message}")


def record_kinds(schema):
    return [entry["$ref"].removeprefix("#/$defs/") for entry in schema["oneOf"]]


def validate_profile(schema):
    """Reject shapes that generation or runtime validation cannot represent."""
    require(isinstance(schema, dict), "schema", "expected object")
    for key in schema:
        require(
            key in ANNOTATIONS | {"$schema", "$defs", "oneOf"} or key.startswith("x-"),
            "schema",
            f"unsupported root keyword {key}",
        )
    require(
        schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema",
        "schema",
        "expected draft 2020-12",
    )
    definitions = schema["$defs"]

    def visit(rule, path):
        require(isinstance(rule, dict), path, "boolean schemas are unsupported")
        for key in rule:
            require(
                key in KEYWORDS | ANNOTATIONS or key.startswith("x-"),
                path,
                f"unsupported keyword {key}",
            )
        require(
            rule.get("additionalProperties", True) is True,
            path,
            "extensions must remain allowed",
        )
        if "const" in rule:
            require(
                isinstance(rule["const"], (str, bool)),
                path,
                "only string and boolean constants are supported",
            )
        if "$ref" in rule:
            ref = rule["$ref"]
            require(
                ref.startswith("#/$defs/") and ref[8:] in definitions,
                path,
                "reference must name a local definition",
            )
            require(
                not (
                    set(rule)
                    - ANNOTATIONS
                    - {"$ref"}
                    - {k for k in rule if k.startswith("x-")}
                ),
                path,
                "reference siblings with constraints are unsupported",
            )
        if "minimum" in rule or "maximum" in rule:
            require(
                rule.get("type") == "integer"
                or rule.get("type") in (["integer", "null"], ["null", "integer"]),
                path,
                "bounds require an integer type",
            )
            for key in ("minimum", "maximum"):
                if key in rule:
                    require(
                        type(rule[key]) is int and -(2**63) <= rule[key] <= 2**63 - 1,
                        path,
                        "bounds must fit int64",
                    )
        require("then" not in rule or "if" in rule, path, "then requires if")
        if "properties" in rule:
            for name, child in rule["properties"].items():
                visit(child, f"{path}.{name}")
        for key in ("allOf",):
            for child in rule.get(key, []):
                visit(child, path)
        for key in ("items", "if", "then", "not"):
            if key in rule:
                visit(rule[key], path)

    kinds = record_kinds(schema)
    require(
        len(set(kinds)) == len(kinds) and bool(kinds),
        "schema",
        "record kinds must be unique and nonempty",
    )
    for entry in schema["oneOf"]:
        require(
            set(entry) == {"$ref"},
            "schema.oneOf",
            "dispatch entries must be references only",
        )
        visit(entry, "schema.oneOf")

    def references(rule):
        if isinstance(rule, dict):
            if "$ref" in rule:
                yield rule["$ref"][8:]
            for child in rule.values():
                yield from references(child)
        elif isinstance(rule, list):
            for child in rule:
                yield from references(child)

    def check_cycles(name, ancestors):
        require(name not in ancestors, name, "recursive definitions are unsupported")
        for target in references(definitions[name]):
            require(target in definitions, name, "unknown definition")
            check_cycles(target, ancestors | {name})

    for name in definitions:
        check_cycles(name, set())
    rust_names = {"Presence", "Record", "KnownRecord", "ErrorKind", "ValidationError"}
    for name, definition in definitions.items():
        require(bool(IDENTIFIER.fullmatch(name)), name, "invalid definition identifier")
        rust_name = "".join(part.capitalize() for part in name.split("_"))
        require(rust_name not in rust_names, name, "generated Rust name collision")
        rust_names.add(rust_name)
        visit(definition, name)
        require(definition.get("type") == "object", name, "definitions must be objects")
        properties = definition["properties"]
        if name not in kinds:
            require(
                "kind" not in properties,
                name,
                "nested structures cannot declare a discriminator",
            )
        required = definition.get("required", [])
        require(
            set(required) <= properties.keys(), name, "required field has no definition"
        )
        require(len(set(required)) == len(required), name, "duplicate required field")
        if name in kinds:
            require(
                properties.get("kind", {}).get("const") == name and "kind" in required,
                name,
                "record kind must match its required discriminator",
            )
            require(
                properties.get("at_ms", {}).get("type") == "number"
                and "at_ms" in required,
                name,
                "record requires numeric at_ms",
            )
        else:
            require(
                name == "Endpoint",
                name,
                "only Endpoint is supported as a nested column structure",
            )
        for field, rule in properties.items():
            path = f"{name}.{field}"
            require(
                bool(IDENTIFIER.fullmatch(field))
                and field not in RUST_RESERVED | {"extensions"},
                path,
                "invalid or reserved field identifier",
            )
            types = rule["type"] if isinstance(rule["type"], list) else [rule["type"]]
            base = [ty for ty in types if ty != "null"]
            require(
                len(base) == 1 and len(types) == len(set(types)),
                path,
                "only scalar nullable unions are supported",
            )
            physical = COLUMN_TYPES.get(base[0])
            if base[0] == "array":
                require("null" not in types, path, "nullable arrays are unsupported")
                items = rule.get("items")
                if items == {"type": "string"}:
                    physical = "list<utf8>"
                elif items == {"$ref": "#/$defs/Endpoint"} and name in kinds:
                    physical = "list<struct>"
            require(
                physical is not None and rule.get("x-column-type") == physical,
                path,
                "JSON and column types disagree",
            )
            presence = rule.get("x-presence")
            require(
                presence in {"required", "optional", "conditional"},
                path,
                "invalid presence annotation",
            )
            require(
                (presence == "required") == (field in required),
                path,
                "required and presence annotations disagree",
            )
            if base[0] == "integer":
                require(
                    rule.get("minimum", -(2**64)) >= -(2**63)
                    and rule.get("maximum", 2**64) <= 2**63 - 1,
                    path,
                    "generated integer fields require int64 bounds",
                )
