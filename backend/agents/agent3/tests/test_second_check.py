import unittest

from backend.agents.agent3.src.second_check_policy import (
    decide_second_check,
)


class SecondCheckTest(
    unittest.TestCase
):

    def test_supported_finalizes(self):
        result = {
            "support_status":
                "supported",

            "evidence_ids":
                ["B0001"],

            "second_check": {
                "required":
                    False
            },
        }

        policy = (
            decide_second_check(
                result
            )
        )

        self.assertFalse(
            policy["required"]
        )

    def test_partial_alone_triggers_boundary_recheck(self):
        result = {
            "support_status":
                "partially_supported",

            "evidence_ids":
                ["B0001"],

            "second_check": {
                "required":
                    False
            },
        }

        policy = (
            decide_second_check(
                result
            )
        )

        self.assertTrue(
            policy["required"]
        )
        self.assertIn(
            "boundary_decision_requires_local_recheck",
            policy["trigger_reasons"],
        )

    def test_exaggerated_triggers_boundary_recheck(self):
        policy = decide_second_check({
            "support_status": "exaggerated",
            "evidence_ids": ["R0001"],
            "second_check": {"required": False},
        })
        self.assertTrue(policy["required"])
        self.assertEqual(
            policy["recommended_inputs"],
            ["pre_crop", "post_crop", "road_status_map_crop", "fused_overlay_crop"],
        )

    def test_partial_with_uncertain_confidence_triggers(self):
        result = {
            "support_status": "partially_supported",
            "evidence_ids": ["B0001"],
            "second_check": {"required": False},
        }
        policy = decide_second_check(result, evidence_context=[{"confidence": 0.6}])
        self.assertTrue(policy["required"])
        self.assertIn("evidence_confidence_uncertainty_interval", policy["trigger_reasons"])


if __name__ == "__main__":
    unittest.main()
