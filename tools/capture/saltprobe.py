#!/usr/bin/env python3
import json, urllib.request, urllib.error

BASE = "http://127.0.0.1:8000"
MODEL = "Qwen/Qwen2.5-0.5B-Instruct"
PROMPT = " ".join(["alpha bravo charlie delta"] * 120)


def send(label, extra):
    body = {"model": MODEL, "prompt": PROMPT, "max_tokens": 4, "temperature": 0.0}
    body.update(extra)
    req = urllib.request.Request(
        f"{BASE}/v1/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            print(f"{label:<22} HTTP {r.status}")
    except urllib.error.HTTPError as e:
        print(f"{label:<22} HTTP {e.code}: {e.read()[:300].decode(errors='replace')}")
    except Exception as e:
        print(f"{label:<22} {type(e).__name__}: {e}")


send("salt=tenant-AAAA", {"cache_salt": "tenant-AAAA"})
send("salt=tenant-BBBB", {"cache_salt": "tenant-BBBB"})
send("no salt", {})
