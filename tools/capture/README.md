# Capture tools

These tools collect and inspect synthetic engine traffic for the wire conformance corpus.

- `kvcap.py` records multipart ZMQ frames as hexadecimal data.
- `kvinspect.py` inspects saved captures, including map-shaped events.
- `kvload.py` sends repeated prefixes and cache-pressure traffic.
- `saltprobe.py` sends the same prompt with different cache salts.

Start the subscriber before the workload. ZMQ PUB messages sent without a subscriber
are not retained for later capture. Use synthetic prompts and record the engine version,
hash algorithm, model, and cache configuration with each contributed capture.

Run tools with `--help` where available. Generate reports locally; commit the raw inputs
needed by the corpus and concise provenance documentation, rather than diagnostic logs.
