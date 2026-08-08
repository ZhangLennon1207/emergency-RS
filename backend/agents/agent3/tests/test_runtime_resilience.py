import json
import unittest

from src.claim_verifier import (
    Agent3Verifier,
)

from src.config import (
    Agent3Config,
)


VALID = {
    "schema_version":
        "3.1",

    "scene_uid":
        "S_TEST",

    "claim_id":
        "C_TEST",

    "claim_type":
        "building_damage_presence",

    "support_status":
        "supported",

    "evidence_ids":
        ["B0001"],

    "reason":
        "The supplied evidence supports the claim.",

    "suggested_revision":
        "",

    "second_check": {
        "required":
            False,

        "trigger_reasons":
            [],

        "recommended_inputs":
            [],

        "recommended_next_step":
            "",
    },

    "human_review_state":
        "unreviewed",
}


class SequenceRunner:

    def __init__(
        self,
        outputs,
    ):
        self.outputs = list(
            outputs
        )

    def generate(
        self,
        request,
    ):
        return self.outputs.pop(
            0
        )


def config():
    return Agent3Config(
        base_model_path="dummy",
        adapter_path="dummy",
        load_in_4bit=False,
        model_version="test",
    )


REQUEST = {
    "instruction":
        "Verify this claim.",

    "input":
        json.dumps({
            "scene_uid":
                "S_TEST",

            "claim_id":
                "C_TEST",
        }),

    "images":
        [],
}


class RuntimeResilienceTest(
    unittest.TestCase
):

    def test_retry_recovers_json(
        self,
    ):
        runner = SequenceRunner([
            "This is not JSON.",
            json.dumps(
                VALID
            ),
        ])

        verifier = Agent3Verifier(
            config=config(),
            runner=runner,
        )

        result = verifier.verify(
            REQUEST
        )

        self.assertEqual(
            result[
                "resolution_state"
            ],
            "finalized",
        )

        self.assertTrue(
            result[
                "generation_quality"
            ][
                "retry_used"
            ]
        )

        self.assertFalse(
            result[
                "human_review_required"
            ]
        )

    def test_double_failure_routes_to_human(
        self,
    ):
        runner = SequenceRunner([
            "not json",
            "still not json",
        ])

        verifier = Agent3Verifier(
            config=config(),
            runner=runner,
        )

        result = verifier.verify(
            REQUEST
        )

        self.assertTrue(
            result[
                "human_review_required"
            ]
        )

        self.assertEqual(
            result[
                "resolution_state"
            ],
            "human_review_required",
        )

        self.assertIsNone(
            result[
                "final_check"
            ]
        )


if __name__ == "__main__":
    unittest.main()
