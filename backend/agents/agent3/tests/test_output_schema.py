from lmformatenforcer import JsonSchemaParser

from src.output_schema import verification_json_schema


def test_frozen_schema_is_supported_by_constraint_parser():
    schema = verification_json_schema(
        scene_uid="S1", claim_id="C1", claim_type="road_impact", evidence_ids=["R1"]
    )
    parser = JsonSchemaParser(schema)
    valid = (
        '{"schema_version":"3.1","scene_uid":"S1","claim_id":"C1",'
        '"claim_type":"road_impact","support_status":"supported",'
        '"evidence_ids":["R1"],"reason":"Visible evidence supports the claim.",'
        '"suggested_revision":"","second_check":{"required":false,'
        '"trigger_reasons":[],"recommended_inputs":[],"recommended_next_step":""},'
        '"human_review_state":"unreviewed"}'
    )
    state = parser
    for character in valid:
        state = state.add_character(character)
    assert state.can_end()
