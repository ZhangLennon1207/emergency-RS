from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Agent3Config:
    base_model_path: str
    adapter_path: str

    data_root: str = ""

    image_max_pixels: int = 200704
    max_new_tokens: int = 768

    load_in_4bit: bool = True
    device_map: str = "auto"

    model_version: str = "agent3-final"
    schema_version: str = "3.1"

    @classmethod
    def from_env(cls):
        base = os.environ.get(
            "AGENT3_BASE_MODEL",
            ""
        )

        adapter = os.environ.get(
            "AGENT3_ADAPTER",
            ""
        )

        if not base:
            raise RuntimeError(
                "AGENT3_BASE_MODEL is not configured."
            )

        if not adapter:
            raise RuntimeError(
                "AGENT3_ADAPTER is not configured."
            )

        return cls(
            base_model_path=base,
            adapter_path=adapter,
            data_root=os.environ.get(
                "AGENT3_DATA_ROOT",
                ""
            ),
            image_max_pixels=int(
                os.environ.get(
                    "AGENT3_IMAGE_MAX_PIXELS",
                    "200704"
                )
            ),
            max_new_tokens=int(
                os.environ.get(
                    "AGENT3_MAX_NEW_TOKENS",
                    "768"
                )
            ),
            load_in_4bit=(
                os.environ.get(
                    "AGENT3_LOAD_IN_4BIT",
                    "1"
                )
                not in {
                    "0",
                    "false",
                    "False",
                }
            ),
            model_version=os.environ.get(
                "AGENT3_MODEL_VERSION",
                "agent3-final"
            ),
        )
