# Agent1：时空视觉证据感知

负责人：`AutigerBai`。本目录包含 Agent1 最终四模型流水线、可复现训练/评估源码和统一 adapter；不包含数据集、模型权重或运行输出。

## 当前能力边界

Agent1 已在原开发环境完成真实训练、推理和本地评估。迁移后的 GitHub 源码已去除个人绝对路径，并已用四个指定本地权重完成 `strict=True` 加载、模型形状和一个已知样本的 GPU 流水线回归。尚未与当前 React 前端真实联调，也不代表四智能体全流程已经实现。

`for_agent4/review_flags.json` 是历史兼容路径。当前 `review_flags` schema `1.2`
只供总控后端和前端显示人工复核提示，不作为证据，也不输入 Agent2、Agent3
或 Agent4 模型。

四个模型依次负责：

1. 灾前建筑二值分割。
2. 灾前/灾后与建筑先验的五类建筑损伤分割。
3. 灾前道路二值分割。
4. 灾前/灾后与道路先验的三类道路状态分割。

权重文件名、大小与 SHA-256 见 [模型卡](docs/model-card.md)。权重只能保存在模型电脑，不得提交到 Git。

## 统一调用

```python
from backend.agents.agent1.adapter import run

result = run(
    payload={
        "sample_id": "sample-001",
        "pre_image": "runtime/input/pre.png",
        "post_image": "runtime/input/post.png",
    },
    work_dir="runtime/jobs/job-001",
    config={
        "device": "cuda",
        "model_paths": {
            "building": "<local model path>",
            "damage": "<local model path>",
            "road_binary": "<local model path>",
            "road_status": "<local model path>",
        },
    },
)
```

显式 `config.model_paths` 优先；也可使用：

```text
AGENT1_BUILDING_MODEL_PATH
AGENT1_DAMAGE_MODEL_PATH
AGENT1_ROAD_BINARY_MODEL_PATH
AGENT1_ROAD_STATUS_MODEL_PATH
AGENT1_CHECKPOINT_DIR
AGENT1_DEVICE
```

所有成果写入 `work_dir`，adapter 只返回相对路径。生成 JSON 中的输入、输出和 checkpoint 绝对路径会在返回前清理。

## 训练与评估

- `training/dataset_tools/`：EBD、OpenEarthMap、SpaceNet8 数据准备与检查。
- `training/train_*.py`：四个最终模型的训练入口。
- `evaluation/`：单模型评估、后处理评估和完整流水线批量评估。
- 数据集要求和划分方式见 [数据集说明](docs/datasets.md)。
- 所有工具通过 `AGENT1_WORKSPACE` 定位外部工作区；默认使用当前目录。

训练和评估脚本由最终有效旧脚本迁移而来，保留了原算法逻辑。历史中间版本未原样提交。

## 验证

无需权重的检查：

```powershell
python -m pytest backend/agents/agent1/tests
```

本地 GPU 回归：配置四个权重后运行 adapter 或 `src/pipeline.py`，确认四个 checkpoint 均能 `strict=True` 加载，并用已知样本比对汇总指标。GitHub CI 不读取数据集或权重。
