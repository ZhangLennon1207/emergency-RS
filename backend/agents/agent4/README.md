# Agent4：可信灾情报告生成（V3）

当前正式版本为 `Agent4-V3`，能力名保持 `report_generation`；历史来源
`Agent5-V2` 只记录在 manifest。模型仅消费 Agent3 生成的可信证据包。

正式证据字段为 `accepted_claims`、`revised_claims`、`rejected_claims` 和
`pending_claims`。正式报告结构位于 `platform_report_json.sections.*`，不再以旧
`key_findings` 作为模型契约。输出同时包含 `markdown_report_zh` 和
`markdown_report_en`；仓库当前旧前端所需的 `markdown_report` 暂时作为中文兼容
别名返回。

`adapter.py` 实现统一 `run(payload, work_dir, config)`，并复用进程内
`ReusableAgent4Adapter`，避免每个请求重新加载 7B 模型。模型路径通过
`AGENT4_BASE_MODEL` 和 `AGENT4_ADAPTER` 配置，权重不提交。

无模型测试：

```powershell
python -m pytest backend/agents/agent4/tests
```
