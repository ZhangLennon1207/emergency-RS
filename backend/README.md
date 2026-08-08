# 后端与智能体集成区

本目录包含统一 FastAPI Job API、Agent1/2 本地 adapter、任务/Artifact 运行时管理和无模型测试。当前可验证范围是 **Agent1 + Agent2 本地集成**；Agent3/4 仍未接入真实代码或同学电脑上的服务。

## 当前真实状态

- Agent1：四个指定权重已在迁移后源码上完成严格加载和单样本 GPU 回归。
- Agent2：Qwen2.5-VL + 指定 LoRA 已在迁移后 adapter 上完成单样本 GPU 回归；模型权重和 Prompt 不变，Adapter 额外生成向后兼容的 `claim_list`。
- FastAPI：Job 创建、查询、上传校验、SQLite 队列、adapter 调度和 Artifact 下载已通过模拟 adapter 测试。
- React 前端：已有兼容的 Job API 客户端，但尚未与本后端和真实模型完成实际联调。
- Agent3/4：跨电脑 HTTP 契约和客户端已进入准备阶段，但尚未接入编排器；响应中仍固定为 `skipped`，`verification` 和 `report` 固定为 `null`，不得据此声明四智能体全流程完成。

## 目录职责

```text
backend/
├── agents/                 # Agent1～4 独立模块；当前真实源码为 Agent1/2
├── app/
│   ├── main.py             # FastAPI Job/Artifact API
│   ├── config.py           # 环境配置，不含个人路径
│   ├── db.py               # 本地 SQLite 任务队列
│   ├── artifacts.py        # 相对路径索引与越界防护
│   ├── clients/            # Agent3/4 远程 HTTP 客户端（尚未接入编排器）
│   ├── integration/        # 跨 Agent 标识符与请求契约
│   └── orchestration/      # Agent1/2 adapter 编排
├── tests/                  # 不依赖权重/CUDA 的集成测试
├── scripts/                # 仓库安全检查
├── requirements.txt
└── .env.example
```

运行目录默认是 `backend/runtime/`，已被 Git 忽略。SQLite、日志、上传影像、模型输出和 offload 均不得提交。

## 配置与启动

复制 `backend/.env.example` 的变量到本机私有 `.env` 或启动环境，并将模型路径改成本机真实位置。不要把真实 `.env` 提交到 Git。

后端进程需能导入 Agent1、Agent2 及其依赖。安装轻量 API 依赖后，再按模型主机环境安装两个 Agent 的依赖：

```powershell
python -m pip install -r backend/requirements.txt
python -m pip install -r backend/agents/agent1/requirements.txt
python -m pip install -r backend/agents/agent2/requirements.txt
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

只使用一个 worker，避免每个进程重复加载大模型。前端本地环境配置 `VITE_API_BASE_URL=http://127.0.0.1:8000` 和 `VITE_USE_MOCK=false` 后，才能开始实际联调。

Agent3/4 的预备配置为 `AGENT34_BASE_URL`、`AGENT34_SHARED_TOKEN`、`AGENT34_CONNECT_TIMEOUT_SECONDS` 和 `AGENT34_READ_TIMEOUT_SECONDS`。配置这些变量只代表远程地址已填写；在 `evidence_list` 映射经真实样例验证、编排器正式接入并完成真实回归前，健康接口仍不得把 Agent3/4 声明为已集成。跨电脑细节见 `docs/agent34-http-integration-contract.md`。

前端开发应以 `docs/frontend-backend-current-contract.md` 为当前可执行接口基线；
该文档区分了已经由 FastAPI 实际返回的字段和仍处于待接入状态的 Agent3/4
结果槽位。

## API

```text
POST /api/v1/jobs
GET  /api/v1/jobs/{job_id}
GET  /api/v1/jobs/{job_id}/result
GET  /api/v1/jobs/{job_id}/artifacts/{artifact_key}
GET  /api/v1/health
```

Agent1/2 都成功时，任务状态为 `succeeded`，含义仅是当前双智能体范围成功。响应同时返回：

```json
{
  "scope": "agent1_agent2_local_only",
  "four_agent_pipeline_complete": false,
  "verification": null,
  "report": null
}
```

## 无模型测试

```powershell
python -m pytest backend/tests backend/agents/agent1/tests backend/agents/agent2/tests
python backend/scripts/check_repo_safety.py
```

测试使用临时目录、微型图片和模拟 adapter，不访问数据集、权重、CUDA 或同学电脑。
