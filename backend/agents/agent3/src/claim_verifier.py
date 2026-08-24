import copy
import json

from .config import (
    Agent3Config,
)

from .model_runner import (
    QwenVLAgent3Runner,
)

from .postprocess_minimal_check import (
    postprocess_minimal_check,
)

from .schemas import (
    Agent3ContractError,
)

from .output_schema import verification_json_schema

from .second_check_policy import (
    decide_second_check,
)

from .second_pass_request_builder import (
    SecondPassUnavailable,
    build_second_pass_from_context,
)

from .wrap_check_result import (
    wrap_check_result,
)


FORMAT_RETRY_SUFFIX = """
IMPORTANT OUTPUT FORMAT RETRY:

Your previous response did not satisfy the required output contract.

Perform the SAME evidence-verification task again using ONLY the
same supplied evidence.

Do not add any new factual assumptions.

Return exactly ONE JSON object and nothing else.

Do not use Markdown code fences.
Do not write text before or after the JSON object.

The JSON object must contain:
schema_version
scene_uid
claim_id
claim_type
support_status
evidence_ids
reason
suggested_revision
second_check
human_review_state
""".strip()


FROZEN_OUTPUT_CONTRACT = """
FROZEN OUTPUT CONTRACT (Agent3-V5.2.1):

Return exactly one compact JSON object with ONLY these root fields:
schema_version, scene_uid, claim_id, claim_type, support_status,
evidence_ids, reason, suggested_revision, second_check,
human_review_state.

The second_check object may contain ONLY:
required, trigger_reasons, recommended_inputs, recommended_next_step.

Never reproduce the input object or any evidence object. In particular,
never output structured_evidence, supporting_statistics, supported_reasons,
required_agent, required_evidence, expected_findings, or other legacy fields.
Use only evidence IDs supplied in allowed_evidence_ids.

Exact shape:
{"schema_version":"3.1","scene_uid":"<scene_uid>","claim_id":"<claim_id>","claim_type":"<claim_type>","support_status":"<one allowed status>","evidence_ids":[],"reason":"<short reason>","suggested_revision":"","second_check":{"required":false,"trigger_reasons":[],"recommended_inputs":[],"recommended_next_step":""},"human_review_state":"unreviewed"}
""".strip()


def _extract_identity(
    request,
):
    inp = request.get(
        "input",
        {}
    )

    if isinstance(
        inp,
        str
    ):
        try:
            inp = json.loads(
                inp
            )
        except Exception:
            inp = {}

    if not isinstance(
        inp,
        dict
    ):
        inp = {}

    return (
        inp.get(
            "scene_uid"
        ),
        inp.get(
            "claim_id"
        ),
    )


def _build_format_retry(
    request,
):
    retry = copy.deepcopy(
        request
    )

    original = str(
        retry.get(
            "instruction",
            ""
        )
    )

    retry[
        "instruction"
    ] = (
        original
        + "\n\n"
        + FORMAT_RETRY_SUFFIX
    ).strip()

    return retry


def _build_contract_request(request):
    """Attach the frozen response contract without changing HTTP payloads."""
    constrained = copy.deepcopy(request)
    inp = _request_input(constrained)
    evidence = inp.get("structured_evidence", [])
    allowed_ids = [
        str(item.get("evidence_id"))
        for item in evidence
        if isinstance(item, dict) and item.get("evidence_id") is not None
    ]
    identity = {
        "scene_uid": inp.get("scene_uid"),
        "claim_id": inp.get("claim_id"),
        "claim_type": inp.get("claim_type"),
    }
    original = str(constrained.get("instruction", "")).strip()
    constrained["instruction"] = (
        original
        + "\n\n"
        + FROZEN_OUTPUT_CONTRACT
        + "\n\nREQUEST IDENTITY (copy these values exactly):\n"
        + json.dumps(identity, ensure_ascii=False, separators=(",", ":"))
        + "\nYou may cite only these evidence IDs: "
        + json.dumps(allowed_ids, ensure_ascii=False, separators=(",", ":"))
    ).strip()
    constrained["output_contract_version"] = "agent3-frozen-json-v3.1"
    if constrained.get("enable_structured_decoding") is True:
        constrained["response_json_schema"] = verification_json_schema(
            scene_uid=identity["scene_uid"],
            claim_id=identity["claim_id"],
            claim_type=identity["claim_type"],
            evidence_ids=allowed_ids,
        )
    return constrained


def _request_input(request):
    value = request.get("input", {})
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _source_evidence_ids(request):
    evidence = _request_input(request).get("structured_evidence", [])
    return sorted({
        str(item["evidence_id"])
        for item in evidence
        if isinstance(item, dict) and item.get("evidence_id") is not None
    })


def _constrain_evidence(check, allowed_ids):
    """Prevent model output from inventing evidence or supporting no evidence."""
    result = copy.deepcopy(check)
    result["evidence_ids"] = [
        str(item) for item in result.get("evidence_ids", [])
        if str(item) in allowed_ids
    ]
    if result.get("support_status") == "supported" and not result["evidence_ids"]:
        result["support_status"] = "unsupported"
        suffix = "No valid input evidence ID supports this claim."
        reason = str(result.get("reason", "")).strip()
        result["reason"] = f"{reason} {suffix}".strip()
    return result


def _scope_second_pass_evidence(request, allowed_ids):
    """Limit the model-visible second-pass ledger to the first-pass evidence."""
    scoped = copy.deepcopy(request)
    inp = _request_input(scoped)
    evidence = inp.get("structured_evidence")
    if isinstance(evidence, list):
        inp["structured_evidence"] = [
            item for item in evidence
            if isinstance(item, dict)
            and str(item.get("evidence_id")) in allowed_ids
        ]
    scoped["input"] = inp
    return scoped


def _invalid_output_fallback(
    request,
    *,
    raw_first,
    raw_retry=None,
    reason,
    model_version,
    first_check=None,
):
    scene_uid, claim_id = (
        _extract_identity(
            request
        )
    )

    return {
        "runtime_schema_version":
            "3.1-runtime",

        "scene_uid":
            (
                first_check.get(
                    "scene_uid"
                )
                if first_check
                else scene_uid
            ),

        "claim_id":
            (
                first_check.get(
                    "claim_id"
                )
                if first_check
                else claim_id
            ),

        "first_check":
            first_check,

        "crop_check":
            None,

        "final_check":
            None,

        "resolution_state":
            "model_output_invalid",

        "human_review_required":
            True,

        "audit": {
            "trigger_reasons": [
                reason
            ],

            "recommended_inputs":
                [],

            "recommended_next_step":
                "repair_model_output_contract",

            "failure_category":
                "format_contract",

            "human_review_reasons": [
                "model_output_invalid"
            ],

            "source_evidence_ids":
                _source_evidence_ids(request),

            "first_evidence_ids":
                sorted(first_check.get("evidence_ids", [])) if first_check else [],

            "second_evidence_ids": [],

            "final_evidence_ids": [],

            "crop_region":
                request.get(
                    "crop_region"
                ),

            "model_version":
                model_version,

            "raw_first_output":
                raw_first,

            "raw_retry_output":
                raw_retry,
        },

        "generation_quality": {
            "retry_used":
                raw_retry is not None,

            "parse_failure":
                True,
        },
    }


class Agent3Verifier:

    def __init__(
        self,
        config=None,
        runner=None,
    ):
        self.config = (
            config
            or Agent3Config.from_env()
        )

        self.runner = (
            runner
            or QwenVLAgent3Runner(
                self.config
            )
        )

    def _generate_first_check(
        self,
        request,
    ):
        contract_request = _build_contract_request(request)

        raw_first = (
            self.runner.generate(
                contract_request
            )
        )

        try:
            parsed = (
                postprocess_minimal_check(
                    raw_first
                )
            )

            return (
                parsed,
                raw_first,
                None,
            )

        except Agent3ContractError:
            pass

        # One format-only retry.
        retry_request = (
            _build_format_retry(
                contract_request
            )
        )

        raw_retry = (
            self.runner.generate(
                retry_request
            )
        )

        try:
            parsed = (
                postprocess_minimal_check(
                    raw_retry
                )
            )

            return (
                parsed,
                raw_first,
                raw_retry,
            )

        except Agent3ContractError:
            return (
                None,
                raw_first,
                raw_retry,
            )

    def verify(
        self,
        request,
    ):
        (
            first_parsed,
            raw_first,
            raw_retry,
        ) = self._generate_first_check(
            request
        )

        # -----------------------------------------
        # Never crash the whole multi-agent chain
        # because of malformed model output.
        # -----------------------------------------
        if first_parsed is None:
            return _invalid_output_fallback(
                request,
                raw_first=raw_first,
                raw_retry=raw_retry,
                reason=(
                    "first_check_unrecoverable_json"
                ),
                model_version=(
                    self.config.model_version
                ),
            )

        request_input = _request_input(request)
        evidence_context = request_input.get("structured_evidence", [])
        allowed_ids = {
            str(item.get("evidence_id"))
            for item in evidence_context
            if isinstance(item, dict) and item.get("evidence_id") is not None
        }

        first = _constrain_evidence(first_parsed[
            "verification"
        ], allowed_ids)

        policy = (
            decide_second_check(
                first,
                evidence_context=evidence_context,
            )
        )

        crop_check = None
        crop_raw = None
        crop_retry_raw = None

        second_pass = request.get(
            "second_pass"
        )

        auto_second_pass = False

        if (
            policy["required"]
            and not second_pass
            and request.get("second_pass_context")
        ):
            try:
                second_pass = (
                    build_second_pass_from_context(
                        request,
                        first,
                        policy,
                    )
                )
                auto_second_pass = True
            except SecondPassUnavailable:
                second_pass = None

        if (
            policy["required"]
            and second_pass
        ):
            # A localized re-check refines the first evidence selection; it
            # must not switch to an unrelated ledger item merely because all
            # source IDs remain present in the request payload.
            crop_allowed_ids = set(first.get("evidence_ids", [])) or allowed_ids
            contract_second_pass = _build_contract_request(
                _scope_second_pass_evidence(second_pass, crop_allowed_ids)
            )
            crop_raw = (
                self.runner.generate(
                    contract_second_pass
                )
            )

            try:
                crop_check = (
                    postprocess_minimal_check(
                        crop_raw
                    )[
                        "verification"
                    ]
                )
                crop_check = _constrain_evidence(crop_check, crop_allowed_ids)

            except Agent3ContractError:
                crop_retry_raw = self.runner.generate(
                    _build_format_retry(contract_second_pass)
                )
                try:
                    crop_check = postprocess_minimal_check(
                        crop_retry_raw
                    )["verification"]
                    crop_check = _constrain_evidence(crop_check, crop_allowed_ids)
                except Agent3ContractError:
                    return _invalid_output_fallback(
                        request,
                        raw_first=crop_raw,
                        raw_retry=crop_retry_raw,
                        reason="crop_check_unrecoverable_json",
                        model_version=self.config.model_version,
                        first_check=first,
                    )

        actual_crop_region = request.get("crop_region")
        localization_audit = None
        if second_pass:
            second_input = _request_input(second_pass)
            localization = second_input.get("localization", {})
            if isinstance(localization, dict):
                localization_audit = localization
            if isinstance(localization, dict) and localization.get("crop_bbox"):
                actual_crop_region = localization["crop_bbox"]

        wrapped = (
            wrap_check_result(
                first,
                policy,
                crop_check,
                model_version=(
                    self.config
                    .model_version
                ),
                crop_region=actual_crop_region,
            )
        )

        wrapped["audit"]["second_pass_auto_built"] = auto_second_pass
        wrapped["audit"]["source_evidence_ids"] = sorted(allowed_ids)
        wrapped["audit"]["first_evidence_ids"] = sorted(first.get("evidence_ids", []))
        wrapped["audit"]["second_evidence_ids"] = (
            sorted(crop_check.get("evidence_ids", [])) if crop_check else []
        )
        final_check = wrapped.get("final_check")
        wrapped["audit"]["final_evidence_ids"] = (
            sorted(final_check.get("evidence_ids", [])) if final_check else []
        )
        if localization_audit is not None:
            wrapped["audit"]["localization_mode"] = localization_audit.get("mode")
            if localization_audit.get("fallback_reason"):
                wrapped["audit"]["fallback_reason"] = localization_audit["fallback_reason"]
        wrapped["audit"]["format_repair_attempted"] = bool(
            raw_retry is not None or crop_retry_raw is not None
        )

        wrapped[
            "generation_quality"
        ] = {
            "first_check_strict_json":
                first_parsed[
                    "strict_json"
                ],

            "first_check_schema_exact":
                first_parsed[
                    "schema_exact"
                ],

            "retry_used":
                raw_retry is not None or crop_retry_raw is not None,

            "crop_retry_used":
                crop_retry_raw is not None,

            "parse_failure":
                False,

            "format_repair_attempted":
                raw_retry is not None or crop_retry_raw is not None,

            "structured_decoding_requested":
                request.get("enable_structured_decoding") is True,
        }

        # Preserve the first malformed response
        # when the retry succeeded.
        if raw_retry is not None:
            wrapped[
                "audit"
            ][
                "format_retry"
            ] = {
                "used":
                    True,

                "raw_first_output":
                    raw_first,
            }

        return wrapped
