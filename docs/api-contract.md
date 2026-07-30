# Emergency RS API 契约草案

> 状态：Draft 0.2
> 临时基线：`competition-four-agent-v1`  
> 更新时间：2026-07-30

## 1. 使用原则

本契约用于当前前端 Mock、后续 FastAPI 和 Agent1～Agent4 的第一轮联调，不代表最终冻结格式。

必须遵循：

- 业务能力通过 `capability` 判断，不通过 Agent 编号判断。
- 每个任务返回 `contract_version` 和 `pipeline_version`。
- 每份 Agent 原始结果保留 `source_schema_version`。
- 后端负责把 Agent 原始字段转换为本契约，前端不直接读取 Agent 本机目录。
- 新增字段应保持向后兼容；字段删除或语义变化必须提升契约主版本。
- 未知 Agent、成果类型和附加字段不得导致前端整体崩溃。
- API 不返回 Windows、Linux 本机绝对路径和模型权重路径。

当前版本关系：

```text
API contract: draft-0.2
pipeline: competition-four-agent-v1
Agent1 evidence_ledger_core: 2.1
Agent1 agent1_report_summary: 1.1
Agent1 review_flags: 1.1
Agent2 agent2_output: 1.0
Agent3 evidence_verification: source Agent4-V4
Agent4 report_generation: source Agent5-V2
```

当前项目采用能力编号，最新交接包仍保留历史模型编号：

| 当前流水线 | capability | 交接包源版本 |
| --- | --- | --- |
| Agent3 | `evidence_verification` | Agent4-V4 |
| Agent4 | `report_generation` | Agent5-V2 |

后端和数据库必须同时保存 `agent_code`、`capability` 与 `source_version`。前端按 `capability` 决定展示区域，不根据源版本中的 Agent 数字决定位置。

### 当前可运行后端 Profile

最新 Agent1 + Agent2 网页后端已经实现，前端首轮真实联调必须优先兼容它：

```text
profile: agent12-web-backend-v1
POST /api/v1/jobs
GET  /api/v1/jobs/{job_id}
GET  /api/v1/health
```

当前后端任务状态：

```text
queued
running_agent1
running_agent2
assembling
succeeded
partial_success
failed
```

这组状态由前端适配为统一页面状态，未来 Agent3/4 接入后再新增阶段，不要求当前后端立即改变。

当前成功结果关键路径：

```text
result.artifacts.input_pre
result.artifacts.input_post
result.artifacts.agent1_fused_overlay
result.artifacts.agent1_visual_compare
result.agent1.status
result.agent1.summary
result.agent2.status
result.agent2.description
result.agent2.verified
errors
```

当前 `result.agent1.summary` 使用：

```text
total_buildings
damaged_buildings
building_damage_ratio
affected_road_ratio
scene_risk_level
review_required
```

前端每2秒查询一次任务。终止状态为 `succeeded`、`partial_success`、`failed`。

---

## 2. 标识符

| 字段 | 含义 |
| --- | --- |
| `job_id` | 一次网页提交和后端执行任务，由后端生成 |
| `sample_id` | 数据集样本身份，用于跨 Agent 配对 |
| `agent_run_id` | 某个 Agent 在某个任务中的一次执行 |
| `artifact_id` | 后端管理的单个成果文件 |
| `pipeline_version` | 智能体组合和能力顺序版本 |
| `contract_version` | 前后端 API 数据结构版本 |
| `source_schema_version` | Agent 原始 JSON Schema 版本 |

同一个 `sample_id` 可以产生多个 `job_id`；重试某个 Agent 可以产生新的 `agent_run_id`。

---

## 3. 枚举

### 3.1 任务状态

```text
queued
running
partial_success
pending_review
completed
failed
cancelled
```

### 3.2 Agent 阶段状态

```text
queued
running
succeeded
failed
skipped
```

### 3.3 能力

当前能力：

```text
visual_evidence
change_description
evidence_verification
report_generation
```

未来可增加例如 `damage_quantification`，前端不能把能力列表限制为固定四项。

### 3.4 Claim 校验状态

```text
supported
partially_supported
unsupported
contradicted
exaggerated
```

### 3.5 建筑类别

```text
0 = background
1 = no_damage
2 = minor_damage
3 = major_damage
4 = destroyed
```

背景不参与建筑数量和损伤比例统计。

### 3.6 道路类别

```text
0 = background
1 = intact
2 = suspected_affected
```

道路结果只能表述为“疑似受影响”或“可能存在通行受阻风险”，不能直接等同于结构性损毁。

---

## 4. 统一响应外壳

成功响应：

```json
{
  "data": {},
  "message": "success",
  "request_id": "req_01K..."
}
```

错误响应：

```json
{
  "error": {
    "code": "IMAGE_SIZE_MISMATCH",
    "message": "灾前图与灾后图尺寸不一致",
    "details": {
      "pre_image": [1024, 1024],
      "post_image": [2048, 2048]
    }
  },
  "request_id": "req_01K..."
}
```

前端逻辑依赖稳定的 `code`，`message` 用于用户展示，`details` 允许按错误类型扩展。

---

## 5. 创建任务

```http
POST /api/v1/jobs
Content-Type: multipart/form-data
```

表单字段：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `pre_image` | 是 | 灾前影像 |
| `post_image` | 是 | 灾后影像 |
| `sample_id` | 否 | 数据集样本可传，普通上传由后端生成 |
| `disaster_type` | 否 | 用户提供的灾害背景，不作为模型结论 |
| `name` | 否 | 任务名称 |
| `pipeline_version` | 否 | 默认使用当前稳定流水线 |

响应：

```json
{
  "data": {
    "job_id": "job_01K...",
    "sample_id": "EARTHQUAKE-TURKEY_003679",
    "contract_version": "draft-0.1",
    "pipeline_version": "competition-four-agent-v1",
    "status": "queued",
    "queue_position": 1,
    "created_at": "2026-07-29T22:00:00+08:00"
  },
  "message": "任务已创建",
  "request_id": "req_01K..."
}
```

---

## 6. 查询任务状态

```http
GET /api/v1/jobs/{job_id}
```

核心响应：

```json
{
  "data": {
    "job_id": "job_01K...",
    "sample_id": "EARTHQUAKE-TURKEY_003679",
    "contract_version": "draft-0.1",
    "pipeline_version": "competition-four-agent-v1",
    "status": "running",
    "progress": 50,
    "queue_position": null,
    "created_at": "2026-07-29T22:00:00+08:00",
    "updated_at": "2026-07-29T22:00:20+08:00",
    "agent_runs": [
      {
        "agent_run_id": "run_agent1_01K...",
        "agent_code": "agent1",
        "capability": "visual_evidence",
        "display_name": "时空视觉证据感知智能体",
        "source_schema_version": "2.1",
        "status": "succeeded",
        "progress": 100,
        "started_at": "2026-07-29T22:00:02+08:00",
        "finished_at": "2026-07-29T22:00:12+08:00",
        "error": null
      }
    ]
  },
  "message": "success",
  "request_id": "req_01K..."
}
```

阶段失败时：

```json
{
  "status": "failed",
  "error": {
    "code": "AGENT_EXECUTION_FAILED",
    "message": "变化描述生成失败",
    "retryable": true
  }
}
```

---

## 7. 查询完整结果

```http
GET /api/v1/jobs/{job_id}/result
```

顶层结构：

```json
{
  "data": {
    "job": {},
    "visual_evidence": {},
    "change_description": {},
    "verification": null,
    "report": null,
    "extensions": {}
  },
  "message": "success",
  "request_id": "req_01K..."
}
```

### 7.1 visual_evidence

```json
{
  "source_schema_versions": {
    "evidence_ledger": "2.1",
    "report_summary": "1.1",
    "review_flags": "1.1"
  },
  "building_summary": {
    "total_buildings": 18,
    "damaged_buildings": 10,
    "damage_ratio": 0.5555555556,
    "distribution": {
      "no_damage": 8,
      "minor_damage": 4,
      "major_damage": 2,
      "destroyed": 4
    },
    "mean_damage_presence_confidence": 0.5305718448,
    "mean_damage_level_confidence": 0.5283192727
  },
  "road_summary": {
    "is_affected": true,
    "total_road_pixels": 13015,
    "affected_road_pixels": 9234,
    "affected_road_ratio": 0.7094890511,
    "affected_presence_confidence": 0.8757181168,
    "wording_level": "suspected_impact",
    "interpretation_note": "红色道路表示疑似受灾影响或存在通行受阻风险，不等同于已经确认的结构性道路损毁。"
  },
  "risk": {
    "building": "high",
    "road": "high",
    "scene": "high"
  },
  "manual_review": {
    "required": true,
    "uncertain_building_count": 7,
    "uncertain_building_ids": [1, 2, 3, 6, 7, 8, 15],
    "reasons": []
  },
  "artifacts": []
}
```

建筑实例明细可能较大，单独查询：

```http
GET /api/v1/jobs/{job_id}/building-instances?page=1&page_size=50
```

### 7.2 change_description

```json
{
  "source_schema_version": "1.0",
  "language": "en",
  "description": "...",
  "verification_status": "unverified",
  "notice": "模型生成的变化描述，尚未经过证据校验。"
}
```

`verification_status`：

```text
unverified
verified
verification_failed
```

### 7.3 verification

Agent3 未完成时必须返回 `null`，不能生成空的“可信结果”。

当前 Agent3 对应交接包中的 Agent4-V4。源接口建议为 `POST /api/v1/agent4/check`，后续统一编排接口可以继续把结果放在任务结果的 `verification` 字段中。

请求核心字段：

```json
{
  "task_id": "string",
  "evidence_list": [
    {
      "evidence_id": "E001",
      "source_agent": "string",
      "source_model": "string",
      "region": "string",
      "evidence_type": "image_pair | change_mask | building_mask | damage_mask | statistics | text_description | disaster_grade",
      "image_evidence": {},
      "finding": "string",
      "supporting_statistics": {},
      "confidence": 0.8,
      "limitations": "string"
    }
  ],
  "claim_list": [
    {
      "claim_id": "C001",
      "claim": "string",
      "related_evidence_ids": ["E001"]
    }
  ]
}
```

响应结构：

```json
{
  "task_id": "string",
  "source_version": "Agent4-V4",
  "check_result": {
    "task_id": "string",
    "overall_status": "pass | warning",
    "claim_checks": [
      {
        "claim_id": "C001",
        "claim": "string",
        "support_status": "supported | partially_supported | unsupported | contradicted | exaggerated",
        "evidence_ids": ["E001"],
        "reason": "string",
        "suggested_revision": "string 或 null"
      }
    ],
    "supported_claims": ["C001"],
    "partially_supported_claims": [],
    "unsupported_claims": [],
    "contradicted_claims": [],
    "exaggerated_claims": [],
    "revision_suggestions": []
  },
  "verified_evidence_package": {
    "task_id": "string",
    "overall_status": "pass | warning",
    "accepted_claims": [],
    "qualified_claims": [],
    "rejected_claims": [],
    "source_evidence_ids": ["E001"],
    "limitations": []
  }
}
```

规则：

- `accepted_claims` 只来自 `supported`。
- `qualified_claims` 只来自 `partially_supported`，进入报告时必须保留限定措辞。
- `rejected_claims` 来自 `unsupported`、`contradicted`、`exaggerated`，不得作为正式灾情结论。
- 人员伤亡、经济损失、政府响应、救援状态等没有证据时必须判为 `unsupported`。
- Agent3 不得接收 Agent1 的 `review_flags.json`；人工复核提示属于报告与业务流程。

### 7.4 report

Agent4 未完成时返回 `null`。

当前 Agent4 对应交接包中的 Agent5-V2。源接口建议为 `POST /api/v1/agent5/report`，输入只能使用 Agent3 输出的 `verified_evidence_package`。

正式响应结构：

```json
{
  "task_id": "string",
  "source_version": "Agent5-V2",
  "platform_report_json": {
    "task_id": "string",
    "report_type": "remote_sensing_disaster_assessment",
    "report_version": "agent5_v2_from_agent4_v4",
    "overall_status": "pass | warning",
    "data_basis": {
      "source": "Agent4-V4 verified_evidence_package",
      "source_evidence_ids": ["E001"]
    },
    "key_findings": [],
    "qualified_findings": [],
    "excluded_claims": [],
    "limitations": [],
    "final_conclusion": "string"
  },
  "markdown_report": "string"
}
```

`markdown_report` 必须按照以下标题和顺序输出：

```text
## 1. 报告摘要
## 2. 核心灾情指标
## 3. 分区评估结果
## 4. 证据支撑与一致性校验
## 5. 证据局限与不可下结论事项
```

前端同时渲染 Markdown 和 `platform_report_json` 卡片，优先展示：

```text
overall_status
key_findings
qualified_findings
excluded_claims
limitations
```

Agent4 返回前必须经过源包规定的 `normalize_agent5_output.py` 后处理。正式报告正文只能使用 `accepted_claims` 和 `qualified_claims`；`rejected_claims` 只能在一致性校验或被排除结论中展示。

---

## 8. Artifact

```http
GET /api/v1/jobs/{job_id}/artifacts
GET /api/v1/artifacts/{artifact_id}/content
```

结构：

```json
{
  "artifact_id": "art_fused_overlay",
  "artifact_type": "fused_overlay",
  "file_name": "fused_overlay.png",
  "mime_type": "image/png",
  "url": "/api/v1/artifacts/art_fused_overlay/content",
  "preview_url": "/api/v1/artifacts/art_fused_overlay/content",
  "source_agent_code": "agent1",
  "metadata": {}
}
```

当前 Artifact 类型至少包括：

```text
pre_image
post_image
building_clean_mask
building_instance_mask
damage_pixel_mask
damage_instance_mask
damage_instance_color
road_clean_mask
road_status_mask
road_status_color
road_affected_probability
fused_mask
fused_color
fused_overlay
visual_compare
evidence_ledger
agent1_report_summary
review_flags
change_description
atomic_claims
verified_description
report_markdown
report_json
```

前端遇到未知 `artifact_type` 时，将其放入“其他成果”，不应丢弃。

---

## 9. 重试

```http
POST /api/v1/jobs/{job_id}/retry
```

请求：

```json
{
  "capability": "report_generation"
}
```

后端必须检查上游依赖是否可用。重试生成新的 `agent_run_id`，但保持同一 `job_id`。

---

## 10. 上传错误码

```text
INVALID_IMAGE_TYPE
IMAGE_DECODE_FAILED
IMAGE_TOO_LARGE
IMAGE_SIZE_MISMATCH
MISSING_PRE_IMAGE
MISSING_POST_IMAGE
QUEUE_UNAVAILABLE
AGENT_EXECUTION_FAILED
ARTIFACT_NOT_FOUND
PIPELINE_VERSION_UNSUPPORTED
```

---

## 11. 兼容与变更规则

### 非破坏性变化

- 新增可选字段。
- 新增 Artifact 类型。
- 新增 Agent capability。
- 新增枚举值，同时提供 `display_name`。
- `extensions` 中增加实验字段。

### 破坏性变化

- 删除字段。
- 字段改名。
- 改变字段数据类型。
- 改变比例范围，例如从 `0～1` 改成 `0～100`。
- 改变状态语义。

发生破坏性变化时：

1. 提升 `contract_version` 主版本。
2. 保留旧适配器一段过渡期。
3. 更新 Mock、接口示例和变动日志。
4. 前端根据版本选择转换函数。

前端推荐处理链：

```text
Agent 原始 JSON
→ 后端 source adapter
→ API contract
→ 前端 contract adapter
→ 页面 ViewModel
```

---

## 12. 当前真实 Mock

当前仓库提供：

```text
public/mock-data/manifest.json
public/mock-data/competition-four-agent-v1/EARTHQUAKE-TURKEY_003679/job-result.json
public/mock-data/competition-four-agent-v1/EARTHQUAKE-TURKEY_003679/artifacts/
```

该 Mock 只包含已经存在的 Agent1/2 真实结果。Agent3/4 为 `skipped`，对应结果为 `null`。
