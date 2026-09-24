#!/usr/bin/env python3
"""Generate the Parquet encoding of the delivery corpus's sealed segment.

Use the generated column catalog and preserve record order. Unknown fields use the
extra map; strings remain literal and other values use JSON text. PyArrow provides
an independent encoder. Its pinned version makes regeneration reproducible.
"""

import json
import pathlib

import pyarrow as pa
import pyarrow.parquet as pq

ROOT = pathlib.Path(__file__).resolve().parent.parent
DELIVERY = ROOT / "conformance" / "delivery"
SCHEMA = ROOT / "conformance" / "schema" / "records.json"

ARROW_TYPES = {
    "utf8": pa.string(),
    "int64": pa.int64(),
    "float64": pa.float64(),
    "bool": pa.bool_(),
    "list<utf8>": pa.list_(pa.string()),
}


def build_schema(spec):
    """The union of every kind's typed fields, column-per-field, plus `extra`.

    Sorted by name for determinism, except `kind` and `at_ms` first: every record carries them
    (spec 2.2), and a human reading the file should meet them before the union's long tail.
    """
    endpoints_struct = pa.struct(
        sorted(
            (
                (name, ARROW_TYPES[f["type"]])
                for name, f in spec["endpoints_element"].items()
            ),
            key=lambda nf: nf[0],
        )
    )
    fields = {}
    for kind in spec["kinds"].values():
        for name, f in kind["fields"].items():
            if f["type"] == "list<struct>":
                t = pa.list_(endpoints_struct)
            else:
                t = ARROW_TYPES[f["type"]]
            prior = fields.get(name)
            if prior is not None and prior != t:
                raise SystemExit(
                    f"field {name!r} is two types across kinds: {prior} vs {t}"
                )
            fields[name] = t
    head = ["kind", "at_ms"]
    ordered = head + sorted(k for k in fields if k not in head)
    return pa.schema(
        [pa.field(n, fields[n]) for n in ordered]
        + [pa.field("extra", pa.map_(pa.string(), pa.string()))]
    )


def rows(records, schema):
    """One row per record: typed fields to their columns, everything else to `extra`."""
    typed = {f.name for f in schema} - {"extra"}
    out = []
    for r in records:
        row = {}
        extra = []
        for key, value in r.items():
            if key in typed:
                row[key] = value
            else:
                rendered = value if isinstance(value, str) else json.dumps(value)
                extra.append((key, rendered))
        row["extra"] = extra
        out.append(row)
    return out


def main():
    spec = json.loads(SCHEMA.read_text())
    corpus = json.loads((DELIVERY / "records.json").read_text())
    segment = corpus["segment"]
    schema = build_schema(spec)
    table = pa.Table.from_pylist(rows(segment["lines"], schema), schema=schema)
    out = DELIVERY / segment["parquet_twin"]
    pq.write_table(table, out, compression="snappy")
    back = pq.read_table(out).to_pylist()
    assert len(back) == len(segment["lines"]), "twin row count diverged from the lines"
    assert back[0]["kind"] == "segment_open", "row zero is not the header"
    assert out.read_bytes()[:4] == b"PAR1", "not a Parquet file"
    print(f"wrote {out} ({out.stat().st_size} bytes, {len(back)} rows)")


if __name__ == "__main__":
    main()
