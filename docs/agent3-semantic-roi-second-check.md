# Agent3 Semantic ROI Second Check

## Purpose

Agent3 now supports localized second checks beyond building instances. The
change is runtime-only: it does not alter model weights or frozen test data.

## ROI Policy

| Evidence type | ROI source | Context margin |
| --- | --- | --- |
| Building (`B*`) | Agent1 instance bbox | 15% of bbox width and height |
| Road (`R*`) | Largest connected red-dominant affected-road component in `road_status_map` | 8% |
| Surface (`S*`) | Non-background component of `surface_change_mask` | 12% |

If aligned artifacts are missing, invalid, or have incompatible dimensions,
Agent3 records `full_image_fallback` rather than failing the request.

## Boundary Claims

`partially_supported` and `exaggerated` always trigger a localized second
check. The second pass receives only the evidence IDs selected by the first
pass, so it cannot switch a road or building conclusion to unrelated evidence.

## Required Inputs

`second_pass_context.assets` may provide `pre_image`, `post_image`,
`building_instance_mask`, `damage_map`, `road_status_map`, `surface_change_mask`,
and `fused_overlay`. All inputs cropped together must be pixel-aligned.

## Validation

Unit coverage includes boundary triggering, road connected-component ROI,
surface ROI, and existing JSON-contract resilience checks. A real external
Agent1/2 integration run used a road claim on
`EARTHQUAKE-TURKEY_003679`: Agent3 automatically built a road ROI, kept
`R0001` consistent through the second pass, and conservatively returned
`partially_supported` for a claim of complete road destruction.

No raw imagery, model weights, handoff package, or frozen predictions are
committed with this change.
