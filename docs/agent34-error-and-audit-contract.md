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

The controller applies the same recursive filter before writing
`logs/agent3_remote_response.json`. Controller job logs therefore contain only
the public, sanitized response and never become a second store for model raw
text.

Second-check crop metadata is treated as untrusted at both HTTP boundaries.
The controller accepts only the frozen PNG filename allowlist, validates
`job_id`, `sample_id`, and `claim_id`, requires the remote download URL to match
those identifiers exactly, and verifies that the local destination remains
inside the current job's `agent3/second_check` directory.
