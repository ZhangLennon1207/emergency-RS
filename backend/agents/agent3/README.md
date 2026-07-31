# Agent3：证据可信校验

当前Agent3对应历史交接版本 `Agent4-V4`。负责人将Claim拆分、证据对齐、规则兜底和校验代码提交到本目录。

## 输入

- `evidence_list`
- `claim_list`
- Agent1结构化统计、Mask和Artifact引用

## 主要输出

- `check_result`
- `verified_evidence_package`
- 五类 `support_status`

## 提交要求

1. 原始代码放入 `src/`。
2. 在 `adapter.py` 中接入统一 `run()`。
3. 输出必须为严格JSON，禁止Markdown包裹。
4. 提供 supported、partially_supported、unsupported、contradicted、exaggerated 样例。
5. 保留规则兜底和能力边界测试。

正式字段以 `docs/api-contract.md` 的 `evidence_verification` 为准。
