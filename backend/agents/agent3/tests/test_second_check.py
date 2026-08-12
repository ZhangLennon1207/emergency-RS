import unittest

from src.second_check_policy import (
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

    def test_partial_alone_does_not_trigger(self):
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

        self.assertFalse(
            policy["required"]
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
