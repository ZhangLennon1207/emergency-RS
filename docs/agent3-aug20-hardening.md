# Agent3 August 20 hardening

This change applies the August 20 Agent3 runtime fixes on top of the current
`main` branch and PR #14 semantic ROI support.

## Runtime behavior

- `partially_supported`, `exaggerated`, and `contradicted` results require
  human review even when first and second checks agree.
- Check conflicts, unavailable required checks, low evidence confidence,
  missing evidence IDs, and invalid model output record stable
  `human_review_reasons` values.
- Format failures enter human review. JSON-schema constrained decoding remains
  opt-in through `enable_structured_decoding=true`.
- Audit output records first/second status and reason changes, localization
  mode, fallback reason, and separate source/first/second/final evidence IDs.
- Bbox crops provide at least 64x64 pixels of context when image dimensions
  allow it.
- Road and surface semantic crops retain the concrete `Rxxxx` or `Sxxxx`
  evidence ID. Missing or invalid masks use an auditable full-image fallback.

## Validation CLI

Run the real Agent2 claim validation with explicit local paths:

```powershell
python backend/agents/agent3/scripts/run_agent3_real_agent2_claim_validation.py `
  --handoff-dir <agent1-agent2-handoff> `
  --regression-dir <agent3-integration-inputs> `
  --output-dir <validation-output> `
  --base-model <qwen-base-model> `
  --adapter <agent3-adapter>
```

Audit and package an existing run:

```powershell
python backend/agents/agent3/scripts/audit_real_agent2_claim_validation.py `
  --input-dir <validation-output>

python backend/agents/agent3/scripts/package_public_validation.py `
  --source-dir <validation-output> `
  --destination-dir <public-output> `
  --zip-path <public-zip> `
  --agent1-handoff-dir <optional-agent1-handoff>
```

No script contains a machine-specific absolute path. The public package omits
images, requests, raw model output, weights, and source paths.

## Verification

```powershell
python -m pytest backend/agents/agent3/tests backend/agents/agent3/src -q
```

The manifest and checksums in `backend/agents/agent3/MANIFEST.json` and
`backend/agents/agent3/SHA256SUMS` cover the files delivered by this change.

## Known limitation

Agent3 supports `surface_change_mask`, but a full Agent1-to-Agent3 surface ROI
run still requires an upstream handoff that actually contains that asset. A
missing mask must remain `full_image_fallback`; it is not evidence that the
surface ROI path has been validated end to end.
