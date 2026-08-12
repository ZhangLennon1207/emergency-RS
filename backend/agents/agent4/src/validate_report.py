import json
from pathlib import Path

from jsonschema import (
    Draft202012Validator,
)


def validate_report(
    report,
    schema_path,
):
    schema = json.loads(
        Path(
            schema_path
        ).read_text(
            encoding="utf-8"
        )
    )

    validator = (
        Draft202012Validator(
            schema
        )
    )

    errors = list(
        validator.iter_errors(
            report
        )
    )

    result = []

    for error in errors:

        path = ".".join(
            str(x)
            for x in error.absolute_path
        )

        result.append({
            "path":
                path or "<ROOT>",

            "message":
                error.message,
        })

    return result
