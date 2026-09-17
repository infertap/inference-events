#!/usr/bin/env python3
"""Re-analyze a kvcap capture offline. Handles map-shaped events."""
import argparse, json, collections
try:
    import msgpack
    def unpack(b): return msgpack.unpackb(b, raw=False, strict_map_key=False)
except ImportError:
    import msgspec
    def unpack(b): return msgspec.msgpack.decode(b)

def d(v, depth=0):
    if v is None: return "null"
    if isinstance(v, bool): return "bool"
    if isinstance(v, int): return f"int({v.bit_length()}b)"
    if isinstance(v, float): return "float"
    if isinstance(v, bytes): return f"bytes({len(v)})"
    if isinstance(v, str): return "str"
    if isinstance(v, (list, tuple)):
        return f"list[{len(v)}]<{d(v[0], depth+1) if v else 'empty'}>"
    if isinstance(v, dict): return f"map[{len(v)}]"
    return type(v).__name__

def hexify(v, cap=64):
    if isinstance(v, bytes):
        h = v.hex()
        return f"<bytes:{len(v)}:{h[:cap]}{'...' if len(h)>cap else ''}>"
    if isinstance(v, dict):  return {k: hexify(x, cap) for k, x in v.items()}
    if isinstance(v, list):
        return [hexify(x, cap) for x in v[:4]] + ([f"...+{len(v)-4}"] if len(v) > 4 else [])
    return v

ap = argparse.ArgumentParser()
ap.add_argument("path")
ap.add_argument("--samples", type=int, default=2)
a = ap.parse_args()

shapes = collections.defaultdict(lambda: collections.defaultdict(set))
counts = collections.Counter()
samples = collections.defaultdict(list)
n_msg = n_ev = 0

for line in open(a.path):
    rec = json.loads(line)
    if "payload_hex" not in rec: continue
    n_msg += 1
    batch = unpack(bytes.fromhex(rec["payload_hex"]))
    events = batch[1] if isinstance(batch, (list, tuple)) and len(batch) > 1 else []
    for ev in events:
        n_ev += 1
        if isinstance(ev, dict):
            key = "map{" + ",".join(sorted(map(str, ev.keys()))) + "}"
            for k, v in ev.items(): shapes[key][str(k)].add(d(v))
        elif isinstance(ev, (list, tuple)):
            key = f"array<{ev[0] if ev and isinstance(ev[0], str) else '?'}>"
            for i, v in enumerate(ev): shapes[key][f"[{i}]"].add(d(v))
        else:
            key = d(ev)
        counts[key] += 1
        if len(samples[key]) < a.samples: samples[key].append(hexify(ev))

print(f"messages decoded: {n_msg}   events: {n_ev}\n")
for key, n in counts.most_common():
    print("=" * 70); print(f"{key}\n  count: {n}")
    for f, ds in sorted(shapes[key].items()):
        print(f"    {f:<24} {sorted(ds)}")
    for s in samples[key]:
        print(f"    SAMPLE: {json.dumps(s, default=str)[:600]}")
    print()
