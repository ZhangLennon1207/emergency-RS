# 前端与 Agent1～Agent4 对接设计

## 1. 设计目标

本文档根据以下两份比赛联调交接材料整理：

- 《智能体一与智能体二输出文件说明及交接指南》
- 《多智能体可信遥感灾情评估系统 Agent3 与 Agent4 接手构建指南》

目标是让 React 前端只依赖稳定 HTTP API，不直接读取 Agent 本机目录，同时兼容：

1. Agent1/2 已完成、Agent3/4 尚未接入的双智能体阶段。
2. Agent1～Agent4 全部完成的比赛联调阶段。
3. 未来拆分独立量化智能体的扩展版本。

---

## 2. 当前正式流水线

### 当前可运行联调范围

最新后端交接确认：目前可直接运行的是 Agent1 + Agent2 网页后端，Agent3/4 仍作为下一阶段扩展。

当前真实接口：

```text
POST /api/v1/jobs
GET /api/v1/jobs/{job_id}
GET /api/v1/health
```

当前真实状态：

```text
queued
running_agent1
running_agent2
assembling
succeeded
partial_success
failed
```

前端应每2秒轮询一次，并读取：

```text
result.artifacts.input_pre
result.artifacts.input_post
result.artifacts.agent1_fused_overlay
result.artifacts.agent1_visual_compare
result.agent1.summary
result.agent2.description
errors
```

这一双智能体 Profile 与下面的最终四智能体流水线并不冲突。前端通过适配层把当前结果归入 `visual_evidence` 和 `change_description` 能力，后续再补充 `evidence_verification` 与 `report_generation`。

```text
Agent1：agent1_visual_evidence
  ├── 建筑分割与实例损伤
  ├── 道路分割与受影响状态
  ├── 融合证据图
  ├── evidence_ledger_core.json
  ├── agent1_report_summary.json
  └── review_flags.json

Agent2：agent2_change_description
  └── 基于灾前/灾后原图生成英文描述

Agent3：agent3_evidence_verification
  ├── 英文描述拆分为原子 Claims
  ├── 对照 Agent1 客观证据逐条校验
  └── 生成 verified_description_en

Agent4：agent4_report_generation
  ├── 读取 Agent3 可信结果
  ├── 读取 Agent1 场景摘要和 review_flags
  └── 生成中文 JSON/Markdown 报告
```

关键边界：

- Agent2 只能读取灾前、灾后原图，不能提前读取 Agent1 结果。
- Agent3 不得读取 `review_flags.json`。
- Agent4 不重新自由看图，只使用校验结果、结构化统计和复核标志。
- Agent2/3 阶段保持英文，Agent4 阶段统一翻译为中文。

---

## 3. 标识符规则

### job_id

- 表示一次网页提交和后端执行任务。
- 由创建任务接口生成。
- 用于任务查询、队列、重试、错误和页面 URL。
- 同一组影像重复执行时会产生不同的 `job_id`。

### sample_id

- 表示实验数据中的样本身份。
- 固定20条样本必须保留原始 `sample_id`。
- Agent1～Agent4 通过 `sample_id` 配对。
- 禁止通过文件顺序或绝对路径配对。

### artifact_id

- 表示后端管理的单个成果文件。
- 前端使用 Artifact URL 访问。
- 不能把 Agent 本地绝对路径作为 Artifact URL。

---

## 4. 状态定义

### 任务总体状态

```text
queued
running
partial_success
pending_review
completed
failed
cancelled
```

### Agent 阶段状态

```text
queued
running
succeeded
failed
skipped
```

### Agent3 Claim 校验状态

```text
supported
partially_supported
unsupported
contradicted
exaggerated
```

注意：

- `pending_review` 是任务/业务复核状态，不是 Agent3 Claim 校验状态。
- `partially_supported` 和 `contradicted` 必须加入前端显示，不能合并为 `unsupported`。
- 一个 Agent 失败而其他 Agent 获得有效结果时，任务使用 `partial_success`。

---

## 5. 模型类别编码

### 建筑像素分类

```text
0 = 背景
1 = 无损建筑
2 = 轻微损伤
3 = 严重损伤
4 = 摧毁
```

前端图例推荐：

| class_id | 显示名称 | 推荐颜色 |
| --- | --- | --- |
| 1 | 无损 | 绿色 |
| 2 | 轻微损伤 | 黄色 |
| 3 | 严重损伤 | 橙色 |
| 4 | 摧毁 | 红色 |

背景不作为建筑损伤等级参与饼图。

### 道路状态

```text
0 = 背景
1 = 完好道路
2 = 疑似受影响道路
```

道路结果必须使用“疑似受影响”“可能存在通行受阻风险”等保守措辞。

---

## 6. Agent1 成果与前端展示映射

### 真实 Schema 版本

当前交接数据中：

```text
evidence_ledger_core.json  schema_version = 2.1
agent1_report_summary.json schema_version = 1.1
review_flags.json          schema_version = 1.1
agent2_output.json         schema_version = 1.0
```

后端必须保留 `source_schema_version`，并转换 JSON 中的本机绝对路径。

Agent1 真实统计字段包括：

```text
building_summary.total_buildings
building_summary.damaged_buildings
building_summary.damage_ratio
building_summary.no_damage_buildings
building_summary.minor_damage_buildings
building_summary.major_damage_buildings
building_summary.destroyed_buildings
building_summary.mean_damage_presence_confidence
building_summary.mean_damage_level_confidence
road_summary.is_affected
road_summary.total_road_pixels
road_summary.affected_road_pixels
road_summary.affected_road_ratio
road_summary.affected_presence_confidence
overall_assessment.building_risk_level
overall_assessment.road_impact_level
overall_assessment.scene_risk_level
```

前端应使用这些真实字段，不再使用先前 Mock 中的像素比例作为建筑数量统计。

### 输入影像

| Agent 文件 | artifact_type | 前端位置 |
| --- | --- | --- |
| `input/pre_image.png` | `pre_image` | 影像对比 |
| `input/post_image.png` | `post_image` | 影像对比 |

### 建筑成果

| Agent 文件 | artifact_type | 前端用途 |
| --- | --- | --- |
| `building/building_raw_mask.png` | `building_raw_mask` | 调试成果，可选下载 |
| `building/building_clean_mask.png` | `building_clean_mask` | 建筑 Mask 图层 |
| `building/damage_pixel_mask.png` | `damage_pixel_mask` | 像素级损伤图层 |
| `building/building_instance_mask.png` | `building_instance_mask` | 建筑实例选择 |
| `building/damage_instance_mask.png` | `damage_instance_mask` | 实例级损伤图层 |
| `building/damage_instance_color.png` | `damage_instance_color` | 默认建筑损伤可视化 |

`.npy` 和 `.npz` 概率文件不直接在浏览器渲染，可以作为高级调试成果下载。

### 道路成果

| Agent 文件 | artifact_type | 前端用途 |
| --- | --- | --- |
| `road/road_clean_mask.png` | `road_clean_mask` | 道路图层 |
| `road/road_status_post_mask.png` | `road_status_mask` | 道路类别图层 |
| `road/road_status_color.png` | `road_status_color` | 默认道路结果图 |
| `road/road_affected_probability.png` | `road_affected_probability` | 受影响概率辅助图 |

### 融合成果

| Agent 文件 | artifact_type | 前端用途 |
| --- | --- | --- |
| `fusion/fused_mask.png` | `fused_mask` | 机器可读融合图层 |
| `fusion/fused_color.png` | `fused_color` | Agent3 主要视觉证据 |
| `fusion/fused_overlay.png` | `fused_overlay` | 结果分析默认叠加图 |
| `fusion/visual_compare.png` | `visual_compare` | 六宫格演示与人工检查 |

### 结构化结果

| Agent 文件 | artifact_type | 前端用途 |
| --- | --- | --- |
| `for_agent3/evidence_ledger_core.json` | `evidence_ledger` | 证据引用和实例详情 |
| `for_agent4/agent1_report_summary.json` | `agent1_report_summary` | 核心统计和报告数值 |
| `for_agent4/review_flags.json` | `review_flags` | 最终复核提示 |
| `run_manifest.json` | `agent1_run_manifest` | 模型版本和运行追踪 |

---

## 7. Agent2～Agent4 成果映射

### Agent2

| 文件 | artifact_type | 前端用途 |
| --- | --- | --- |
| `agent2_output.json` | `change_description` | 英文变化描述 |
| `raw_response.txt` | `change_description_raw` | 原始响应，可选查看 |
| `prompt_snapshot.txt` | `agent2_prompt` | 实验复现信息 |
| `run_manifest.json` | `agent2_run_manifest` | 模型、LoRA 和生成参数 |

Agent3 尚未成功时，前端必须在 Agent2 文本上显示：

> 模型生成的变化描述，尚未经过证据校验。

### Agent3

当前项目 Agent3 对应最新交接包中的历史版本 `Agent4-V4`。前端使用：

```json
{
  "agent_code": "agent3",
  "capability": "evidence_verification",
  "source_agent_id": "agent4",
  "source_version": "Agent4-V4"
}
```

| 文件 | artifact_type | 前端用途 |
| --- | --- | --- |
| `check_result.json` | `verification_result` | Claim 逐条校验、分类列表和修改建议 |
| `verified_evidence_package.json` | `verified_evidence_package` | Agent4 报告生成的唯一可信事实输入 |
| `run_manifest.json` | `agent3_run_manifest` | Agent4-V4 源模型和运行追踪 |

每条 Claim 至少包含：

```json
{
  "claim_id": "C001",
  "claim": "Several buildings appear damaged.",
  "support_status": "supported",
  "evidence_ids": ["E001"],
  "reason": "The referenced evidence supports the core statement.",
  "suggested_revision": null
}
```

### Agent4

当前项目 Agent4 对应最新交接包中的历史版本 `Agent5-V2`：

```json
{
  "agent_code": "agent4",
  "capability": "report_generation",
  "source_agent_id": "agent5",
  "source_version": "Agent5-V2"
}
```

| 文件 | artifact_type | 前端用途 |
| --- | --- | --- |
| `platform_report_json` | `final_report_json` | 结论、限定结论、排除项和局限卡片 |
| `markdown_report` | `final_report_markdown` | 固定五段式中文报告预览和下载 |
| `final_report.docx` | `final_report_docx` | 可选 Word 下载 |
| `run_manifest.json` | `agent4_run_manifest` | Agent5-V2 源模型和运行追踪 |

Markdown 固定顺序：

```text
## 1. 报告摘要
## 2. 核心灾情指标
## 3. 分区评估结果
## 4. 证据支撑与一致性校验
## 5. 证据局限与不可下结论事项
```

前端必须把 `excluded_claims` 作为“被排除结论”展示，不能混入核心灾情指标或最终结论。

---

## 8. 前端页面结构

### 任务详情

展示：

- `job_id`
- `sample_id`
- `pipeline_version`
- 总体状态
- 队列位置
- Agent1～Agent4 状态、耗时和错误
- 已生成成果数量

### 结果分析

建议标签：

1. 原图对比
2. 建筑损伤
3. 道路影响
4. 融合证据
5. 核心指标
6. 英文描述

### 证据校验

- 左侧显示 Agent2 原始英文描述。
- 中间显示原子 Claims。
- 右侧显示状态、证据引用、理由和建议修正。
- 提供状态筛选。
- `unsupported` 和 `contradicted` 使用明显风险样式。
- `exaggerated` 显示原文和降级表述。

### 报告中心

- 中文正式报告预览。
- 人工复核提示。
- 证据追踪入口。
- Markdown、JSON、可选 DOCX 下载。

---

## 9. HTTP API 建议

### 创建任务

```http
POST /api/v1/jobs
Content-Type: multipart/form-data
```

字段：

```text
pre_image
post_image
sample_id（固定数据集时传入，用户上传时可不传）
pipeline_version
```

响应：

```json
{
  "job_id": "job_20260729_0001",
  "sample_id": "PAKISTAN-FLOODING_001517",
  "pipeline_version": "competition-four-agent-v1",
  "status": "queued",
  "queue_position": 1
}
```

### 查询状态

```http
GET /api/v1/jobs/{job_id}
```

```json
{
  "job_id": "job_20260729_0001",
  "sample_id": "PAKISTAN-FLOODING_001517",
  "status": "running",
  "current_capability": "evidence_verification",
  "queue_position": 0,
  "agents": [
    {
      "agent_code": "agent1",
      "capability": "visual_evidence",
      "display_name": "时空视觉证据感知智能体",
      "status": "succeeded",
      "started_at": "2026-07-29T10:00:00+08:00",
      "finished_at": "2026-07-29T10:01:32+08:00",
      "error": null
    }
  ]
}
```

### 查询归一化结果

```http
GET /api/v1/jobs/{job_id}/result
```

```json
{
  "job_id": "job_20260729_0001",
  "sample_id": "PAKISTAN-FLOODING_001517",
  "status": "completed",
  "inputs": {
    "pre_image_url": "/api/v1/artifacts/art_pre/content",
    "post_image_url": "/api/v1/artifacts/art_post/content"
  },
  "visual_evidence": {
    "building_summary": {
      "total_buildings": 42,
      "damaged_buildings": 13,
      "damage_ratio": 0.3095,
      "damage_distribution": {
        "no_damage": 29,
        "minor": 5,
        "severe": 6,
        "destroyed": 2
      }
    },
    "road_summary": {
      "affected_ratio": 0.18,
      "wording_level": "suspected_impact"
    },
    "scene_risk_level": "high",
    "artifacts": []
  },
  "change_description": {
    "language": "en",
    "description": "...",
    "verification_status": "verified"
  },
  "verification": {
    "overall_status": "partially_supported",
    "atomic_claims": [],
    "verified_description_en": "..."
  },
  "report": {
    "language": "zh-CN",
    "title": "遥感灾情评估报告",
    "manual_review": {
      "required": true,
      "reasons": [],
      "note": "..."
    },
    "artifact_ids": []
  }
}
```

### 获取成果文件

```http
GET /api/v1/jobs/{job_id}/artifacts
GET /api/v1/artifacts/{artifact_id}/content
```

Artifact：

```json
{
  "artifact_id": "art_fused_overlay",
  "artifact_type": "fused_overlay",
  "file_name": "fused_overlay.png",
  "mime_type": "image/png",
  "url": "/api/v1/artifacts/art_fused_overlay/content",
  "preview_url": "/api/v1/artifacts/art_fused_overlay/content"
}
```

API 不返回 Agent 本地路径。

---

## 10. 部分成功处理

### Agent1 成功、Agent2 失败

- 展示建筑、道路、融合图和场景统计。
- 英文描述区域显示失败原因。
- Agent3、Agent4 标记为 `skipped`。
- 总体状态为 `partial_success`。

### Agent1 失败、Agent2 成功

- 展示灾前/灾后图和未校验英文描述。
- Agent3 因缺少客观证据标记为 `skipped`。
- Agent4 不生成正式可信报告。
- 总体状态为 `partial_success`。

### Agent3 失败

- 保留 Agent1 和 Agent2 结果。
- Agent2 描述标记为“尚未经过证据校验”。
- Agent4 不生成正式可信报告，或仅生成明确标记为草稿的非正式报告。

### Agent4 失败

- 保留 Agent1～Agent3 全部结果。
- 前端仍可展示校验后的英文描述和 Claims。
- 报告区域显示失败原因和重试入口。

---

## 11. 上传与安全规则

前端预校验：

- 文件扩展名和 MIME 类型。
- 文件体积。
- 两张图片是否都存在。
- 浏览器可读取格式时检查宽高一致。

后端强制校验：

- 文件能否真实解码。
- 文件签名是否与声明类型一致。
- 尺寸是否一致。
- 文件是否超过限制。
- 是否包含非法路径或文件名。

错误码至少包括：

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
```

---

## 12. 前端当前代码调整清单

在正式联调前需要调整：

1. 把当前五 Agent Mock 流水线改为四 Agent 比赛流水线。
2. 把当前五级建筑损伤图例改为背景加四种建筑状态。
3. 增加道路影响结果页面。
4. 增加 `partially_supported` 和 `contradicted` 校验状态。
5. 将人工复核标志从 Agent3 校验逻辑中分离，放到 Agent4 报告区域。
6. 同时展示 `job_id` 和 `sample_id`。
7. 增加 `pipeline_version` 和 `capability`。
8. 增加 Agent2 未校验提示。
9. 增加 Agent 失败、跳过和 `partial_success` 页面状态。
10. 将成果图片改为 Artifact URL。
11. 核心统计从“像素数量”改为真实的建筑实例数量，并单独保留像素级调试信息。
12. 使用 `EARTHQUAKE-TURKEY_003679` 建立第一套真实演示 Mock。

这些调整应在接口字段讨论确认后逐项实施，避免再次依赖错误的 Agent 编号。
