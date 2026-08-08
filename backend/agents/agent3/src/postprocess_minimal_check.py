import json

from .schemas import (
    TOP_LEVEL_KEYS,
    SECOND_CHECK_KEYS,
    Agent3ContractError,
    validate_verification,
)


def _strict_json(text):
    try:
        obj = json.loads(
            str(text).strip()
        )

        if isinstance(
            obj,
            dict
        ):
            return obj

    except Exception:
        pass

    return None


def _recover_json(text):
    text = str(text).strip()

    strict = _strict_json(
        text
    )

    if strict is not None:
        return strict

    if text.startswith("```"):
        newline = text.find("\n")

        if newline >= 0:
            text = text[
                newline + 1:
            ].strip()

    if text.endswith("```"):
        text = text[:-3].strip()

    try:
        obj = json.loads(
            text
        )

        if isinstance(
            obj,
            dict
        ):
            return obj

    except Exception:
        pass

    decoder = json.JSONDecoder()

    for i, ch in enumerate(
        text
    ):
        if ch != "{":
            continue

        try:
            obj, _ = (
                decoder.raw_decode(
                    text[i:]
                )
            )

        except Exception:
            continue

        if isinstance(
            obj,
            dict
        ):
            return obj

    raise Agent3ContractError(
        "No recoverable JSON object "
        "was produced by Agent3."
    )


def postprocess_minimal_check(
    raw_text,
):
    strict = (
        _strict_json(
            raw_text
        )
        is not None
    )

    result = _recover_json(
        raw_text
    )

    second = result.get(
        "second_check"
    )

    if not isinstance(
        second,
        dict
    ):
        second = {}

    second.setdefault(
        "required",
        False
    )

    second.setdefault(
        "trigger_reasons",
        []
    )

    second.setdefault(
        "recommended_inputs",
        []
    )

    second.setdefault(
        "recommended_next_step",
        ""
    )

    result[
        "second_check"
    ] = second

    result.setdefault(
        "human_review_state",
        "unreviewed"
    )

    errors = validate_verification(
        result
    )

    if errors:
        raise Agent3ContractError(
            "; ".join(
                errors
            )
        )

    schema_exact = (
        set(result.keys())
        == TOP_LEVEL_KEYS
        and set(
            result[
                "second_check"
            ].keys()
        )
        == SECOND_CHECK_KEYS
    )

    return {
        "verification":
            result,

        "raw_text":
            raw_text,

        "strict_json":
            strict,

        "schema_exact":
            schema_exact,
    }
