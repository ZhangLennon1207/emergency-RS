# Agent2：灾前—灾后变化描述

负责人：`AutigerBai`。本目录交付 Qwen2.5-VL + LoRA 的微调后推理、正式提示词、固定样本评估和配对消融分析源码；不包含基础模型、LoRA 权重、数据集、逐样本输出或模型 offload 文件。

## 当前能力边界

Agent2 已在原开发环境运行真实本地模型并完成 140 条配对消融推理。迁移后的 adapter 也已使用指定本地基础模型与 LoRA 完成一个已知样本的 GPU 回归。旧项目中没有发现 Agent2 微调训练源码或完整训练清单，因此当前交付**不能声称微调训练完全可复现**。

自动消融说明模型输出会随灾前图变化，但双人盲审尚未完成；在此之前不得将结果解释为“已严格证明模型正确利用灾前—灾后对应关系”。Agent2 文本统一标记为 `verification_status: unverified`，需后续 Agent3 基于 Agent1 证据核验。

当前模型权重、LoRA 和正式 Prompt 保持不变。`sentence-span-v1` 后处理仅在原始英文段落之后增加向后兼容的 `claim_list`，不会重新训练模型，也不会改写原始 `description`。第一版按明确的句号、问号、感叹号和分号边界保留原文切分；`related_evidence_ids` 默认留空，由 Agent3 根据 Agent1 证据填写。

## 统一调用

```python
from backend.agents.agent2.adapter import run

result = run(
    payload={
        "sample_id": "sample-001",
        "pre_image": "runtime/input/pre.png",
        "post_image": "runtime/input/post.png",
    },
    work_dir="runtime/jobs/job-001",
    config={
        "base_model_path": "<local Qwen2.5-VL directory>",
        "lora_path": "<local LoRA directory>",
        "gpu_memory": "6GiB",
        "cpu_memory": "24GiB",
    },
)
```

显式 `config` 优先；也可设置 `AGENT2_BASE_MODEL_PATH`、`AGENT2_LORA_PATH` 和 `AGENT2_OFFLOAD_DIR`。adapter 将运行成果写入 `work_dir/agent2/`，对外只返回相对 Artifact 路径。

## 目录

- `src/pipeline.py`：单样本正式推理流水线。
- `src/claim_builder.py`：不改写原描述的确定性 `claim_list` 后处理。
- `src/prompts/paired.txt`：正式 paired 提示词。
- `src/prompts/post_only.txt`：post-only 消融提示词。
- `evaluation/run_same20.py`：固定样本批量评估入口。
- `experiments/pair_ablation.py`：paired/post-only/mismatched-pre 配对消融。
- `experiments/review_pair_ablation.py`：双人盲审材料与聚合分析。
- `docs/model-card.md`：基础模型、LoRA 元数据和限制。
- `docs/metrics.json`：不含逐样本文本的聚合自动指标。

## 验证

无需权重的检查：

```powershell
python -m pytest backend/agents/agent2/tests
```

本地 GPU 回归需提供基础模型和 LoRA 路径，使用一个已知样本调用 adapter，并确认输出 JSON 可序列化且 Artifact 路径均为相对路径。GitHub CI 不下载模型、不读取数据集，也不要求 CUDA。

Agent3/4 接入前还应在固定 20 条 Agent2 描述上审核 `claim_list`：确认每个原句均可追溯、不漏句，并记录仍包含多个事实的复合句。当前 `sentence-span-v1` 不声称能把所有复合句语义拆到最小原子粒度。

本目录不代表当前前端已联调，也不代表四智能体全流程已经实现。
