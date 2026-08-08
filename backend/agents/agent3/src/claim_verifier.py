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

from .second_check_policy import (
    decide_second_check,
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


def _human_review_fallback(
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
            "human_review_required",

        "human_review_required":
            True,

        "audit": {
            "trigger_reasons": [
                reason
            ],

            "recommended_inputs":
                [],

            "recommended_next_step":
                "human_review",

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
        raw_first = (
            self.runner.generate(
                request
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
                request
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
            return _human_review_fallback(
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

        first = first_parsed[
            "verification"
        ]

        policy = (
            decide_second_check(
                first
            )
        )

        crop_check = None
        crop_raw = None

        second_pass = request.get(
            "second_pass"
        )

        if (
            policy["required"]
            and second_pass
        ):
            crop_raw = (
                self.runner.generate(
                    second_pass
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

            except Agent3ContractError:
                return (
                    _human_review_fallback(
                        request,
                        raw_first=raw_first,
                        raw_retry=crop_raw,
                        reason=(
                            "crop_check_"
                            "unrecoverable_json"
                        ),
                        model_version=(
                            self.config
                            .model_version
                        ),
                        first_check=first,
                    )
                )

        wrapped = (
            wrap_check_result(
                first,
                policy,
                crop_check,
                model_version=(
                    self.config
                    .model_version
                ),
                crop_region=request.get(
                    "crop_region"
                ),
            )
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
                raw_retry is not None,

            "parse_failure":
                False,
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
