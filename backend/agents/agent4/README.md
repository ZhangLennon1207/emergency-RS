# Agent4：可信灾情报告生成

当前Agent4对应历史交接版本 `Agent5-V2`。负责人将可信证据包转报告、格式归一化和导出代码提交到本目录。

## 输入

- Agent3生成的 `verified_evidence_package`

## 主要输出

- `platform_report_json`
- `markdown_report`
- 固定五段式报告正文

## 提交要求

1. 原始代码放入 `src/`。
2. 在 `adapter.py` 中接入统一 `run()`。
3. 正式结论只能使用 accepted和qualified内容。
4. 保留 `normalize_agent5_output.py` 或等价归一化步骤。
5. 测试Markdown五个固定标题完整存在。

正式字段以 `docs/api-contract.md` 的 `report_generation` 为准。
