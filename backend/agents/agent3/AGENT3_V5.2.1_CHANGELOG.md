# Agent3-V5.2.1

Agent3-V5.2.1 is a runtime contract correction over V5.2. The LoRA adapter
weights are unchanged (`agent3_v52_targeted_best`; SHA256
`77027dc79afdfb0c97cc9dbce4e8a34ad52ab57ade678925659a890e878bfc76`).

## Runtime changes since V5.2

- Prompt: injects a frozen ten-field JSON contract and forbids input/evidence
  echo, legacy fields, and out-of-scope evidence IDs.
- Parser: exact root and nested key sets; conservative truncated-suffix repair;
  deterministic repair for known `support_status` typos and an omitted constant
  `second_check` block.
- Schema: freezes schema version 3.1 and the allowed support/review enums.
- Retry: at most one format-only retry per first or second check. It cannot
  change evidence or invent a semantic decision.
- Routing: unrecoverable format output becomes `model_output_invalid` with
  `human_review_required=false`.
- Second check: `partially_supported` alone no longer forces rerun. Triggers are
  explicit model request, contradicted/exaggerated status, missing evidence ID,
  or low/uncertain evidence confidence.
- Package/report: format attention and semantic human review remain separate
  through Agent3, verified package, and Agent4 `review_info`.

## Compatibility

HTTP paths, multipart fields, and response envelopes remain
`agent34-http-1.0`. Agent3/4 model checkpoints are not included in Git.
