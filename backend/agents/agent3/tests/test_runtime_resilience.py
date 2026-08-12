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

            "claim_type":
                "building_damage_presence",

            "structured_evidence": [{
                "evidence_id": "B0001",
                "evidence_type": "building_instance",
                "finding": "The building is damaged.",
            }],
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

    def test_double_failure_is_model_output_invalid(
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

        self.assertFalse(
            result[
                "human_review_required"
            ]
        )

        self.assertEqual(
            result[
                "resolution_state"
            ],
                "model_output_invalid",
        )

        self.assertIsNone(
            result[
                "final_check"
            ]
        )

        self.assertEqual(
            result["audit"]["failure_category"],
            "format_contract",
        )

    def test_contract_is_injected_without_changing_request(self):
        valid = json.dumps(VALID)
        runner = SequenceRunner([valid])
        seen = []

        def capture(request):
            seen.append(request)
            return valid

        runner.generate = capture
        verifier = Agent3Verifier(config=config(), runner=runner)
        original = dict(REQUEST)
        verifier.verify(REQUEST)

        self.assertEqual(REQUEST, original)
        self.assertEqual(
            seen[0]["output_contract_version"],
            "agent3-frozen-json-v3.1",
        )
        self.assertIn("Never reproduce the input object", seen[0]["instruction"])

    def test_crop_check_gets_contract_retry(self):
        first = dict(VALID)
        first["support_status"] = "partially_supported"
        first["second_check"] = {
            "required": True,
            "trigger_reasons": ["low_confidence"],
            "recommended_inputs": ["localized_crop"],
            "recommended_next_step": "run_second_check",
        }
        crop = dict(VALID)
        crop["support_status"] = "partially_supported"
        runner = SequenceRunner([
            json.dumps(first),
            "legacy crop output",
            json.dumps(crop),
        ])
        verifier = Agent3Verifier(config=config(), runner=runner)
        request = dict(REQUEST)
        request["second_pass"] = dict(REQUEST)
        result = verifier.verify(request)
        self.assertEqual(result["resolution_state"], "second_check_agreement")
        self.assertTrue(result["generation_quality"]["crop_retry_used"])


if __name__ == "__main__":
    unittest.main()
