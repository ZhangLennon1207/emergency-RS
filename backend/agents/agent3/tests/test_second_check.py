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

    def test_partial_triggers(self):
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

    def test_low_confidence_triggers(self):
        result = {
            "support_status": "supported",
            "evidence_ids": ["B0001"],
            "second_check": {"required": False},
        }
        policy = decide_second_check(
            result,
            evidence_context=[{"evidence_id": "B0001", "confidence": 0.32}],
        )
        self.assertIn("low_evidence_confidence", policy["trigger_reasons"])

    def test_uncertainty_interval_triggers(self):
        result = {
            "support_status": "supported",
            "evidence_ids": ["B0001"],
            "second_check": {"required": False},
        }
        policy = decide_second_check(
            result,
            evidence_context=[{"evidence_id": "B0001", "confidence": 0.6}],
        )
        self.assertIn(
            "evidence_confidence_uncertainty_interval",
            policy["trigger_reasons"],
        )


if __name__ == "__main__":
    unittest.main()
