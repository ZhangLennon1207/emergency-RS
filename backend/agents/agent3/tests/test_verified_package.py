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


if __name__ == "__main__":
    unittest.main()
