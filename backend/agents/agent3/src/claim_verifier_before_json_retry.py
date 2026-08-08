from .config import (
    Agent3Config,
)

from .model_runner import (
    QwenVLAgent3Runner,
)

from .postprocess_minimal_check import (
    postprocess_minimal_check,
)

from .second_check_policy import (
    decide_second_check,
)

from .wrap_check_result import (
    wrap_check_result,
)


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

    def verify(
        self,
        request,
    ):
        raw_first = (
            self.runner.generate(
                request
            )
        )

        first_parsed = (
            postprocess_minimal_check(
                raw_first
            )
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

        second_pass = request.get(
            "second_pass"
        )

        if (
            policy["required"]
            and second_pass
        ):
            raw_crop = (
                self.runner.generate(
                    second_pass
                )
            )

            crop_check = (
                postprocess_minimal_check(
                    raw_crop
                )[
                    "verification"
                ]
            )

        wrapped = wrap_check_result(
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
        }

        return wrapped
