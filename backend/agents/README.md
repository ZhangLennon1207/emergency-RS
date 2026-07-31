# Agent独立提交区

每个Agent目录都是一个独立责任边界，成员可以在自己的目录中组织源码，不需要修改其他成员代码。

## 每个Agent必须包含

```text
agentX/
├── README.md           # 模型、输入输出、运行命令和限制
├── manifest.json       # 能力标识、源版本和适配入口
├── adapter.py          # 统一调度层调用入口
├── requirements.txt   # 本Agent额外Python依赖
├── src/                # 原始推理代码
├── tests/              # 最小测试
└── examples/           # 小型JSON样例，不放大影像
```

## 统一适配入口

集成人员只调用各目录的 `adapter.run()`，不直接依赖成员原始脚本内部结构：

```python
def run(payload: dict, work_dir: str, config: dict | None = None) -> dict:
    ...
```

- `payload`：上游统一结构。
- `work_dir`：当前任务可写目录。
- `config`：模型路径、设备和推理参数。
- 返回值：只返回可JSON序列化的字典；图片和大文件写入 `work_dir`，JSON中返回相对路径或Artifact描述。

当前字段规范以根目录 `contracts/` 和 `docs/api-contract.md` 为准。
