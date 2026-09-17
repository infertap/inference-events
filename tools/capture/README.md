# Capture tools

The scripts that produced `capture/` (the vLLM 0.26.0 capture the corpora are generated
from) and that a maintainer runs against a live engine to re-derive it for a newer vLLM.
They moved here from the tap repository on 2026-09-16 to sit beside the generators that
consume their output. The capture is also published as an asset on the corpus tag's
release, with a `SHA256SUMS`. They are re-run when an engine version moves; the data they
produced is evidence rather than input.

- `kvcap.py` — subscribe, write every multipart frame verbatim as hex, report the **observed**
  types of every field position. It validates nothing against an expected schema on purpose:
  the corpus it replaced was authored from schema-reading and was self-consistently wrong, so
  this reports what arrived rather than what should have.
- `kvinspect.py` — re-analyse a capture offline. Separate from `kvcap.py` because the first
  version of that analysis assumed tag-first arrays and reported `<not observed>` for every
  field; being able to re-run the analysis over saved bytes, without re-renting a GPU, is what
  made that recoverable.
- `kvload.py` — traffic shaped to produce every event kind: reused prefixes for stores, more
  prefixes than the cache holds for evictions.
- `saltprobe.py` — the same prompt under different `cache_salt` values. This is what refuted
  flagged item 1.

Runbook, including the engine flags and the ordering that matters (subscriber before load,
because ZMQ PUB drops with no subscriber attached), is in `capture/serve-cmds.txt`.
