# Agent3 structured-output reliability protocol

Agent3-V5.2.1 uses deterministic greedy decoding (`do_sample=false`, one beam)
plus token-level JSON Schema constrained generation. The schema fixes all root
and nested fields, enums, request identity constants, and the allowed evidence
ID set. Post-generation validation remains a second independent gate.

Format repair and semantic second-check are different stages and are reported
separately. Deterministic repair may close a truncated JSON suffix, restore a
fixed empty `second_check` object, and correct a known field-name typo. It must
not invent a support status, evidence ID, or reason. Semantic uncertainty and
evidence conflict are handled only by the second-check policy.

`model_output_invalid` is counted once per unique `(scene_uid, claim_id)` in the
final verified package. Raw attempts, retry events, and audit rows are not
independent invalid claims. Papers must report structural validity separately
from support-status accuracy, macro-F1, and evidence-ID metrics; constrained
decoding can guarantee schema structure, not semantic correctness.
