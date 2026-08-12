# Agent3：证据可信校验（V5.2）

当前正式版本为 `Agent3-V5.2.1`，能力名保持 `evidence_verification`；
历史实验来源 `Agent4-V4` 仅记录在 manifest，不再作为 HTTP `source_version`。

模块消费 Agent2 已拆分的英文 `claim_list`、Agent1 `evidence_list` 以及灾前/灾后
影像。`claim_type` 必须来自 `schemas/claim_type_enum_v52.json` 的 12 类冻结枚举，
不得在 Agent3 内通过关键词猜测。

主要输出为 `3.1-runtime` check result 和
`agent3_verified_package_v1.1`。最终证据包使用 `revised_claims`，不再使用历史
`qualified_claims`；并补全 `task_info.scene_uid`、`atomic_claim` 和完整原 claim。

`adapter.py` 提供仓库统一的 `run(payload, work_dir, config)`，HTTP 服务复用
`Agent3Adapter`，同一批 claim 只加载一次模型。模型路径来自 `AGENT3_BASE_MODEL`
和 `AGENT3_ADAPTER`，权重不进入仓库。

当 deterministic policy 要求二次核验时，Runtime 使用私有
`second_pass_context` 定位 evidence bbox、裁剪相关图片并构造第二次 V5.2 request；
上下文不足或输出冲突时进入 pending/human review，不编造结论。

无模型测试：

```powershell
python -m pytest backend/agents/agent3/tests
```
