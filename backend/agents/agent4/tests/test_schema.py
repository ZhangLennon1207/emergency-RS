import json
from pathlib import Path


def test_report_schema_is_valid_json():
    root = Path(__file__).resolve().parents[1]

    path = (
        root
        / "src"
        / "platform_report_schema_v3.json"
    )

    schema = json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )

    assert isinstance(schema, dict)
