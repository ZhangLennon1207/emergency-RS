# 后端与智能体集成区

本目录包含统一 FastAPI Job API、Agent1/2 本地 adapter、Agent3/4 远程服务客户端、跨智能体映射、任务/Artifact 管理和无模型测试。未配置 `AGENT34_BASE_URL` 与 `AGENT34_SHARED_TOKEN` 时保持 Agent1/2 本地模式；配置后按冻结契约执行四阶段远程编排。

## 当前真实状态

- Agent1：四个指定权重已在迁移后源码上完成严格加载和单样本 GPU 回归。
- Agent2：Qwen2.5-VL + 指定 LoRA 已在迁移后 adapter 上完成单样本 GPU 回归；模型权重和 Prompt 不变，Adapter 额外生成向后兼容的 `claim_list`。
- FastAPI：Job 创建、查询、上传校验、SQLite 队列、adapter 调度和 Artifact 下载已通过模拟 adapter 测试。
- React 前端：已有 Job API 客户端；新增 Agent3/4 状态和最终 V5.2/V3 字段仍需在真实后端响应上验收。
- Agent3/4：总控侧映射、multipart 客户端、失败隔离和编排代码已完成无模型回归。魏松辰真实服务尚未在本机通过 SSH 隧道联调，因此只有单次真实任务的 `four_agent_pipeline_complete=true` 才表示该任务四阶段均成功。

## 目录职责

```text
backend/
├── agents/                 # Agent1～4 独立模块；当前真实源码为 Agent1/2
├── app/
│   ├── main.py             # FastAPI Job/Artifact API
│   ├── config.py           # 环境配置，不含个人路径
│   ├── db.py               # 本地 SQLite 任务队列
│   ├── artifacts.py        # 相对路径索引与越界防护
│   ├── clients/            # Agent3/4 远程 HTTP 客户端
│   ├── integration/        # claim 类型、证据转换/关联与请求契约
│   └── orchestration/      # Agent1～4 条件编排与失败隔离
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

Agent3/4 配置为 `AGENT34_BASE_URL`、`AGENT34_SHARED_TOKEN`、`AGENT34_CONNECT_TIMEOUT_SECONDS` 和 `AGENT34_READ_TIMEOUT_SECONDS`。魏松辰服务保持监听 `127.0.0.1:8100`；建议通过 SSH 隧道映射为本机 `127.0.0.1:18100`。配置字段只表示远程编排已启用，不等于真实服务已经通过验收。跨电脑细节见 `docs/agent34-http-integration-contract.md`。

真实 Agent1/2 启动前先运行 `python backend/scripts/preflight_real_integration.py --env-file backend/.env`。模型文件准备、启动顺序和验收标准见 `docs/real-agent12-integration-runbook.md`。

前端开发应以 `docs/frontend-backend-current-contract.md` 为当前可执行接口基线；
该文档区分了已经由 FastAPI 实际返回的字段和仍处于待接入状态的 Agent3/4
结果槽位。

## API

```text
POST /api/v1/jobs
GET  /api/v1/jobs?page=1&page_size=20
GET  /api/v1/jobs/{job_id}
GET  /api/v1/jobs/{job_id}/result
GET  /api/v1/jobs/{job_id}/artifacts/{artifact_key}
GET  /api/v1/dashboard
GET  /api/v1/health
```

未配置 Agent3/4 时，Agent1/2 都成功仍返回兼容的本地范围：

```json
{
  "scope": "agent1_agent2_local_only",
  "four_agent_pipeline_complete": false,
  "verification": null,
  "report": null
}
```

配置远程服务后，总控执行 `Agent1 → Agent2 → Agent3 → Agent4`。只有四阶段都成功时返回：

```json
{
  "scope": "four_agent_remote_service",
  "pipeline_version": "competition-four-agent-v1",
  "agent34_contract_version": "agent34-http-1.0",
  "four_agent_pipeline_complete": true,
  "verification": {"verified_evidence_package": {}},
  "report": {
    "platform_report_json": {},
    "markdown_report_zh": "...",
    "markdown_report_en": "..."
  }
}
```

Agent3 失败时跳过 Agent4；Agent4 失败时保留 Agent1～3 结果并返回 `partial_success`。远程原始生成文本只保存在 Git 忽略的运行日志中，公开 Job API 返回脱敏后的结构化结果。

## 无模型测试

```powershell
python -m pytest backend/tests backend/agents/agent1/tests backend/agents/agent2/tests
python backend/scripts/check_repo_safety.py
```

测试使用临时目录、微型图片和模拟 adapter，不访问数据集、权重、CUDA 或同学电脑。
