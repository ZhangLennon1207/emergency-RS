# 前后端接口契约区

本目录保存团队协作时需要共同遵守的稳定格式，避免通过口头描述或聊天截图传字段。

```text
contracts/
├── examples/     # 可提交的小型标准JSON输入输出
└── schemas/      # 后续补充JSON Schema
```

当前权威说明：

- `docs/api-contract.md`
- `docs/frontend-agent-integration.md`
- `public/mock-data/manifest.json`
- `public/mock-data/competition-four-agent-v1/.../job-result.json`

修改契约时：

1. 先单独提交契约PR。
2. 说明旧字段是否兼容。
3. 更新标准样例。
4. Agent和前端再基于新契约开发。

禁止把个人电脑绝对路径写入样例；文件必须使用Artifact URL、相对路径或Artifact ID。
