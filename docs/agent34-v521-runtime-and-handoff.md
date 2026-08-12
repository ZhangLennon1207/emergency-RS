# Agent3-V5.2.1 / Agent4-V3 runtime and handoff note

## Version definition

Agent3-V5.2.1 is a runtime-contract repair of Agent3-V5.2. It changes the
frozen JSON prompt, strict parser, schema validation, one bounded format retry,
second-check routing, evidence-ID filtering, status/reason consistency checks,
and package/report review-state propagation. It does not retrain or modify the
LoRA. The expected LoRA SHA-256 remains
`77027dc79afdfb0c97cc9dbce4e8a34ad52ab57ade678925659a890e878bfc76`.

## Second-check policy

A second check is required for `contradicted` or `exaggerated`, an explicit
model request, missing referenced evidence, confidence below 0.45, or an
uncertain confidence interval up to 0.70. `partially_supported` alone is not a
trigger. This replaces the earlier over-broad rule that forced every partial
result to be checked again; that rule was a major reason the 20-sample audit
grew from 19 requested second checks to 70 routed records.

If a required localized input cannot be built, the claim remains semantically
pending with `human_review_required=true`. Invalid JSON or schema output is
instead marked `model_output_invalid`, with `human_review_required=false`.
Agent4 exposes the latter as `attention_required`; it does not merge a format
failure into the semantic human-review count.

## Output directories

`second_check/` is the only delivery directory for retained second-check
metadata and crops. `second_pass/` is an ephemeral runtime workspace and must
not be included in release archives. A delivery package must contain at most
one copy of each crop under `second_check/<claim_id>/`.

## Security and deployment

The HTTP model service listens only on `127.0.0.1:8100` and is reached through
an SSH tunnel. Repository material must not contain model weights, datasets,
real imagery, tokens, process files, debug logs, or machine-specific absolute
paths.
