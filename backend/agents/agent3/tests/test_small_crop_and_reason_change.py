import unittest

from backend.agents.agent3.src.second_check_crop_builder import padded_bbox
from backend.agents.agent3.src.wrap_check_result import wrap_check_result


class SmallCropAndReasonChangeTest(unittest.TestCase):
    def test_tiny_bbox_gets_minimum_context(self):
        self.assertEqual(padded_bbox((0, 0, 5, 5), width=512, height=512), (0, 0, 64, 64))

    def test_second_check_can_change_first_reason(self):
        first = {"scene_uid": "S", "claim_id": "C", "support_status": "supported", "evidence_ids": ["R0001"], "reason": "Initial evidence appears supportive."}
        second = {"scene_uid": "S", "claim_id": "C", "support_status": "supported", "evidence_ids": ["R0001"], "reason": "Localized crop is insufficient to confirm the extent."}
        policy = {"required": True, "trigger_reasons": ["model_requested_second_check"], "recommended_inputs": [], "recommended_next_step": "run_localized_second_check"}
        result = wrap_check_result(first, policy, second)
        self.assertEqual(result["resolution_state"], "second_check_agreement")
        self.assertTrue(result["audit"]["second_check_reason_changed"])
        self.assertFalse(result["audit"]["second_check_status_changed"])


if __name__ == "__main__":
    unittest.main()
