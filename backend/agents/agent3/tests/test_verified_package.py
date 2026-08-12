import unittest

from src.build_verified_package import (
    build_verified_package,
)


class PackageTest(
    unittest.TestCase
):

    def test_supported_claim(self):
        item = {
            "scene_uid":
                "S0001",

            "claim_id":
                "C1",

            "final_check": {
                "scene_uid":
                    "S0001",

                "claim_id":
                    "C1",

                "claim_type":
                    "road_impact",

                "support_status":
                    "supported",

                "evidence_ids":
                    ["R0001"],

                "reason":
                    "Supported.",

                "suggested_revision":
                    "",
            },
        }

        package = (
            build_verified_package(
                [item]
            )
        )

        self.assertEqual(
            package[
                "summary"
            ][
                "accepted"
            ],
            1,
        )

    def test_format_failure_is_attention_not_human_review(self):
        package = build_verified_package([{
            "scene_uid": "S0001", "claim_id": "C2",
            "resolution_state": "model_output_invalid",
            "human_review_required": False,
            "audit": {"failure_category": "format_contract"},
            "final_check": None,
        }])
        self.assertEqual(package["summary"]["model_output_invalid"], 1)
        self.assertEqual(package["summary"]["human_review_required"], 0)
        self.assertFalse(package["pending_claims"][0]["human_review_required"])


if __name__ == "__main__":
    unittest.main()
