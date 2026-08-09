import json
from pathlib import Path

from .config import Agent3Config
from .prompts import get_system_prompt


class QwenVLAgent3Runner:
    """
    Direct Transformers/PEFT runtime for the final Agent3
    Qwen2.5-VL LoRA adapter.

    Model loading is lazy so backend startup can complete
    before GPU initialization if desired.
    """

    def __init__(
        self,
        config: Agent3Config,
    ):
        self.config = config

        self._model = None
        self._processor = None

    def _load(self):
        if self._model is not None:
            return

        import torch

        from transformers import (
            AutoProcessor,
            BitsAndBytesConfig,
        )

        try:
            from transformers import (
                Qwen2_5_VLForConditionalGeneration,
            )

            model_cls = (
                Qwen2_5_VLForConditionalGeneration
            )

        except ImportError:
            from transformers import (
                AutoModelForVision2Seq,
            )

            model_cls = AutoModelForVision2Seq

        from peft import PeftModel

        kwargs = {
            "device_map":
                self.config.device_map,

            "trust_remote_code":
                True,

            "torch_dtype":
                torch.bfloat16,
        }

        if self.config.load_in_4bit:
            kwargs[
                "quantization_config"
            ] = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_use_double_quant=True,
                bnb_4bit_compute_dtype=(
                    torch.bfloat16
                ),
            )

        base = (
            model_cls
            .from_pretrained(
                self.config.base_model_path,
                **kwargs,
            )
        )

        self._model = (
            PeftModel
            .from_pretrained(
                base,
                self.config.adapter_path,
            )
        )

        self._model.eval()

        self._processor = (
            AutoProcessor
            .from_pretrained(
                self.config.base_model_path,
                trust_remote_code=True,
            )
        )

    def _resolve_image(self, value):
        value = str(value)

        if value.startswith(
            (
                "http://",
                "https://",
                "file://",
                "data:",
            )
        ):
            return value

        path = Path(value)

        if (
            not path.is_absolute()
            and self.config.data_root
        ):
            path = (
                Path(
                    self.config.data_root
                )
                / path
            )

        path = path.resolve()

        if not path.exists():
            raise FileNotFoundError(
                f"Image not found: {path}"
            )

        return path.as_uri()

    def _build_content(
        self,
        instruction,
        input_text,
        images,
    ):
        instruction = str(
            instruction or ""
        )

        if isinstance(
            input_text,
            str
        ):
            query = input_text
        else:
            query = json.dumps(
                input_text,
                ensure_ascii=False,
            )

        text = (
            instruction
            + "\n"
            + query
        ).strip()

        count = text.count(
            "<image>"
        )

        if count != len(images):
            raise ValueError(
                "Image-token mismatch: "
                f"<image>={count}, "
                f"images={len(images)}"
            )

        parts = text.split(
            "<image>"
        )

        content = []

        for index, part in enumerate(
            parts
        ):
            if part:
                content.append({
                    "type":
                        "text",

                    "text":
                        part,
                })

            if index < len(images):
                content.append({
                    "type":
                        "image",

                    "image":
                        self._resolve_image(
                            images[index]
                        ),

                    "max_pixels":
                        self.config
                        .image_max_pixels,
                })

        return content

    def generate(
        self,
        request,
    ):
        self._load()

        import torch
        from qwen_vl_utils import (
            process_vision_info,
        )

        system_prompt = request.get(
            "system"
        )

        if not system_prompt:
            system_prompt = (
                get_system_prompt()
            )

        content = self._build_content(
            request.get(
                "instruction",
                ""
            ),
            request.get(
                "input",
                ""
            ),
            request.get(
                "images",
                []
            ),
        )

        messages = [
            {
                "role":
                    "system",

                "content": [
                    {
                        "type":
                            "text",

                        "text":
                            system_prompt,
                    }
                ],
            },
            {
                "role":
                    "user",

                "content":
                    content,
            },
        ]

        prompt = (
            self._processor
            .apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )
        )

        image_inputs, video_inputs = (
            process_vision_info(
                messages
            )
        )

        model_inputs = (
            self._processor(
                text=[prompt],
                images=image_inputs,
                videos=video_inputs,
                padding=True,
                return_tensors="pt",
            )
        )

        model_inputs = (
            model_inputs.to(
                self._model.device
            )
        )

        with torch.inference_mode():
            output_ids = (
                self._model.generate(
                    **model_inputs,
                    do_sample=False,
                    max_new_tokens=(
                        self.config
                        .max_new_tokens
                    ),
                )
            )

        generated = output_ids[
            :,
            model_inputs.input_ids.shape[1]:
        ]

        text = (
            self._processor
            .batch_decode(
                generated,
                skip_special_tokens=True,
                clean_up_tokenization_spaces=False,
            )[0]
        )

        return text.strip()
