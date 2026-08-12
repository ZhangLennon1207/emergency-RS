# Agent3/4 模型主机服务

本服务实现仓库冻结的三个路径：

- `GET /api/v1/health`
- `POST /api/v1/agent3/verify`
- `POST /api/v1/agent4/report`

所有模型调用由一个 Runtime 锁串行执行，Uvicorn 必须保持单 worker。服务仅监听
`127.0.0.1:8100`，跨电脑通过 SSH 隧道访问。

## 与仓库现有契约的适配统计

合入前仓库文本引用统计：

| 名称 | 已有引用数 | 当前处理 |
| --- | ---: | --- |
| `qualified_claims` | 7 | 模型正式字段改为 `revised_claims`，不伪造旧字段 |
| `revised_claims` | 0 | Agent3-V5.2.1 正式输出 |
| `key_findings` | 4 | 模型正式结构改为 `platform_report_json.sections.*` |
| `markdown_report` | 11 | 暂时返回中文兼容别名 |
| `markdown_report_zh/en` | 0 | Agent4-V3 正式双语输出 |
| `AGENT34_SHARED_TOKEN` | 8 | 服务采用该仓库变量名 |
| `AGENT34_API_TOKEN` | 0 | 不再使用，统一改为仓库变量 |
| `claim_type` | 0 | 服务要求 Agent2/契约层提供冻结的 12 类值 |

这意味着当前总控客户端可以直接完成鉴权和 multipart 上传，但 Agent2 在正式调用
Agent3 前仍须由契约维护者补齐 `claim_type`。服务不会根据 claim 文本猜测类别。

## multipart

`payload` 同时兼容仓库客户端使用的 `application/json` 文件 part，以及普通 UTF-8
form 字符串。`pre_image`、`post_image` 必选；`damage_map`、`fused_overlay`、
`road_status_map`、`building_instance_mask` 可选。所有图片在推理前做解码检查。

## 启动

```bash
python -m uvicorn backend.services.agent34_service.main:app \
  --host 127.0.0.1 --port 8100 --workers 1
```

真实 Token 和模型路径只写入未跟踪环境，不提交仓库。
