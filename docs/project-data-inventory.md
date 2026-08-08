# 项目数据与资产清单

## 1. 扫描范围

本清单基于 `E:\遥感大创` 下现有文件整理，覆盖：

- React 前端仓库
- Agent1 固定20条输出
- Agent2 固定20条输出
- Agent2 灾前/灾后配对消融实验
- Agent1～Agent4 交接文档

---

## 2. 前端和后端仓库

路径：

```text
E:\遥感大创\emergency-RS\emergency-RS
```

当前状态：

- React 多页面前端已存在。
- 前端目前使用 Mock 数据。
- `backend/` 只有目录和空的 `__init__.py`，尚无 FastAPI、数据库或 Agent 调用实现。
- `docs/` 已包含前端方案、全过程方案和 Agent 对接设计。

---

## 3. Agent1 固定20条输出

路径：

```text
E:\遥感大创\交接数据\交接数据\agent1_random20_seed20260707
```

统计：

- 样本数：20
- 成功数：20
- 失败数：0
- 文件数：543
- 总体积：约206.4MB

每条样本包含：

```text
input/
building/
road/
fusion/
for_agent3/
for_agent4/
run_manifest.json
```

可直接用于前端的主要内容：

- 灾前图、灾后图
- 建筑 Mask
- 建筑实例 Mask
- 四种建筑状态彩色图
- 道路状态图
- 道路受影响概率图
- 融合类别图
- 灾后叠加图
- 六宫格视觉对比图
- 建筑和道路核心统计
- 建筑实例证据和 bbox
- 模型预测置信度
- 人工复核标志与原因

---

## 4. Agent2 固定20条输出

路径：

```text
E:\遥感大创\交接数据\交接数据\agent2_same20_seed20260707
```

统计：

- 样本数：20
- 成功数：20
- 失败数：0
- 文件数：82
- 总体积：约0.2MB

Agent1 和 Agent2 的 `sample_id` 集合完全一致，没有缺失或额外样本。

每条样本包含：

```text
agent2_output.json
raw_response.txt
prompt_snapshot.txt
run_manifest.json
```

正式网页应读取 `agent2_output.json` 的英文 `description`，并在 Agent3 完成前标记为未经证据校验。

---

## 5. 真实 JSON Schema 版本

已抽查 `PAKISTAN-FLOODING_001517` 和 `EARTHQUAKE-TURKEY_003679`。

| 文件 | schema_version |
| --- | --- |
| `evidence_ledger_core.json` | `2.1` |
| `agent1_report_summary.json` | `1.1` |
| `review_flags.json` | 历史样例 `1.1`；当前路由语义修正版 `1.2` |
| `agent2_output.json` | 历史样例 `1.0`；当前 Adapter `1.1` |

### evidence_ledger_core.json

顶层字段：

```text
schema_version
agent
sample_id
input_images
building_evidence
road_evidence
derived_assessment
evidence_images
output_files
model_metadata
confidence_metadata
```

`building_evidence` 包含：

```text
total_buildings
damaged_buildings
damage_ratio
damage_distribution
damage_distribution_ratio
damage_presence_confidence_summary
damage_level_confidence_summary
building_instances
```

单个建筑实例包含：

```text
evidence_id
building_id
area_pixels
bbox
is_damaged
damage_presence_confidence
damage_presence_confidence_level
damage_level_id
damage_level
damage_level_zh
damage_level_confidence
damage_level_confidence_level
confidence_source
confidence_is_calibrated
```

### agent1_report_summary.json

顶层字段：

```text
schema_version
sample_id
building_summary
road_summary
overall_assessment
evidence_images
```

### review_flags.json

当前 `1.2` 版本的正式接收方是 `backend_review_display`。历史目录名
`for_agent4/` 仅为兼容已有产物而保留；该文件不得输入 Agent2、Agent3 或
Agent4 模型。

顶层字段：

```text
schema_version
sample_id
review_required
uncertainty_summary
review_reasons
report_instruction
routing
```

### agent2_output.json

顶层字段：

```text
schema_version
agent_id
agent_name
sample_id
language
description
input_images
routing
```

---

## 6. 推荐标准演示样本

推荐：

```text
EARTHQUAKE-TURKEY_003679
```

选择理由：

- 建筑总数18栋。
- 受损建筑10栋。
- 建筑受损比例约55.56%。
- 疑似受影响道路比例约70.95%。
- 建筑、道路和场景风险均为 `high`。
- 7栋建筑处于是否受损的临界置信度区间。
- `review_required=true`。
- Agent2 描述中出现“可能洪水”等推断，适合展示 Agent3 的逐条证据校验。
- 六宫格视觉对比图清晰，适合网页和比赛演示。

该样本可以完整展示：

```text
原始影像
→ Agent1 视觉证据
→ Agent2 可能存在偏差的英文描述
→ Agent3 Claims 校验
→ Agent4 中文可信报告和人工复核提示
```

备用无损样本：

```text
PAKISTAN-FLOODING_001517
```

该样本中 Agent1 判断3栋建筑均无明显损伤、道路未受影响，但 Agent2 描述了建筑坍塌和可能洪水，也适合展示视觉语言模型幻觉。

---

## 7. Agent2 配对消融实验

路径：

```text
E:\遥感大创\pair_ablation_ebdtest20_seed20260728(1)\pair_ablation_ebdtest20_seed20260728
```

统计：

- 固定样本：20
- paired：20条
- post-only：20条
- mismatched-pre：100条
- 总推理记录：140
- 成功：140
- 失败：0
- 文件数：616
- 总体积：约73.2MB

可复用资产：

- 灾前/灾后正确配对图
- 错配灾前图
- 140条英文输出
- 自动拆分 Claims
- paired、post-only 和 mismatched-pre 对比指标
- 盲审页面和审核表

重要限制：

- `qualification_status=pending_review`
- 当前审核人数为0
- `strict_conclusion_allowed=false`
- 自动结果显示 Agent2 存在明显的 flood 措辞偏置和灾种判断不稳定
- 不能宣称该实验已经严格证明模型正确利用灾前图

该实验适合：

- Agent3 原子 Claims 输入测试
- 前端“实验评估”或“可信性分析”扩展页面
- 比赛材料中的模型局限性说明

暂不建议把它直接混入在线任务数据库。

---

## 8. 当前缺失内容

项目文件夹中尚未发现：

- Agent1 推理源代码
- Agent2 推理源代码
- 当前 Agent3（源版本 Agent4-V4）的完整后端包和实际任务输出
- 当前 Agent4（源版本 Agent5-V2）的完整后端包和实际任务输出
- PyTorch 模型权重
- FastAPI 后端实现
- PostgreSQL 数据库迁移
- MinIO 配置
- GPU Worker 或任务队列代码

现有 JSON 中包含原开发电脑的绝对路径和模型路径。后端接入时必须转换为当前存储系统的 `artifact_id` 和 URL，不能原样返回前端。

### 最新 Agent3/4 格式规范

路径：

```text
E:\遥感大创\frontend_codex_handoff_agent4_agent5_json
```

已提供：

- Agent4-V4 证据校验格式、五类 `support_status` 和评估摘要。
- `check_result` 与 `verified_evidence_package` 字段规范。
- Agent5-V2 的 `platform_report_json` 和固定五段式 Markdown 规范。
- 报告安全边界、前端卡片和排除项展示规则。

在当前四智能体流水线中映射为：

```text
当前 Agent3 evidence_verification ← 源版本 Agent4-V4
当前 Agent4 report_generation     ← 源版本 Agent5-V2
```

这批文件属于格式规范，不是某个真实任务的 Agent3/4 输出。因此首套真实 Mock 中的 `verification` 和 `report` 仍保持 `null`，不得把规范示例伪装成模型运行结果。

---

## 9. 现有前端与文档的一致性

当前 React 页面已经具备可用的多页面框架，但代码仍沿用早期五智能体 Mock：

- `taskService.js` 把量化评估、描述生成、证据校验和报告生成编号为 Agent2～Agent5。
- 损伤图例仍是五个建筑损伤等级。
- 量化区域主要统计像素数，没有使用真实建筑实例数量。
- 证据页把校验能力显示为 Agent4，报告页显示为 Agent5。
- 尚未展示道路状态、`sample_id`、Artifact URL、部分成功和单 Agent 错误。

因此现有前端适合作为页面与样式基线，但 Mock 数据层和任务详情页必须按当前四智能体流水线重构。

文档使用优先级：

1. `docs/frontend-agent-integration.md`：当前前端联调依据。
2. `docs/full-process-plan.md`：当前全过程执行依据。
3. `docs/project-data-inventory.md`：真实数据和可复用资产依据。
4. `docs/frontend-plan.md`：页面工程化参考，部分“当前状态”已过时。
5. `docs/backend-plan.md`：早期通用后端设想，只参考基础设施，不作为当前 Agent 接口依据。

此外，依赖缓存 `.npm-cache/` 和父目录 `.pnpm-store/` 不是项目源代码，不应进入 Git 或作为交付资产。

---

## 10. 下一步资产整理建议

1. 将 `EARTHQUAKE-TURKEY_003679` 作为第一套前端真实 Mock。
2. 将该样本需要的网页图片复制到前端演示资产目录，保留来源说明。
3. 基于真实 JSON 编写 `docs/api-contract.md`。
4. 建立“Agent 原始字段 → 后端归一化字段”映射。
5. 等 Agent3/4 代码和正式输出到位后补充对应 Schema。
6. 不把206MB全量 Agent1 输出直接提交到前端仓库。
