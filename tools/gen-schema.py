#!/usr/bin/env python3
"""Derive the record schema from the specification's own field tables.

The schema is what a producer writes columnar records against and what a reader builds its
decode from. It exists here, once, because written twice it drifts -- and it drifts on the
fields that decide whether a taint fires, which is the failure a single decoder exists to
prevent.

Governance rule 4: this reads the specification text. It never reads an implementation, and an
implementation that disagrees with what this emits is the implementation that is wrong.

The parser is deliberately strict. Every record kind in 2.3 to 2.5 must yield a table, every
table row must parse, and the row count consumed must equal the row count present -- a table
the parser silently skipped is the failure mode this whole artifact exists to remove, and the
`endpoints` element was prose rather than a table until 2026-08-12 for exactly that reason.
"""

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SPEC = ROOT / "spec" / "kv-cache-v1.md"
OUT = ROOT / "conformance" / "schema" / "records.json"

# The specification's type vocabulary (2.2), mapped to what a columnar writer needs. A type
# outside this set is an error rather than a default: guessing would put a wrong physical type
# on a field nobody noticed was new.
TYPES = {
    "string": "utf8",
    "integer": "int64",
    "number": "float64",
    "boolean": "bool",
    "array of string": "list<utf8>",
    "array": "list<struct>",
}

PRESENCE = {"required", "optional", "conditional"}

ROW = re.compile(r"^\|\s*`([a-z_]+)`\s*\|\s*(.+?)\s*\|\s*(\w+)\s*\|(.*)\|\s*$")
KIND_HEAD = re.compile(r"^#### `([a-z_]+)`\s*$")
SECTION = re.compile(r"^### (2\.\d) ")


def parse_type(raw, field, kind):
    """The declared type, or the literal a `kind` field pins."""
    lit = re.fullmatch(r'`"([a-z_]+)"`', raw)
    if lit:
        if field != "kind":
            raise SystemExit(f"{kind}.{field}: a literal type outside `kind`")
        return "utf8", lit.group(1)
    if raw not in TYPES:
        raise SystemExit(f"{kind}.{field}: type {raw!r} is outside the specification's vocabulary")
    return TYPES[raw], None


def main():
    lines = SPEC.read_text().split("\n")
    kinds, section, kind, endpoints = {}, None, None, None
    consumed = 0

    for i, line in enumerate(lines):
        m = SECTION.match(line)
        if m:
            section, kind = m.group(1), None
            continue
        m = KIND_HEAD.match(line)
        if m:
            # **A heading always clears the current kind, in or out of range.** Setting it only
            # inside the range left the PREVIOUS kind in scope, so a section the parser stopped
            # recognising did not skip its rows -- it filed them under the last kind it had seen.
            # The count guard below passes on that, because no row is lost. Misattribution is the
            # worse failure and the quieter one.
            kind = m.group(1) if section in ("2.3", "2.4", "2.5") else None
            if kind is not None:
                kinds[kind] = {"section": section, "fields": {}}
            continue
        # The nested element's table follows its own sentence rather than a #### heading.
        if line.startswith("Each `endpoints` element carries"):
            endpoints, kind = {}, None
            continue

        m = ROW.match(line)
        if not m:
            continue
        field, raw, presence, _ = m.groups()
        if presence not in PRESENCE:
            raise SystemExit(f"{field}: presence {presence!r} is not one of {sorted(PRESENCE)}")

        if endpoints is not None and kind is None:
            ty, _ = parse_type(raw, field, "endpoints")
            endpoints[field] = {"type": ty, "presence": presence}
            consumed += 1
        elif kind is not None:
            ty, const = parse_type(raw, field, kind)
            entry = {"type": ty, "presence": presence}
            if const is not None:
                entry["const"] = const
            kinds[kind]["fields"][field] = entry
            consumed += 1

    if not kinds:
        raise SystemExit("no record kinds found: the parser and the specification have diverged")

    # Every `#### `kind`` heading inside 2.3 to 2.5 must have produced an entry. The row count
    # alone cannot see a heading the parser walked past, because the rows behind it still land
    # somewhere.
    heads, sec = 0, None
    for line in lines:
        m = SECTION.match(line)
        if m:
            sec = m.group(1)
        elif line.startswith("## "):
            sec = None
        if sec in ("2.3", "2.4", "2.5") and KIND_HEAD.match(line):
            heads += 1
    if len(kinds) != heads:
        raise SystemExit(
            f"parsed {len(kinds)} record kinds but sections 2.3-2.5 declare {heads}: "
            "a heading was skipped, and its fields are filed under whichever kind came before it"
        )
    if endpoints is None:
        raise SystemExit("the `endpoints` element table was not found")

    # **Every field row in those sections must have been consumed, counted INDEPENDENTLY.**
    #
    # The first version of this guard counted rows with `ROW` -- the parser's own regex -- so a row
    # the parser could not read was not counted as present either, and the check compared the
    # parser against itself. It passed while `evict` carried one field, because that table used a
    # comma-separated shorthand `ROW` did not match and the counter did not see. A self-consistent
    # parser is trivially self-consistent.
    #
    # The counter here is a different measure: a table line inside 2.3 to 2.5 that is not the
    # header or the separator is a field row, whatever its shape. A row this cannot parse is now
    # a hard error rather than an absence.
    present = 0
    section = None
    for line in lines:
        m = SECTION.match(line)
        if m:
            section = m.group(1)
        elif line.startswith("## "):
            section = None
        if section not in ("2.3", "2.4", "2.5"):
            continue
        t = line.strip()
        if not t.startswith("|") or t.startswith("| field ") or set(t) <= set("|- "):
            continue
        present += 1
    if consumed != present:
        raise SystemExit(
            f"parsed {consumed} field rows but sections 2.3-2.5 contain {present}: a row shape "
            "this parser cannot read is a field the schema silently lacks. State every field on "
            "its own row with its own type -- a shorthand is a second grammar."
        )

    doc = {
        "schema_version": "v0",
        "note": (
            "Derived from the specification's field tables by tools/gen-schema.py. The producer "
            "writes records against this and a reader decodes from it; it exists once because "
            "written twice it drifts."
        ),
        "types": TYPES,
        "endpoints_element": dict(sorted(endpoints.items())),
        "kinds": {k: kinds[k] for k in sorted(kinds)},
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1, sort_keys=False) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(kinds)} kinds, {consumed} fields", file=sys.stderr)


if __name__ == "__main__":
    main()
