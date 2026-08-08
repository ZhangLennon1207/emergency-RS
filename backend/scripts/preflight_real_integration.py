"""Check whether this computer can run the real Agent1 + Agent2 integration."""

from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.config import Settings  # noqa: E402


DEFAULT_PRE_IMAGE = (
    REPO_ROOT
    / "public"
    / "mock-data"
    / "competition-four-agent-v1"
    / "EARTHQUAKE-TURKEY_003679"
    / "artifacts"
    / "pre_image.png"
)
DEFAULT_POST_IMAGE = DEFAULT_PRE_IMAGE.with_name("post_image.png")
AGENT1_MODELS = {
    "building": "AGENT1_BUILDING_MODEL_PATH",
    "damage": "AGENT1_DAMAGE_MODEL_PATH",
    "road_binary": "AGENT1_ROAD_BINARY_MODEL_PATH",
    "road_status": "AGENT1_ROAD_STATUS_MODEL_PATH",
}
RUNTIME_MODULES = {
    "torch": "PyTorch",
    "numpy": "NumPy",
    "cv2": "OpenCV",
    "transformers": "Transformers",
    "peft": "PEFT",
    "accelerate": "Accelerate",
    "bitsandbytes": "bitsandbytes",
    "qwen_vl_utils": "qwen-vl-utils",
}


def report(ok: bool, label: str, detail: str) -> None:
    marker = "PASS" if ok else "FAIL"
    print(f"[{marker}] {label}: {detail}")


def configured_path(value: object) -> Path | None:
    if not value:
        return None
    path = Path(str(value)).expanduser()
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def check_gpu() -> bool:
    executable = shutil.which("nvidia-smi")
    if not executable:
        report(False, "NVIDIA GPU", "未找到 nvidia-smi")
        return False
    completed = subprocess.run(
        [executable, "--query-gpu=name,memory.total", "--format=csv,noheader"],
        check=False,
        capture_output=True,
        text=True,
    )
    detail = completed.stdout.strip() or completed.stderr.strip() or "查询失败"
    report(completed.returncode == 0, "NVIDIA GPU", detail)
    return completed.returncode == 0


def check_modules() -> bool:
    all_ready = True
    for module, label in RUNTIME_MODULES.items():
        ready = importlib.util.find_spec(module) is not None
        report(ready, f"运行依赖 {label}", "已安装" if ready else f"缺少模块 {module}")
        all_ready &= ready
    return all_ready


def check_agent1(settings: Settings) -> bool:
    paths = settings.agent1_config.get("model_paths") or {}
    all_ready = isinstance(paths, dict)
    for key, environment in AGENT1_MODELS.items():
        path = configured_path(paths.get(key) if isinstance(paths, dict) else None)
        ready = bool(path and path.is_file())
        report(
            ready,
            f"Agent1 {key} 权重",
            path.name if ready and path else f"请设置 {environment}",
        )
        all_ready &= ready
    return all_ready


def check_agent2(settings: Settings) -> bool:
    base_model = configured_path(settings.agent2_config.get("base_model_path"))
    lora = configured_path(settings.agent2_config.get("lora_path"))
    checks = {
        "Agent2 基础模型目录": bool(base_model and base_model.is_dir()),
        "Agent2 基础模型权重": bool(base_model and list(base_model.glob("*.safetensors"))),
        "Agent2 LoRA 目录": bool(lora and lora.is_dir()),
        "Agent2 LoRA 配置": bool(lora and (lora / "adapter_config.json").is_file()),
        "Agent2 LoRA 权重": bool(lora and (lora / "adapter_model.safetensors").is_file()),
    }
    for label, ready in checks.items():
        environment = "AGENT2_BASE_MODEL_PATH" if "基础模型" in label else "AGENT2_LORA_PATH"
        report(ready, label, "已找到" if ready else f"请检查 {environment}")
    return all(checks.values())


def check_images(pre_image: Path, post_image: Path) -> bool:
    if not pre_image.is_file() or not post_image.is_file():
        report(False, "双时相样本", "灾前图或灾后图不存在")
        return False
    try:
        with Image.open(pre_image) as pre, Image.open(post_image) as post:
            same_size = pre.size == post.size
            detail = f"灾前 {pre.size[0]}×{pre.size[1]}，灾后 {post.size[0]}×{post.size[1]}"
    except OSError as error:
        report(False, "双时相样本", f"图片无法读取：{error}")
        return False
    report(same_size, "双时相样本", detail)
    return same_size


def load_env_file(path: Path | None) -> None:
    if path is None:
        return
    if not path.is_file():
        raise FileNotFoundError(f"环境变量文件不存在：{path}")
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--pre-image", type=Path, default=DEFAULT_PRE_IMAGE)
    parser.add_argument("--post-image", type=Path, default=DEFAULT_POST_IMAGE)
    args = parser.parse_args()

    os.chdir(REPO_ROOT)
    load_env_file(args.env_file.resolve() if args.env_file else None)
    settings = Settings.from_env()
    checks = [
        check_gpu(),
        check_modules(),
        check_agent1(settings),
        check_agent2(settings),
        check_images(args.pre_image.resolve(), args.post_image.resolve()),
    ]
    print()
    if all(checks):
        print("真实 Agent1 + Agent2 联调预检通过，可以启动 FastAPI。")
        return 0
    print("真实联调预检未通过；请按 FAIL 项补齐本机模型资产或运行依赖。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
