import json
import re

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


def _close_truncated_json(text):
    """Repair only a mechanically truncated JSON suffix.

    This never invents fields or values. It only closes an open string and
    unmatched arrays/objects when the response already starts with an object.
    The normal schema validator remains the final gate.
    """
    candidate = str(text).strip()
    start = candidate.find("{")
    if start < 0:
        return None
    candidate = candidate[start:]
    stack = []
    in_string = False
    escaped = False
    for char in candidate:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "[{":
            stack.append(char)
        elif char in "]}":
            if not stack:
                return None
            opener = stack.pop()
            if (opener, char) not in {("[", "]"), ("{", "}")}:
                return None
    if in_string:
        if escaped:
            candidate += "\\"
        candidate += '"'
    candidate += "".join("}" if opener == "{" else "]" for opener in reversed(stack))
    return _strict_json(candidate)


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

    repaired = _close_truncated_json(text)
    if repaired is not None:
        return repaired

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

    # Repair only known field-name typos. Values are moved unchanged; no
    # support decision or evidence reference is inferred by the runtime.
    aliases = {
        "supported_status": "support_status",
        "supportstatus": "support_status",
    }
    for legacy, frozen in aliases.items():
        if legacy not in result:
            continue
        if frozen in result:
            raise Agent3ContractError(
                f"both legacy and frozen fields are present: {legacy}, {frozen}"
            )
        result[frozen] = result.pop(legacy)

    second = result.get("second_check")

    # A common bounded generation failure omits the unchanged second_check
    # block on a format-only retry. Restore this schema constant only; no
    # support decision, evidence ID, reason, or review state is inferred.
    if second is None:
        result["second_check"] = {
            "required": False,
            "trigger_reasons": [],
            "recommended_inputs": [],
            "recommended_next_step": "",
        }
        second = result["second_check"]

    errors = validate_verification(
        result
    )

    # Reject direct status/reason contradictions. This is a contract check,
    # not a semantic rewrite: invalid output is retried and never relabelled.
    status = result.get("support_status")
    explanation = " ".join([
        str(result.get("reason", "")),
        str(result.get("suggested_revision", "")),
    ]).lower()
    if status == "supported" and re.search(
        r"\b(?:0|zero) affected pixels\b|\bno affected pixels\b|"
        r"\bno (?:valid )?evidence\b|\bnot supported\b",
        explanation,
    ):
        errors.append("support_status=supported contradicts reason text")

    if errors:
        raise Agent3ContractError(
            "; ".join(
                errors
            )
        )

    if set(result.keys()) != TOP_LEVEL_KEYS:
        missing = sorted(TOP_LEVEL_KEYS - set(result.keys()))
        extra = sorted(set(result.keys()) - TOP_LEVEL_KEYS)
        raise Agent3ContractError(
            f"root fields drifted; missing={missing}; extra={extra}"
        )

    if set(second.keys()) != SECOND_CHECK_KEYS:
        missing = sorted(SECOND_CHECK_KEYS - set(second.keys()))
        extra = sorted(set(second.keys()) - SECOND_CHECK_KEYS)
        raise Agent3ContractError(
            f"second_check fields drifted; missing={missing}; extra={extra}"
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
