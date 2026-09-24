# Wire capture inputs

These files contain multipart engine messages from synthetic inference traffic.
`tools/gen-vllm-wire-corpus.py` uses them to generate the wire conformance fixtures.
Keep the captured bytes unchanged so the fixtures remain reproducible.

| Input | Hash algorithm | Workload |
|---|---|---|
| `capture-sha256.jsonl` | `sha256` | Repeated prefixes and cache pressure. |
| `capture-salt.jsonl` | `sha256_cbor` | Requests with different cache salts. |

The captures use vLLM 0.26.0, Python 3.10.12, msgspec 0.21.1, pyzmq 27.1.0,
and an NVIDIA A10 with driver 580.105.08. The model is Qwen/Qwen2.5-0.5B-Instruct,
with a maximum model length of 4096 and a GPU block-count override of 1024.

These versions identify fixture inputs; they are not a library support matrix.
The generator adds constructed cases for malformed messages and fields not present
in the captures. See [capture tools](../tools/capture/README.md).
