# Agent34 error and audit privacy contract

Every public failure uses `{"error":{"code","message","retryable"}}`.
Required mappings are `EMPTY_CLAIM_LIST` (422), `UNKNOWN_EVIDENCE_ID` (422),
`MODEL_NOT_READY` (503), `MODEL_TIMEOUT` (504), and `INTERNAL_ERROR` (500).
Exception text, model paths, prompts, and raw output are not included.

Public `check_result` and `verified_evidence_package.audit_records` contain a
fixed summary whitelist only. Raw first/retry/second-check output is removed
recursively before serialization. When present, it is appended only to
`<AGENT34_WORK_ROOT>/private_model_audit/agent3_raw_outputs.jsonl` and must not
be published as an artifact, sent to Agent4, or committed to Git.
