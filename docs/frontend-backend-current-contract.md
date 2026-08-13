# 前端—总控后端当前可执行契约

## Agent3-V5.2.1 状态兼容说明（2026-08-12）

统一任务结果新增：

```json
{
  "review_required": true,
  "attention_required": true,
  "review_summary": {
    "agent1_review_required": false,
    "human_review_required": true,
    "human_review_claim_count": 1,
    "model_output_invalid": true,
    "model_output_invalid_count": 1,
    "pending_claim_count": 2,
    "other_pending_claim_count": 0
  }
}
```

- `review_required` 为兼容字段，现在只表示需要人工参与的复核，不再把模型 JSON/Schema 失败算作人工复核。
- `attention_required` 表示存在任意待处理事项，包括人工复核、`model_output_invalid` 或尚未分类的 pending claim。
- `model_output_invalid` 是输出契约失败，不代表遥感证据在语义上存在争议。
- 前端应分别显示“待人工复核”和“模型输出异常”。
- Agent3 版本优先读取远端响应，其次读取 `/api/v1/health` 的 `agent3.version`；当前运行时为 `Agent3-V5.2.1`。
- Agent3 正式分组为 `accepted_claims`、`revised_claims`、`rejected_claims`、`pending_claims`。历史 `qualified_claims` 仅作为前端兼容输入。
- Agent4 正式 Markdown 字段为 `markdown_report_zh` 和 `markdown_report_en`，前端分别提供中英文下载。

> 更新日期：2026-08-10
> 当前实现范围：Agent1/Agent2 本地真实 Adapter；Agent3/Agent4 条件远程编排已实现，等待与魏松辰真实服务完成 SSH 联调。
> 前端只访问总控后端，不直接访问任一模型或魏松辰的电脑。

## 1. 当前能力边界

| 能力 | 当前状态 | 前端必须如何显示 |
| --- | --- | --- |
| Agent1 视觉证据 | 本地真实模型 Adapter | 可显示结构化统计、结果图和人工复核提示 |
| Agent2 变化描述 | 本地真实 Qwen2.5-VL + LoRA Adapter | 显示英文描述、`claim_type` 和证据关联；以 `verified` 判断是否已核验 |
| Agent3 证据校验 | 配置远程服务后进入 Job 编排 | 显示 accepted/revised/rejected/pending 四组真实结果 |
| Agent4 双语报告 | Agent3 成功后进入 Job 编排 | 分别显示 JSON、中文 Markdown 和英文 Markdown |

只要响应中 `four_agent_pipeline_complete=false`，前端就不得使用“完整四智能体
分析完成”等措辞。

## 2. 前端提交任务

```http
POST /api/v1/jobs
Content-Type: multipart/form-data
```

| 表单字段 | 类型 | 必填 | 规则 |
| --- | --- | --- | --- |
| `pre_image` | PNG/JPEG 文件 | 是 | 灾前影像 |
| `post_image` | PNG/JPEG 文件 | 是 | 灾后影像，尺寸必须与灾前图一致 |
| `sample_id` | 字符串 | 否 | `^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$`；省略时由后端生成 |

默认限制：每张图不超过 25 MiB，像素总数不超过 100,000,000。后端会统一
处理 EXIF 方向并保存为 RGB PNG。

创建成功返回 HTTP `202`：

```json
{
  "job_id": "9f6...",
  "sample_id": "case-001",
  "contract_version": "draft-0.2",
  "pipeline_version": "competition-four-agent-v1",
  "agent34_contract_version": "agent34-http-1.0",
  "status": "queued",
  "stage": "等待本地模型队列",
  "progress": 0,
  "result": null,
  "errors": [],
  "status_url": "/api/v1/jobs/9f6..."
}
```

### 2.1 读取真实任务列表

```http
GET /api/v1/jobs?page=1&page_size=20
```

`page` 从 1 开始，`page_size` 取值为 1～100。接口按创建时间倒序返回 SQLite
中的任务摘要：

```json
{
  "items": [
    {
      "job_id": "9f6...",
      "sample_id": "case-001",
      "status": "succeeded",
      "stage": "当前双智能体范围执行成功",
      "progress": 100,
      "created_at": "2026-08-08T08:00:00+00:00",
      "scope": "agent1_agent2_local_only",
      "four_agent_pipeline_complete": false,
      "scene_risk_level": "high",
      "review_required": true
    }
  ],
  "page": 1,
  "page_size": 20,
  "total": 1
}
```

列表接口不返回本地图片路径或完整 `result`。前端点击真实任务后进入
`/live-jobs/{job_id}`，再通过单任务接口读取详情。

### 2.2 读取真实态势统计

```http
GET /api/v1/dashboard
```

接口返回 SQLite 全量任务的状态计数、最近 24 小时四小时分桶趋势和最近 4 条
任务摘要。`counts.succeeded` 表示该任务当前启用范围成功；是否为完整四阶段必须
读取任务结果中的 `four_agent_pipeline_complete`，不能仅由状态推断。

主要字段：

```json
{
  "scope": "four_agent_remote_service",
  "four_agent_pipeline_complete": true,
  "review_required": true,
  "counts": {
    "total": 12,
    "active": 1,
    "review_required": 2,
    "succeeded": 8,
    "partial_success": 1,
    "failed": 2
  },
  "trend": [{"time": "08:00", "tasks": 2, "completed": 1}],
  "recent_jobs": []
}
```

## 3. 任务状态与轮询

```http
GET /api/v1/jobs/{job_id}
```

当前后端没有 WebSocket/SSE。前端建议每 1～2 秒轮询一次，在终态停止。

| `status` | 是否终态 | 页面含义 |
| --- | --- | --- |
| `queued` | 否 | 等待模型队列 |
| `starting` | 否 | 准备任务 |
| `running_agent1` | 否 | Agent1 正在提取视觉证据 |
| `running_agent2` | 否 | Agent2 正在生成变化描述 |
| `running_agent3` | 否 | Agent3 正在逐条核验证据 |
| `running_agent4` | 否 | Agent4 正在生成双语报告 |
| `assembling` | 否 | 后端正在整理统一结果 |
| `succeeded` | 是 | 当前启用范围全部成功；继续检查是否为四阶段范围 |
| `partial_success` | 是 | 至少一个智能体成功，后续或其他阶段失败/跳过 |
| `failed` | 是 | 没有可用的智能体结果 |

前端进度条使用后端返回的 `progress`，阶段文字使用 `stage`，不要自行根据时间
推断模型是否完成。

## 4. 获取统一结果

```http
GET /api/v1/jobs/{job_id}/result
```

任务尚未产出结果时返回 HTTP `409 RESULT_NOT_READY`。当前成功结果的关键结构：

```json
{
  "contract_version": "draft-0.2",
  "pipeline_version": "agent12-local-adapters-v1",
  "job_id": "9f6...",
  "sample_id": "case-001",
  "scope": "agent1_agent2_local_only",
  "four_agent_pipeline_complete": false,
  "artifacts": {
    "input_pre": "/api/v1/jobs/9f6.../artifacts/input_pre",
    "input_post": "/api/v1/jobs/9f6.../artifacts/input_post",
    "agent1_fused_overlay": "/api/v1/jobs/9f6.../artifacts/agent1_fused_overlay",
    "agent1_review_flags": "/api/v1/jobs/9f6.../artifacts/agent1_review_flags",
    "agent3_verified_evidence_package": "/api/v1/jobs/9f6.../artifacts/agent3_verified_evidence_package",
    "agent4_platform_report": "/api/v1/jobs/9f6.../artifacts/agent4_platform_report",
    "agent4_markdown_report_zh": "/api/v1/jobs/9f6.../artifacts/agent4_markdown_report_zh",
    "agent4_markdown_report_en": "/api/v1/jobs/9f6.../artifacts/agent4_markdown_report_en"
  },
  "agent_runs": [],
  "agent1": {
    "status": "succeeded",
    "source_schema_versions": {
      "evidence_ledger": "2.1",
      "report_summary": "1.1",
      "review_flags": "1.2"
    },
    "summary": {
      "total_buildings": 18,
      "damaged_buildings": 10,
      "building_damage_ratio": 0.5556,
      "affected_road_ratio": 0.7095,
      "scene_risk_level": "high",
      "review_required": true
    },
    "review_flags": {
      "schema_version": "1.2",
      "review_required": true,
      "uncertainty_summary": {},
      "review_reasons": [],
      "report_instruction": {},
      "routing": {
        "intended_recipient": "backend_review_display"
      }
    }
  },
  "agent2": {
    "status": "succeeded",
    "source_schema_version": "1.1",
    "description": "...",
    "language": "en",
    "claim_builder_version": "sentence-span-v1",
    "claim_list": [
      {
        "claim_id": "C001",
        "claim": "...",
        "language": "en",
        "claim_type": "building_damage_presence",
        "claim_type_source": "keyword-rules-v1",
        "source": "agent2_description_postprocess",
        "source_text_span": {"start": 0, "end": 42},
        "related_evidence_ids": ["SCENE_BUILDING_SUMMARY", "VIS_DAMAGE_MAP"]
      }
    ],
    "verified": true,
    "verification_status": "verified",
    "notice": "Agent2 claims have been checked by Agent3."
  },
  "agent3": {
    "status": "succeeded",
    "source_version": "Agent3-V5.2.1",
    "verified_evidence_package": {
      "schema_version": "agent3_verified_package_v1.1",
      "accepted_claims": [],
      "revised_claims": [],
      "rejected_claims": [],
      "pending_claims": []
    }
  },
  "agent4": {
    "status": "succeeded",
    "source_version": "Agent4-V3",
    "platform_report_json": {},
    "markdown_report_zh": "...",
    "markdown_report_en": "..."
  },
  "verification": {"verified_evidence_package": {}},
  "report": {"platform_report_json": {}}
}
```

## 5. `review_flags` 的前端含义

`review_flags` 是 Agent1 根据临界置信度和异常高比例生成的人工复核提示，不是
证据，也不代表模型结论一定错误。

前端处理规则：

1. `review_required=false`：不显示警告卡，或显示“未触发自动复核提示”。
2. `review_required=true`：在 Agent1 结果区显示醒目的“建议人工复核”标记。
3. 使用 `review_reasons[].message` 逐条显示原因；建筑 ID 可用于后续实例定位。
4. 可以显示 `report_instruction.recommended_wording`，但不得改写成“模型错误”。
5. 不把 `review_flags` 放进 Agent2 描述、Agent3证据校验或 Agent4 模型输入。

历史文件仍位于 `for_agent4/review_flags.json`，这是兼容旧产物的目录名。正式
接收方由 `routing.intended_recipient=backend_review_display` 决定。

## 6. 当前可访问的 Artifact

```http
GET /api/v1/jobs/{job_id}/artifacts/{artifact_key}
```

Artifact 是否存在以结果中的 `artifacts` 映射为准，前端不要拼接未返回的 key。

| 典型 key | 内容 | 建议页面位置 |
| --- | --- | --- |
| `input_pre` | 标准化灾前图 | 影像对比 |
| `input_post` | 标准化灾后图 | 影像对比 |
| `agent1_damage_instance_color` | 建筑实例损伤图 | 建筑结果主图层 |
| `agent1_road_status_color` | 道路状态图 | 道路结果主图层 |
| `agent1_road_affected_probability` | 道路受影响概率辅助图 | 高级/辅助图层 |
| `agent1_fused_color` | 融合证据图 | 证据展示 |
| `agent1_fused_overlay` | 原图叠加结果 | 默认分析主图 |
| `agent1_visual_compare` | 多图比较结果 | 对比/演示页 |
| `agent1_evidence_ledger` | Agent1 结构化证据 JSON | 高级证据查看/下载 |
| `agent1_report_summary` | Agent1 汇总 JSON | 高级数据查看/下载 |
| `agent1_review_flags` | 完整人工复核提示 JSON | 复核详情/下载 |
| `agent1_run_manifest` | Agent1 运行追踪 | 调试/论文复现 |
| `agent2_change_description` | Agent2 正式输出 JSON | 描述详情/下载 |
| `agent2_raw_model_response` | Agent2 原始文本 | 调试/论文复现，不默认展示 |
| `agent2_prompt_snapshot` | 本次 Prompt 快照 | 调试/论文复现，不默认展示 |
| `agent2_run_manifest` | Agent2 运行追踪 | 调试/论文复现 |
| `agent3_verified_evidence_package` | Agent3 脱敏后的可信证据包 | 核验结果查看/下载 |
| `agent3_second_check_crop_1`、`agent3_second_check_crop_2` 等 | Agent3 低置信/冲突 Claim 的局部二次核验 PNG | 成果图片区预览/下载；数字后缀由总控按实际返回顺序生成 |
| `agent4_platform_report` | Agent4 结构化报告 JSON | 报告详情/下载 |
| `agent4_markdown_report_zh` | 中文 Markdown 报告 | 中文报告查看/下载 |
| `agent4_markdown_report_en` | 英文 Markdown 报告 | 英文报告查看/下载 |

## 7. 页面功能建议

### 7.1 上传页

- 灾前/灾后两张图并排预览。
- 可选 `sample_id`。
- 在提交前检查文件类型；尺寸一致性仍以后端校验为准。
- 上传后立即保存 `job_id` 并进入进度页。

### 7.2 进度页

- 使用 `stage`、`progress` 和 `agent_runs`。
- 根据 `running_agent3`、`running_agent4` 和 `agent_runs` 显示真实阶段；只有对应 run 为 `succeeded` 才使用完成状态。
- `partial_success` 时保留成功 Agent 的结果入口，同时展示 `errors`。

### 7.3 结果页

- 影像区：灾前、灾后、`agent1_fused_overlay`，并允许切换其他已返回图层。
- Agent1 统计区：建筑数量、受损建筑、损伤比例、道路疑似受影响比例、场景风险。
- 人工复核区：根据 `review_flags` 显示标记、原因和建议措辞。
- Agent2 描述区：显示原始英文 `description`、逐条 `claim_type` 和 Evidence ID；依据 `verified` 显示核验状态。
- Agent3 区：显示 accepted/revised/rejected/pending；`skipped` 或 `failed` 时显示后端原因。
- Agent4 区：成功时分别提供 JSON、中文 Markdown 和英文 Markdown；失败或跳过时不得生成占位报告。
- 下载区：只渲染后端实际返回的 Artifact 链接。

## 8. 前端禁止做出的推断

- 模型 confidence 不是已经校准的真实正确概率。
- `review_required=true` 不等于结果错误。
- 道路红色区域只能表述为“疑似受影响”或“可能存在通行受阻风险”，不能直接称为结构性损毁。
- Agent2 的 `description` 和 `claim_list` 在 Agent3 接入前均为 `unverified`。
- Agent3/4 为 `skipped` 时，不得生成或展示伪造的核验结果和正式中文报告。
- 不得因本地配置了魏松辰服务地址，就显示“四智能体已完成”；必须以实际 Job 的 Agent3/4 运行状态为准。

## 9. 错误响应

当前 FastAPI 错误格式：

```json
{
  "detail": {
    "code": "IMAGE_SIZE_MISMATCH",
    "message": "灾前图与灾后图尺寸不一致"
  }
}
```

前端至少处理：`INVALID_IMAGE_TYPE`、`IMAGE_TOO_LARGE`、
`IMAGE_DECODE_FAILED`、`IMAGE_SIZE_MISMATCH`、`INVALID_SAMPLE_ID`、
`JOB_NOT_FOUND`、`RESULT_NOT_READY` 和 `ARTIFACT_NOT_FOUND`。

## 10. Agent3/4 条件编排原则

前端接口保持不变：仍然只提交一次 Job、轮询同一个状态接口、读取同一个统一结果。总控后端已经负责：

1. 将 Agent1 ledger 映射为魏松辰真实 `evidence_list`。
2. 把 Agent2 `claim_list` 与灾前/灾后图发送给 Agent3。
3. 把 Agent3 `verified_evidence_package` 发送给 Agent4。
4. 把 Agent3/4 的真实状态、核验结果和报告填入现有结果槽位。

当前 mapper 版本为 `agent1-ledger-2.1-to-evidence-list-v1`。真实联调若发现字段语义变化，应升级 mapper 版本并重新运行契约测试，不在前端补偿后端字段。
