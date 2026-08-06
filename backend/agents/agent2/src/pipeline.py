# -*- coding: utf-8 -*-
"""Agent2: pre/post-disaster remote-sensing change description with Qwen2.5-VL + LoRA."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import torch
from PIL import Image
from peft import PeftModel
from qwen_vl_utils import process_vision_info
from transformers import AutoProcessor, BitsAndBytesConfig

try:
    from transformers import Qwen2_5_VLForConditionalGeneration as ModelClass
except ImportError:
    from transformers import AutoModelForImageTextToText as ModelClass


AGENT2_ROOT = Path(__file__).resolve().parents[1]
PROMPT_PATH = AGENT2_ROOT / "src" / "prompts" / "paired.txt"
DEFAULT_OUTPUT_ROOT = AGENT2_ROOT / "outputs" / "agent2_runs"

BASE_MODEL_PATH = os.environ.get("AGENT2_BASE_MODEL_PATH")
LORA_PATH = os.environ.get("AGENT2_LORA_PATH")

# Two images are used simultaneously. These limits reduce visual-token memory.
MIN_PIXELS = 256 * 28 * 28
MAX_PIXELS = 512 * 28 * 28
DEFAULT_GPU_MEMORY = "6GiB"
DEFAULT_CPU_MEMORY = "24GiB"
DEFAULT_MAX_NEW_TOKENS = 320


def validate_paths(base_model_path: Path, lora_path: Path, prompt_path: Path) -> None:
    required = {
        "base model directory": base_model_path,
        "LoRA directory": lora_path,
        "LoRA config": lora_path / "adapter_config.json",
        "LoRA weights": lora_path / "adapter_model.safetensors",
        "prompt": prompt_path,
    }
    missing = [f"{name}: {path}" for name, path in required.items() if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing required files:\n" + "\n".join(missing))

    model_weights = list(base_model_path.glob("*.safetensors"))
    if not model_weights:
        raise FileNotFoundError(f"No .safetensors weights found in {base_model_path}")


def load_prompt(path: Path) -> str:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"Prompt file is empty: {path}")
    return text


def processor_source(base_model_path: Path, lora_path: Path) -> Path:
    # Prefer the tokenizer/chat template saved with the LoRA run.
    if (lora_path / "preprocessor_config.json").exists() and (
        lora_path / "tokenizer_config.json"
    ).exists():
        return lora_path
    return base_model_path


def clean_text(text: str) -> str:
    text = text.strip()
    for prefix in ("assistant\n", "Assistant:\n", "assistant:", "Assistant:"):
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
    return " ".join(text.split())


class Agent2Pipeline:
    def __init__(
        self,
        gpu_memory: str = DEFAULT_GPU_MEMORY,
        cpu_memory: str = DEFAULT_CPU_MEMORY,
        base_model_path: str | Path | None = None,
        lora_path: str | Path | None = None,
        prompt_path: str | Path = PROMPT_PATH,
        offload_dir: str | Path | None = None,
    ) -> None:
        base_value = base_model_path or BASE_MODEL_PATH
        lora_value = lora_path or LORA_PATH
        if not base_value:
            raise ValueError("缺少 Agent2 基础模型路径：base_model_path")
        if not lora_value:
            raise ValueError("缺少 Agent2 LoRA 路径：lora_path")
        self.base_model_path = Path(base_value)
        self.lora_path = Path(lora_value)
        self.prompt_path = Path(prompt_path)
        validate_paths(self.base_model_path, self.lora_path, self.prompt_path)
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA GPU is not available in agent2_env.")

        self.processor_path = processor_source(self.base_model_path, self.lora_path)
        self.offload_dir = Path(
            offload_dir
            or os.environ.get("AGENT2_OFFLOAD_DIR", AGENT2_ROOT / "model_offload")
        )
        self.offload_dir.mkdir(parents=True, exist_ok=True)

        adapter_cfg = json.loads(
            (self.lora_path / "adapter_config.json").read_text(encoding="utf-8")
        )

        print("=" * 100)
        print("Initializing Agent2Pipeline")
        print("=" * 100)
        print(f"torch: {torch.__version__}")
        print(f"CUDA runtime: {torch.version.cuda}")
        print(f"GPU: {torch.cuda.get_device_name(0)}")
        print(f"Base model: {self.base_model_path}")
        print(f"LoRA: {self.lora_path}")
        print(f"Processor: {self.processor_path}")
        print(f"LoRA type: {adapter_cfg.get('peft_type')}")
        print(f"LoRA base model record: {adapter_cfg.get('base_model_name_or_path')}")

        self.processor = AutoProcessor.from_pretrained(
            str(self.processor_path),
            min_pixels=MIN_PIXELS,
            max_pixels=MAX_PIXELS,
            trust_remote_code=True,
            local_files_only=True,
        )

        quant_cfg = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.float16,
        )

        print("Loading Qwen2.5-VL-7B in 4-bit mode...")
        self.base_model = ModelClass.from_pretrained(
            str(self.base_model_path),
            quantization_config=quant_cfg,
            device_map="auto",
            max_memory={0: gpu_memory, "cpu": cpu_memory},
            offload_folder=str(self.offload_dir),
            offload_state_dict=True,
            low_cpu_mem_usage=True,
            dtype=torch.float16,
            trust_remote_code=True,
            local_files_only=True,
        )

        print("Loading LoRA adapter...")
        self.model = PeftModel.from_pretrained(
            self.base_model,
            str(self.lora_path),
            is_trainable=False,
        )
        self.model.eval()
        if hasattr(self.model, "config"):
            self.model.config.use_cache = True

        print("Agent2 model is ready.")
        print(f"GPU allocated: {torch.cuda.memory_allocated(0) / 1024**3:.2f} GiB")
        print(f"GPU reserved:  {torch.cuda.memory_reserved(0) / 1024**3:.2f} GiB")
        print("=" * 100)

    @staticmethod
    def _open_image(path: Path) -> Image.Image:
        if not path.exists():
            raise FileNotFoundError(f"Image not found: {path}")
        return Image.open(path).convert("RGB")

    def _messages(self, pre: Image.Image, post: Image.Image, prompt: str):
        return [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Pre-disaster image:"},
                    {
                        "type": "image",
                        "image": pre,
                        "min_pixels": MIN_PIXELS,
                        "max_pixels": MAX_PIXELS,
                    },
                    {"type": "text", "text": "Post-disaster image:"},
                    {
                        "type": "image",
                        "image": post,
                        "min_pixels": MIN_PIXELS,
                        "max_pixels": MAX_PIXELS,
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ]

    def generate(
        self,
        pre_image_path: Path,
        post_image_path: Path,
        prompt: str,
        max_new_tokens: int = DEFAULT_MAX_NEW_TOKENS,
    ) -> Tuple[str, str]:
        messages = self._messages(
            self._open_image(pre_image_path),
            self._open_image(post_image_path),
            prompt,
        )
        return self.generate_from_messages(
            messages,
            max_new_tokens=max_new_tokens,
        )

    def generate_from_messages(
        self,
        messages,
        max_new_tokens: int = DEFAULT_MAX_NEW_TOKENS,
    ) -> Tuple[str, str]:
        """Generate from a caller-supplied Qwen-VL chat message.

        The existing two-image ``generate`` path delegates here without
        changing its message construction, processor arguments, or decoding
        settings.  Ablation experiments can therefore supply a single-image
        message without duplicating model-generation code.
        """
        chat_text = self.processor.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        image_inputs, video_inputs = process_vision_info(messages)
        inputs = self.processor(
            text=[chat_text],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
        )

        input_device = self.model.get_input_embeddings().weight.device
        inputs = inputs.to(input_device)

        try:
            with torch.inference_mode():
                generated_ids = self.model.generate(
                    **inputs,
                    max_new_tokens=max_new_tokens,
                    do_sample=False,
                    repetition_penalty=1.05,
                    use_cache=True,
                )
        except torch.OutOfMemoryError as exc:
            torch.cuda.empty_cache()
            raise RuntimeError(
                "CUDA out of memory. Close GPU applications first. If it still fails, "
                "change MAX_PIXELS from 512 to 384 and use --max_new_tokens 192."
            ) from exc

        trimmed_ids = [
            output_ids[len(input_ids):]
            for input_ids, output_ids in zip(inputs.input_ids, generated_ids)
        ]
        raw = self.processor.batch_decode(
            trimmed_ids,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        )[0].strip()
        return raw, clean_text(raw)

    def run_one(
        self,
        pre_image_path: Path,
        post_image_path: Path,
        sample_id: str,
        prompt_path: Path | None = None,
        output_root: Path = DEFAULT_OUTPUT_ROOT,
        max_new_tokens: int = DEFAULT_MAX_NEW_TOKENS,
        overwrite: bool = True,
    ) -> Dict[str, Any]:
        pre_image_path = Path(pre_image_path)
        post_image_path = Path(post_image_path)
        prompt_path = Path(prompt_path or self.prompt_path)
        output_root = Path(output_root)
        validate_paths(self.base_model_path, self.lora_path, prompt_path)
        prompt = load_prompt(prompt_path)

        sample_root = output_root / sample_id
        if sample_root.exists() and overwrite:
            shutil.rmtree(sample_root)
        sample_root.mkdir(parents=True, exist_ok=True)

        output_json = sample_root / "agent2_output.json"
        raw_txt = sample_root / "raw_response.txt"
        prompt_snapshot = sample_root / "prompt_snapshot.txt"
        manifest_json = sample_root / "run_manifest.json"
        start_time = datetime.now().isoformat(timespec="seconds")

        try:
            raw, description = self.generate(
                pre_image_path,
                post_image_path,
                prompt,
                max_new_tokens=max_new_tokens,
            )
            if not description:
                raise RuntimeError("The model generated an empty response.")

            raw_txt.write_text(raw, encoding="utf-8")
            prompt_snapshot.write_text(prompt, encoding="utf-8")

            payload = {
                "schema_version": "1.0",
                "agent_id": "agent2",
                "agent_name": "change_description",
                "sample_id": sample_id,
                "language": "en",
                "description": description,
                "input_images": {
                    "pre_image": pre_image_path.name,
                    "post_image": post_image_path.name,
                },
                "routing": {
                    "intended_recipient": "agent3_evidence_verification",
                    "agent3_instruction": (
                        "Split the description into atomic claims and verify each claim "
                        "against Agent1 evidence."
                    ),
                },
            }
            output_json.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )

            manifest = {
                "schema_version": "1.0",
                "sample_id": sample_id,
                "status": "success",
                "start_time": start_time,
                "end_time": datetime.now().isoformat(timespec="seconds"),
                "base_model": self.base_model_path.name,
                "lora_adapter": self.lora_path.name,
                "processor_source": self.processor_path.name,
                "prompt": prompt_path.name,
                "quantization": {
                    "load_in_4bit": True,
                    "quant_type": "nf4",
                    "double_quant": True,
                    "compute_dtype": "float16",
                },
                "generation": {
                    "max_new_tokens": max_new_tokens,
                    "do_sample": False,
                    "repetition_penalty": 1.05,
                },
                "outputs": {
                    "agent2_output": output_json.name,
                    "raw_response": raw_txt.name,
                    "prompt_snapshot": prompt_snapshot.name,
                },
            }
            manifest_json.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
            )

            return {
                "sample_id": sample_id,
                "status": "success",
                "description": description,
                "sample_root": sample_root.name,
                "agent2_output": output_json.name,
                "run_manifest": manifest_json.name,
            }

        except Exception as exc:
            error_path = sample_root / "error.txt"
            error_path.write_text(traceback.format_exc(), encoding="utf-8")
            failed = {
                "schema_version": "1.0",
                "sample_id": sample_id,
                "status": "failed",
                "start_time": start_time,
                "end_time": datetime.now().isoformat(timespec="seconds"),
                "error": str(exc),
                "error_path": error_path.name,
            }
            manifest_json.write_text(
                json.dumps(failed, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            raise


def parse_args():
    parser = argparse.ArgumentParser(description="Run Agent2 on one pre/post image pair.")
    parser.add_argument("--pre_image", required=True)
    parser.add_argument("--post_image", required=True)
    parser.add_argument("--sample_id", required=True)
    parser.add_argument("--prompt_path", default=str(PROMPT_PATH))
    parser.add_argument("--output_root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--base_model_path", default=BASE_MODEL_PATH)
    parser.add_argument("--lora_path", default=LORA_PATH)
    parser.add_argument("--offload_dir")
    parser.add_argument("--gpu_memory", default=DEFAULT_GPU_MEMORY)
    parser.add_argument("--cpu_memory", default=DEFAULT_CPU_MEMORY)
    parser.add_argument("--max_new_tokens", type=int, default=DEFAULT_MAX_NEW_TOKENS)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    pipeline = Agent2Pipeline(
        gpu_memory=args.gpu_memory,
        cpu_memory=args.cpu_memory,
        base_model_path=args.base_model_path,
        lora_path=args.lora_path,
        prompt_path=args.prompt_path,
        offload_dir=args.offload_dir,
    )
    result = pipeline.run_one(
        pre_image_path=Path(args.pre_image),
        post_image_path=Path(args.post_image),
        sample_id=args.sample_id,
        prompt_path=Path(args.prompt_path),
        output_root=Path(args.output_root),
        max_new_tokens=args.max_new_tokens,
    )
    print("=" * 100)
    print("Agent2 single-sample inference completed")
    print("=" * 100)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
