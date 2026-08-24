import unittest

from backend.agents.agent3.src.wrap_check_result import wrap_check_result


def check(status, evidence_ids=None):
    return {
        "scene_uid": "S_TEST",
        "claim_id": "C_TEST",
        "support_status": status,
        "evidence_ids": evidence_ids if evidence_ids is not None else ["R0001"],
    }


def policy(required=True, reasons=None):
    return {
        "required": required,
        "trigger_reasons": reasons or [],
        "recommended_inputs": [],
        "recommended_next_step": "run_localized_second_check" if required else "finalize_first_check",
    }


class HumanReviewPolicyTest(unittest.TestCase):

    def test_partial_agreement_still_requires_review(self):
        result = wrap_check_result(
            check("partially_supported"),
            policy(reasons=["boundary_status:partially_supported"]),
            check("partially_supported"),
        )
        self.assertEqual(result["resolution_state"], "second_check_agreement")
        self.assertTrue(result["human_review_required"])

    def test_exaggerated_agreement_still_requires_review(self):
        result = wrap_check_result(
            check("exaggerated"),
            policy(reasons=["boundary_status:exaggerated"]),
            check("exaggerated"),
        )
        self.assertTrue(result["human_review_required"])
        self.assertIn(
            "high_risk_status:exaggerated",
            result["audit"]["human_review_reasons"],
        )

    def test_conflicting_checks_require_review(self):
        result = wrap_check_result(
            check("supported"),
            policy(reasons=["model_requested_second_check"]),
            check("unsupported"),
        )
        self.assertEqual(result["resolution_state"], "human_review_required")
        self.assertTrue(result["human_review_required"])
        self.assertIn("second_check_conflict", result["audit"]["human_review_reasons"])

    def test_low_confidence_agreement_requires_review(self):
        result = wrap_check_result(
            check("supported"),
            policy(reasons=["low_evidence_confidence"]),
            check("supported"),
        )
        self.assertTrue(result["human_review_required"])

    def test_missing_required_second_check_requires_review(self):
        result = wrap_check_result(
            check("supported"),
            policy(reasons=["model_requested_second_check"]),
        )
        self.assertEqual(result["resolution_state"], "second_check_required")
        self.assertTrue(result["human_review_required"])

    def test_unsupported_agreement_does_not_force_review(self):
        result = wrap_check_result(
            check("unsupported"),
            policy(reasons=["boundary_status:unsupported"]),
            check("unsupported"),
        )
        self.assertFalse(result["human_review_required"])

    def test_contradicted_agreement_requires_review(self):
        result = wrap_check_result(
            check("contradicted"),
            policy(reasons=["boundary_status:contradicted"]),
            check("contradicted"),
        )
        self.assertTrue(result["human_review_required"])


if __name__ == "__main__":
    unittest.main()
