#!/usr/bin/env python3
"""Check fixture fields against the generated column catalog.

Each fixture family declares its record containers. Unknown families fail validation.
Optional fields may be absent. Provenance fields are resolved within each segment.
"""

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CORPUS = ROOT / "conformance"
SCHEMA = json.loads((CORPUS / "schema" / "records.json").read_text())


def segments_of(rel, doc):
    """Every fixture's records, grouped by the segment that declares for them.

    Grouping matters: provenance is unspecified operator vocabulary (2.2) declared on a header, so
    what counts as a legal unnamed key depends on which header a record sits behind. A flat list
    of records cannot answer that.
    """
    family = rel.parts[1]
    if family == "telemetry":
        # Transduction fixtures: records without a segment, so nothing declares provenance for
        # them and the fixture states its own.
        return [(None, list(doc["expect"]["records"]))]
    if family == "reader":
        return [(seg[0] if seg else None, seg) for seg in doc["segments"]]
    if family in ("lifecycle", "delivery"):
        out = [
            (
                None,
                [
                    c["expect"]
                    for c in doc.get("cases", [])
                    if isinstance(c.get("expect"), dict)
                ],
            )
        ]
        for key in ("segment", "recovering_segment"):
            lines = list(doc.get(key, {}).get("lines", []))
            if lines:
                out.append((lines[0], lines))
        return out
    if family in ("vllm-wire", "pseudonym", "structure", "content"):
        return []  # wire input and key vectors: not record streams
    raise SystemExit(
        f"{rel}: fixture family {family!r} has no known shape; teach this check"
    )


def named_fields(kind):
    k = SCHEMA["kinds"].get(kind)
    return set(k["fields"]) if k else None


def main():
    bad, checked = [], 0
    for path in sorted(CORPUS.rglob("*.json")):
        rel = path.relative_to(ROOT)
        if rel.parts[1] in ("schema", "structure"):
            continue
        doc = json.loads(path.read_text())
        declared = set(doc.get("provenance", {}))

        for header, recs in segments_of(rel, doc):
            # **Any unnamed key on a header IS provenance** (2.2): the vocabulary is the
            # operator's and this contract does not specify it. What that buys the check is the
            # set of keys the records behind that header may legally carry -- under 1.1, where a
            # producer stamped provenance on every record. From 1.2 a producer MUST NOT.
            version, prov = "1.1", set(declared)
            if header is not None and header.get("kind") in (
                "segment_open",
                "segment_recovered",
            ):
                hfields = named_fields(header["kind"]) or set()
                prov |= {k for k in header if k.split(".")[0] not in hfields}
                version = str(header.get("contract_version", "1.1"))

            for rec in recs:
                kind = rec.get("kind")
                fields = named_fields(kind)
                if fields is None:
                    continue  # a kind this contract does not model is a reader's problem
                checked += 1
                is_header = kind in ("segment_open", "segment_recovered")
                allowed = set(fields)
                if is_header or version == "1.1":
                    allowed |= prov
                for f in rec:
                    base = f.split(".")[0]
                    if base in allowed or base in SCHEMA["endpoints_element"]:
                        continue
                    bad.append(f"{rel}: {kind} emits {f!r}")

    if bad:
        print(f"{len(set(bad))} fixture field(s) no kind names:", file=sys.stderr)
        for b in sorted(set(bad))[:40]:
            print(f"  {b}", file=sys.stderr)
        raise SystemExit(1)
    print(f"corpora agree with the schema ({checked} records checked)", file=sys.stderr)


if __name__ == "__main__":
    main()
