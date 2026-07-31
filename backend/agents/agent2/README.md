# Agent2：灾情变化描述生成

负责人将视觉语言模型调用、提示词、LoRA配置和描述生成代码提交到本目录。

## 输入

- 灾前/灾后影像或可访问Artifact
- Agent1融合结果与结构化证据

## 主要输出

- 英文变化描述
- 语言和源版本
- `verification_status: unverified`
- 能力边界说明

## 提交要求

1. 原始代码放入 `src/`。
2. API Key只能通过环境变量读取。
3. 在 `adapter.py` 中接入统一 `run()`。
4. 提供一组不调用云API也能检查格式的样例和测试。
5. 禁止在未校验文本中断言人员伤亡、经济损失或救援状态。

正式字段以 `docs/api-contract.md` 的 `change_description` 为准。
