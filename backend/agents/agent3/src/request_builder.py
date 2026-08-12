def build_request_from_dataset_record(
    record,
):
    """
    Convert one Agent3 training/evaluation-style record
    into the runtime request contract.

    This helper is mainly used for regression tests
    and integration demos.
    """

    return {
        "system":
            record.get(
                "system"
            ),

        "instruction":
            record.get(
                "instruction",
                ""
            ),

        "input":
            record.get(
                "input",
                ""
            ),

        "images":
            record.get(
                "images",
                []
            ),
    }
