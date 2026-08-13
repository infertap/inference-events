#!/usr/bin/env python3
"""Every field a fixture emits is a field the schema names for that kind.

Three specification changes in one day landed in one generator and not another, and each was
caught downstream by an implementation whose test compared its output against a fixture. The
contract was internally inconsistent and only a consumer noticed. This is the check that belongs
here.

It reads `conformance/schema/records.json`, derived from the specification's tables, and walks
every fixture. A field an implementation would refuse is a field this repository refuses first.

**Containers are enumerated, never sniffed.** A heuristic that calls an object a record because
it carries `kind` and `at_ms` also calls a lifecycle CASE a record, because a case carries both.
Guessing the shape is the same class of mistake as guessing a field's type, so a fixture family
this does not recognise is an error rather than a skip.

Direction is deliberate: a fixture may omit an optional field, so absence is silent. Emitting a
field no kind names is the error.
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
        out = [(None, [c["expect"] for c in doc.get("cases", []) if isinstance(c.get("expect"), dict)])]
        for key in ("segment", "orphan_segment"):
            lines = list(doc.get(key, {}).get("lines", []))
            if lines:
                out.append((lines[0], lines))
        return out
    if family in ("vllm-wire", "pseudonym"):
        return []  # wire input and key vectors: not record streams
    raise SystemExit(f"{rel}: fixture family {family!r} has no known shape; teach this check")


def named_fields(kind):
    k = SCHEMA["kinds"].get(kind)
    return set(k["fields"]) if k else None


def main():
    bad, checked = [], 0
    for path in sorted(CORPUS.rglob("*.json")):
        rel = path.relative_to(ROOT)
        if rel.parts[1] == "schema":
            continue
        doc = json.loads(path.read_text())
        declared = set(doc.get("provenance", {}))

        for header, recs in segments_of(rel, doc):
            # **Any unnamed key on a header IS provenance** (2.2): the vocabulary is the
            # operator's and this contract does not specify it. What that buys the check is the
            # set of keys the records behind that header may legally carry -- under 1.1, where a
            # producer stamped provenance on every record. From 1.2 a producer MUST NOT.
            version, prov = "1.1", set(declared)
            if header is not None and header.get("kind") in ("segment_open", "segment_recovered"):
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
