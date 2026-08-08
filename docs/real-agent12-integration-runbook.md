# Agent1+Agent2 真实联调操作手册

> 当前范围：总控 FastAPI、本地 SQLite、Agent1 四模型和 Agent2 Qwen2.5-VL+LoRA。
> Agent3/4 尚未进入任务编排，不在本次验收范围内。

## 1. 当前电脑预检结论

2026-08-08 的本机检查结果：

- NVIDIA RTX 5060 Laptop GPU（8GB）可识别。
- 仓库内置的 `EARTHQUAKE-TURKEY_003679` 灾前/灾后图均为 512×512，可作为首条联调样本。
- 当前电脑尚未配置 Agent1 四个权重、Qwen2.5-VL 基础模型和 Agent2 LoRA。
- 当前轻量 `.venv` 只用于 FastAPI 与测试，不包含 PyTorch、Transformers 等模型依赖。
- 在隔离临时目录完成了无模型链路验证：任务可创建、排队、失败、返回脱敏错误，并正确进入任务列表与首页统计。

因此，源码和接口链路已具备联调条件；真实模型推理必须先从模型负责人处取得外部模型资产。

## 2. 必须准备的外部文件

模型文件不得提交到 Git。建议统一放在仓库外的 `<MODEL_ROOT>`：

```text
<MODEL_ROOT>/
├── agent1/
│   ├── building_unet_medium_best.pth
│   ├── damage_unet_7ch_best.pth
│   ├── road_unet_best.pth
│   └── road_status_attresunet7ch_best.pth
└── agent2/
    ├── Qwen2.5-VL-7B-Instruct/
    │   ├── config.json
    │   ├── *.safetensors
    │   └── tokenizer/processor 文件
    └── agent2-lora/
        ├── adapter_config.json
        └── adapter_model.safetensors
```

Agent1 权重的文件名、大小和 SHA-256 应与
`backend/agents/agent1/docs/model-card.md` 一致。Agent2 基础模型与 LoRA 元数据应与
`backend/agents/agent2/docs/model-card.md` 一致。

## 3. 创建模型运行环境

不要把模型依赖装进轻量测试环境。建议单独建立模型环境，并安装与显卡驱动匹配的 CUDA 版 PyTorch：

```powershell
python -m venv .venv-model
.\.venv-model\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
python -m pip install -r backend\agents\agent1\requirements.txt
python -m pip install -r backend\agents\agent2\requirements.txt
```

PyTorch 的 CUDA 安装命令应按模型电脑的 CUDA/驱动版本选择。8GB 笔记本显卡运行
7B 视觉语言模型尚未完成实测，可能需要 CPU offload；正式演示优先使用已验证的
RTX 4090/5090 模型电脑。

## 4. 配置本机环境变量

复制模板但不要提交生成的 `.env`：

```powershell
Copy-Item backend\.env.example backend\.env
```

将 `backend/.env` 中六个模型路径改为真实位置：

```text
AGENT1_BUILDING_MODEL_PATH=<MODEL_ROOT>/agent1/building_unet_medium_best.pth
AGENT1_DAMAGE_MODEL_PATH=<MODEL_ROOT>/agent1/damage_unet_7ch_best.pth
AGENT1_ROAD_BINARY_MODEL_PATH=<MODEL_ROOT>/agent1/road_unet_best.pth
AGENT1_ROAD_STATUS_MODEL_PATH=<MODEL_ROOT>/agent1/road_status_attresunet7ch_best.pth
AGENT2_BASE_MODEL_PATH=<MODEL_ROOT>/agent2/Qwen2.5-VL-7B-Instruct
AGENT2_LORA_PATH=<MODEL_ROOT>/agent2/agent2-lora
```

然后执行一键预检：

```powershell
.\.venv-model\Scripts\python.exe backend\scripts\preflight_real_integration.py `
  --env-file backend\.env
```

所有项目均为 `PASS` 后才启动真实服务。

## 5. 启动顺序

后端终端：

```powershell
.\.venv-model\Scripts\python.exe -m uvicorn backend.app.main:app `
  --host 0.0.0.0 --port 8000 --workers 1 --env-file backend\.env
```

只使用一个 worker，避免重复加载模型和同时占用 GPU。

前端根目录新建未跟踪的 `.env.local`：

```text
VITE_USE_MOCK=false
VITE_API_BASE_URL=http://127.0.0.1:8000
```

前端终端：

```powershell
npm run dev
```

跨电脑联调时，将 `127.0.0.1` 改为模型电脑局域网 IPv4，并把前端实际地址加入
后端 `FRONTEND_ORIGINS`。

## 6. 首条真实任务

默认预检样本位于：

```text
public/mock-data/competition-four-agent-v1/EARTHQUAKE-TURKEY_003679/artifacts/
```

提交时使用：

- `pre_image.png`
- `post_image.png`
- `sample_id=EARTHQUAKE-TURKEY_003679-REAL-01`

不要使用成果叠加图代替输入原图。

## 7. 验收标准

1. `/api/v1/health` 中 Agent1/2 的 `configured=true`，队列 worker 正常。
2. 上传返回 HTTP 202 和唯一 `job_id`。
3. 状态按队列、Agent1、Agent2、整理结果顺序推进，不同时占用两份 GPU 模型。
4. 终态为 `succeeded` 或可解释的 `partial_success`。
5. Agent1 返回核心统计、`review_flags` 和实际 Artifact URL。
6. Agent2 返回英文 `description` 与非空 `claim_list`，并保持 `unverified`。
7. Agent3/4 显示“待接入/跳过”，`four_agent_pipeline_complete=false`。
8. 首页和任务中心能从 SQLite 重新打开该真实任务。
9. 所有响应不包含模型电脑绝对路径、Token、权重内容或原始异常堆栈。

## 8. 失败处理

- 预检缺模型：向模型负责人索取对应文件，不要从代码仓库下载未知权重。
- CUDA 显存不足：降低 Agent2 GPU memory 配额并启用 CPU offload，或迁移到 4090/5090。
- 单个 Agent 失败：保留另一个 Agent 的结果，页面显示 `partial_success` 和脱敏错误。
- 两个 Agent 均失败：页面显示 `failed`；检查后端终端日志，不把完整堆栈返回浏览器。
- 图片被拒绝：检查 PNG/JPEG、25 MiB、1亿像素和双图尺寸一致性。
