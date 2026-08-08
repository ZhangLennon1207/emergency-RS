# Agent3 / Agent4 跨电脑 HTTP 联调实施要求

> 版本：`agent34-http-1.0-draft`
> 日期：2026-08-08
> 用途：发给魏松辰，作为 Agent3/4 服务实现、参数设置和首轮联调依据。
> 状态：接口骨架已冻结；`evidence_list` 内部字段等待 3～5 条真实脱敏样例后最终确认。

## 1. 最终命名

| 当前系统 | capability | 历史模型版本 |
| --- | --- | --- |
| Agent3 | `evidence_verification` | Agent4-V4 |
| Agent4 | `report_generation` | Agent5-V2 |

新 API、GitHub 目录、日志和前端统一使用 Agent3/Agent4。历史配置、权重目录和实验记录可以保留 Agent4/Agent5 文件名，通过 `source_version` 追踪，不做全局重命名。

## 2. 魏松辰需要提交的 GitHub 内容

分支：`feature/agent34-service-weisongchen`。必须从最新 `main` 创建。

```text
backend/
├── agents/
│   ├── agent3/
│   │   ├── adapter.py
│   │   ├── runtime/                  # Agent4-V4 稳定源码，不含权重
│   │   ├── prompts/evidence_verification.txt
│   │   ├── schemas/
│   │   ├── model_metadata.json
│   │   └── tests/
│   └── agent4/
│       ├── adapter.py
│       ├── runtime/                  # Agent5-V2 稳定源码，不含权重
│       ├── prompts/report_generation.txt
│       ├── schemas/
│       ├── model_metadata.json
│       └── tests/
└── services/agent34_service/
    ├── __init__.py
    ├── main.py
    ├── config.py
    ├── schemas.py
    ├── auth.py
    ├── runtime_manager.py
    └── tests/
```

Agent3 必须保留：

- `postprocess_minimal_check.py`
- `validate_minimal_check.py`
- `wrap_check_result.py`
- `build_verified_package.py`

Agent4 必须保留：

- `normalize_agent5_output.py`
- 实际稳定 Prompt
- 固定五章节重建及 rejected/high-risk 检查

不得提交：基础模型、`*.safetensors`、LoRA 权重、数据集、逐样本原始运行目录、密钥、缓存和个人绝对路径。

## 3. 魏松辰模型电脑的环境变量

`$PROJECT` 代表魏松辰当前已验证的 AutoDL 项目根目录。下面路径必须用实际存在的 POSIX 路径替换，不能把示例文本原样运行。

```bash
export PROJECT=/root/autodl-tmp/llama_factory_workspace

export AGENT34_BASE_MODEL_PATH=<Qwen2.5-VL-7B-Instruct实际目录>
export AGENT3_PREDICT_CONFIG=$PROJECT/configs/current/agent3/agent3_v4_baseline_predict.yaml
export AGENT3_LORA_PATH=$PROJECT/models_current/agent3_v4_baseline_lora
export AGENT4_PREDICT_CONFIG=$PROJECT/configs/current/agent4/agent4_v2_baseline_predict.yaml
export AGENT4_LORA_PATH=$PROJECT/models_current/agent4_v2_baseline_lora
export AGENT34_WORK_ROOT=$PROJECT/runtime/agent34_service

export AGENT34_SHARED_TOKEN=<双方私下交换的高强度随机Token>
export AGENT34_MAX_CONCURRENCY=1
export AGENT34_PORT=8100
```

Token 只能私下传递，写入未跟踪的 `.env` 或 shell 环境，不得发到群聊、文档、GitHub、日志和截图。

### 3.1 推荐：AutoDL/异地电脑使用 SSH 隧道

魏松辰服务只监听远端本机：

```bash
export AGENT34_HOST=127.0.0.1
python -m uvicorn backend.services.agent34_service.main:app \
  --host 127.0.0.1 --port 8100 --workers 1
```

AutigerBai 的 Windows 电脑建立隧道：

```powershell
ssh -N -L 18100:127.0.0.1:8100 <autodl-user>@<autodl-host> -p <ssh-port>
```

本地后端设置：

```text
AGENT34_BASE_URL=http://127.0.0.1:18100
AGENT34_SHARED_TOKEN=<与魏松辰相同的Token>
AGENT34_CONNECT_TIMEOUT_SECONDS=5
AGENT34_READ_TIMEOUT_SECONDS=900
```

`900` 秒是首次联调临时值；完成冷启动和 warm benchmark 后再缩短。

### 3.2 仅在同一可信局域网使用直接连接

魏松辰：

```bash
python -m uvicorn backend.services.agent34_service.main:app \
  --host 0.0.0.0 --port 8100 --workers 1
```

AutigerBai：

```text
AGENT34_BASE_URL=http://<WEI_LAN_IP>:8100
```

只允许专用/私人网络防火墙规则。不要把无 TLS 的 8100 端口直接暴露到公网。

## 4. 冻结接口

```text
GET  /api/v1/health
POST /api/v1/agent3/verify
POST /api/v1/agent4/report
```

所有 POST 请求使用：

```http
Authorization: Bearer <AGENT34_SHARED_TOKEN>
```

历史 `/api/v1/agent4/check` 和 `/api/v1/agent5/report` 只能作为临时兼容别名；总控后端不会使用历史路径。

### 4.1 GET /api/v1/health

响应只返回服务状态，不泄露路径和 Token：

```json
{
  "status": "ok",
  "service_version": "agent34-service-1.0",
  "agent3_ready": true,
  "agent4_ready": true,
  "max_concurrency": 1
}
```

### 4.2 POST /api/v1/agent3/verify

使用 `multipart/form-data`，字段固定为：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `payload` | `application/json` 文件部分 | 标识符、版本、evidence_list、claim_list |
| `pre_image` | 图片文件 | 灾前图 |
| `post_image` | 图片文件 | 灾后图 |

`payload`：

```json
{
  "contract_version": "agent34-http-1.0",
  "pipeline_version": "competition-four-agent-v1",
  "job_id": "job-001",
  "sample_id": "sample-001",
  "source_schema_versions": {
    "evidence_list": "待真实样例冻结",
    "claim_list": "1.1"
  },
  "evidence_list": [],
  "claim_list": [
    {
      "claim_id": "C001",
      "claim": "Several buildings in the center appear damaged.",
      "language": "en",
      "related_evidence_ids": []
    }
  ]
}
```

服务行为：

1. 校验双图可解码且成对。
2. 校验 `job_id`、`sample_id`、claim/evidence ID 唯一。
3. HTTP 一次接收完整 `claim_list`。
4. Runtime 内部按 Agent4-V4 稳定逻辑逐 claim 调用。
5. 同一场景内不得为每条 claim 重新加载一次 7B 基座模型。
6. 保存每条 raw output，再运行后处理、校验和聚合。
7. HTTP 只返回 normalized JSON。

响应：

```json
{
  "contract_version": "agent34-http-1.0",
  "pipeline_version": "competition-four-agent-v1",
  "job_id": "job-001",
  "sample_id": "sample-001",
  "agent_code": "agent3",
  "capability": "evidence_verification",
  "source_version": "Agent4-V4",
  "runtime_version": "agent3-v4-baseline",
  "status": "succeeded",
  "check_result": {},
  "verified_evidence_package": {}
}
```

### 4.3 POST /api/v1/agent4/report

请求为普通 JSON：

```json
{
  "contract_version": "agent34-http-1.0",
  "pipeline_version": "competition-four-agent-v1",
  "job_id": "job-001",
  "sample_id": "sample-001",
  "verified_evidence_package": {}
}
```

Agent4 模型的唯一事实输入是 `verified_evidence_package`。`review_flags` 由总控后端在展示层附加，不输入 Agent4 模型。

响应：

```json
{
  "contract_version": "agent34-http-1.0",
  "pipeline_version": "competition-four-agent-v1",
  "job_id": "job-001",
  "sample_id": "sample-001",
  "agent_code": "agent4",
  "capability": "report_generation",
  "source_version": "Agent5-V2",
  "runtime_version": "agent4-v2-baseline",
  "status": "succeeded",
  "platform_report_json": {},
  "markdown_report": "## 1. 报告摘要\n..."
}
```

Markdown 标题固定为：

```text
## 1. 报告摘要
## 2. 核心灾情指标
## 3. 分区评估结果
## 4. 证据支撑与一致性校验
## 5. 证据局限与不可下结论事项
```

## 5. 标识符规则

- `job_id`：总控后端一次任务运行，由 AutigerBai 后端生成。
- `sample_id`：遥感场景身份。
- `claim_id`：Agent2 Adapter 生成的稳定 claim 编号。
- 历史 `task_id=sample_id_claim_id` 只能在魏松辰 Runtime 内部使用，不出现在正式 HTTP 契约。
- 返回响应必须原样回传请求中的 `job_id` 和 `sample_id`。

## 6. 错误响应

统一结构：

```json
{
  "error": {
    "code": "EMPTY_CLAIM_LIST",
    "message": "claim_list must not be empty",
    "retryable": false
  }
}
```

至少实现：

| code | HTTP | retryable |
| --- | ---: | --- |
| `UNAUTHORIZED` | 401 | false |
| `INVALID_REQUEST` | 422 | false |
| `IMAGE_DECODE_FAILED` | 422 | false |
| `EMPTY_CLAIM_LIST` | 422 | false |
| `UNKNOWN_EVIDENCE_ID` | 422 | false |
| `MODEL_NOT_READY` | 503 | true |
| `SERVICE_BUSY` | 503 | true |
| `MODEL_TIMEOUT` | 504 | true |
| `MODEL_OUTPUT_INVALID` | 502 | 可按情况 |
| `INTERNAL_ERROR` | 500 | true |

错误内容不得包含模型路径、输入路径、Token 或完整异常堆栈。

## 7. 单 GPU 运行要求

- `uvicorn --workers 1`。
- 服务层并发上限为 1；其他请求排队或返回 `SERVICE_BUSY`。
- 优先实现基座模型常驻和两个 LoRA Adapter 切换。
- 如果暂时只能用 CLI，Agent3 一次 CLI 至少处理完整 claim_list，不能每条 claim 冷启动一次。
- 分别记录 cold start、warm mean/median/p95 和 peak VRAM。
- Agent3 记录单 claim 与 5 claims 总耗时；Agent4 记录单报告耗时。

## 8. 魏松辰必须提供的 evidence_list 样例

请提供 3～5 套脱敏 JSON，不要提供影像或数据集：

1. 建筑变化为主的一套。
2. 道路影响为主的一套。
3. 建筑+道路混合的一套。
4. 包含 unsupported/contradicted/exaggerated 的一套（如有）。
5. 包含 partially_supported 的一套（如有）。

每套最好包括：

```text
原始 Agent1 evidence_ledger_core.json
→ 实际送入历史 Agent4-V4 的 evidence_list
→ claim_list
→ minimal_check raw/normalized
→ check_result
→ verified_evidence_package
```

可以替换 `sample_id`、路径和地理标识，但必须保留完整字段、类型、空值和嵌套关系。收到后由 AutigerBai 冻结 `evidence_mapper`；在此之前不要假定仓库现有 Agent1 ledger 与 historical evidence_list 完全同构。

## 9. 冻结前验收

- 无 GPU CI：Schema、鉴权、multipart、空 claim、重复 ID、未知 evidence_id、错误码测试通过。
- 当前 GPU：Agent3 用一套真实英文 claims 完成逐条校验。
- 当前 GPU：Agent4 用该 verified package 生成 normalized JSON 和固定五章节 Markdown。
- 记录 raw 与 normalized，但 raw 不直接返回前端。
- 输出不含绝对路径、密钥和数据集原始标识。
- 两个 Prompt、Runtime 源码和 Adapter 文件记录 SHA-256。
- 两个 `adapter_model.safetensors` 只记录文件名、字节数和 SHA-256，不提交文件。

## 10. 双方分工

### AutigerBai

- 保持 Agent2 已训练模型和 Prompt 不变。
- 在 Agent2 Adapter 后生成向后兼容的 `claim_list`。
- 根据魏松辰真实样例实现 Agent1 ledger → evidence_list 映射。
- 总控后端生成 `job_id`，上传双图，调用 Agent3/4，保存 Artifact。
- Agent3 失败时跳过 Agent4；Agent4 失败时保留 Agent1～3 结果。

### 魏松辰

- 提交 Agent3/4 稳定 Runtime、Prompt、后处理、Schema、测试和服务源码。
- 实现本文三个 HTTP 路由、Bearer Token、单 worker 和结构化错误。
- 确保 claim_list 在同一次服务请求中逐条运行并聚合。
- 提供真实脱敏 evidence_list 链路样例、环境版本、模型元数据和基准结果。
