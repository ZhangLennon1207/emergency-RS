# 鉴微（JianWei）统一命名规范

本文件是系统、论文、图表、代码文档、汇报材料和用户界面的命名单一事实来源。此前使用的四个 Agent 长名称不再作为正式名称。

## 系统名称

- 中文正式名：**鉴微：面向高危场景的证据驱动多智能体评估系统**
- 中文简称：**鉴微**
- 英文名：**JianWei**
- 英文全称：**JianWei: An Evidence-Grounded Multi-Agent Framework for High-Risk Scenario Assessment**

`Emergency-RS` 暂时仅作为 GitHub 仓库名、兼容性存储键、内部线程名等开发代号。新论文、图表、汇报和界面优先使用“鉴微 / JianWei”。

## 四个 Agent 的正式名称

| 代码标识 | 中文正式名称 | 英文正式名称 |
|---|---|---|
| `agent1` | 视觉感知智能体 | Visual Perception Agent |
| `agent2` | 变化理解智能体 | Change Understanding Agent |
| `agent3` | 证据约束核验智能体 | Evidence-Grounded Verification Agent |
| `agent4` | 报告生成智能体 | Report Generation Agent |

代码中的 `agent1`～`agent4` 是稳定机器标识，不随展示名称改变。接口需要展示名称时，应同时提供 `display_name` 和 `display_name_en`。

## 论文技术章节标题

章节标题可以按方法内容使用更具体的技术表述，例如：

- Visual Perception and Evidence Construction
- Bi-temporal Change Understanding and Claim Construction
- Claim-Level Evidence-Grounded Verification
- Structured Report Generation

这些标题描述技术步骤，不替代四个 Agent 的正式名称。

## 实现与验证范围

当前代码、模型训练、系统实现和实验验证范围是**双时相遥感灾情评估**，包括建筑与道路的分割、损伤/受影响状态评估、变化理解、Claim 级证据核验和结构化报告生成。

“面向高危场景”是系统总体定位，不表示已经在医疗、工业安全或其他高危场景完成实验。论文、答辩和产品材料不得把未来可扩展能力表述为已验证结果。
