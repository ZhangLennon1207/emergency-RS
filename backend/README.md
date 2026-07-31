# 后端与智能体集成区

本目录用于汇总四个智能体代码和统一 FastAPI 调度层。当前阶段采用“一个仓库、独立模块、统一接口、集中集成”的方式协作。

## 目录职责

```text
backend/
├── agents/                 # 各成员独立提交区
│   ├── common/             # 仅放跨Agent共享的小型工具
│   ├── agent1/             # 视觉证据、损伤量化与复核标志
│   ├── agent2/             # 英文灾情变化描述
│   ├── agent3/             # 证据可信校验
│   └── agent4/             # 可信报告生成
├── app/
│   ├── api/                # FastAPI接口
│   ├── orchestration/      # 四Agent流水线编排
│   ├── schemas/            # Pydantic请求/响应模型
│   └── services/           # 任务、文件、存储等公共服务
├── scripts/                # 启动、数据检查和集成辅助脚本
├── tests/                  # 跨模块集成测试
└── .env.example            # 环境变量模板，禁止提交真实.env
```

## 基本原则

1. Agent成员默认只修改自己的 `backend/agents/agentX/`。
2. `backend/app/` 由后端集成人员维护，Agent成员不要自行修改公共接口。
3. 公共字段变更必须先更新 `contracts/` 和 `docs/api-contract.md`。
4. 模型权重、数据集、虚拟环境、运行输出和密钥禁止提交。
5. 每个Agent必须提供依赖、运行说明、最小样例和适配入口。

详细操作见 [团队协作与Agent交付指南](../docs/team-collaboration-guide.md)。
