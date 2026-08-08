import argparse
import json
from pathlib import Path


try:
    from .src.config import (
        Agent3Config,
    )

    from .src.claim_verifier import (
        Agent3Verifier,
    )

    from .src.build_verified_package import (
        build_verified_package,
    )

except ImportError:
    from src.config import (
        Agent3Config,
    )

    from src.claim_verifier import (
        Agent3Verifier,
    )

    from src.build_verified_package import (
        build_verified_package,
    )


class Agent3Adapter:
    """
    Public backend-facing API for Agent3.

    Model loading is lazy and occurs on the first
    verification call.
    """

    def __init__(
        self,
        config=None,
    ):
        self.config = (
            config
            or Agent3Config.from_env()
        )

        self._verifier = None

    def _get_verifier(self):
        if self._verifier is None:
            self._verifier = (
                Agent3Verifier(
                    self.config
                )
            )

        return self._verifier

    def health(self):
        return {
            "agent":
                "agent3",

            "role":
                "evidence_verification",

            "model_version":
                self.config
                .model_version,

            "schema_version":
                self.config
                .schema_version,

            "ready":
                True,
        }

    def verify_claim(
        self,
        request,
    ):
        return (
            self
            ._get_verifier()
            .verify(
                request
            )
        )

    def verify_batch(
        self,
        requests,
    ):
        results = [
            self.verify_claim(
                request
            )
            for request
            in requests
        ]

        return (
            build_verified_package(
                results
            )
        )

    def handle(
        self,
        payload,
    ):
        if (
            isinstance(
                payload,
                dict
            )
            and "requests"
            in payload
        ):
            return self.verify_batch(
                payload[
                    "requests"
                ]
            )

        return self.verify_claim(
            payload
        )


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--input",
        required=True
    )

    parser.add_argument(
        "--output",
        required=True
    )

    args = parser.parse_args()

    payload = json.loads(
        Path(
            args.input
        ).read_text(
            encoding="utf-8"
        )
    )

    adapter = Agent3Adapter()

    result = adapter.handle(
        payload
    )

    Path(
        args.output
    ).write_text(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    print(
        args.output
    )


if __name__ == "__main__":
    main()


def run(payload: dict, work_dir: str, config: dict | None = None) -> dict:
    """
    Compatibility entrypoint for the shared orchestrator.
    Keeps the old manifest entrypoint style:
    backend.agents.agent3.adapter:run
    """
    _ = work_dir

    if isinstance(config, Agent3Config):
        adapter = Agent3Adapter(config=config)
    else:
        adapter = Agent3Adapter()

    return adapter.handle(payload)
