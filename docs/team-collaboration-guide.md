# 团队GitHub协作与Agent代码交付指南

> 适用仓库：`ZhangLennon1207/emergency-RS`  
> 适用阶段：四个Agent分别开发、统一后端集成、前端持续完善  
> 核心规则：不直接修改 `main`，每个人只在自己的分支和模块目录中工作，通过PR交给集成人员合并。

---

## 1. 团队协作方式

```text
main（始终保留可运行版本）
  ├─ feature/agent1-姓名
  ├─ feature/agent2-姓名
  ├─ feature/agent3-姓名
  ├─ feature/agent4-姓名
  ├─ feature/backend-姓名
  └─ feature/frontend-姓名
          ↓
      Pull Request
          ↓
    集成人员检查和测试
          ↓
       合并到main
```

成员不需要在同一地点，也不需要同时在线。GitHub负责传递代码、记录修改和处理审查；最终由一名集成人员在具备完整环境的电脑或GPU服务器上运行全流程。

---

## 2. 目录归属

| 角色 | 默认可修改目录 | 不应自行修改 |
| --- | --- | --- |
| 前端成员 | `src/`、`public/`、`e2e/` | Agent源码、公共后端调度 |
| Agent1成员 | `backend/agents/agent1/` | 其他Agent和 `backend/app/` |
| Agent2成员 | `backend/agents/agent2/` | 其他Agent和 `backend/app/` |
| Agent3成员 | `backend/agents/agent3/` | 其他Agent和 `backend/app/` |
| Agent4成员 | `backend/agents/agent4/` | 其他Agent和 `backend/app/` |
| 后端集成人员 | `backend/app/`、`backend/tests/`、`backend/scripts/` | 未沟通时不要重写成员Agent源码 |
| 契约维护者 | `contracts/`、`docs/api-contract.md` | 修改字段前必须通知所有上下游 |

如果确实需要跨目录修改，应在PR说明原因，并让对应模块负责人参与审查。

---

## 3. 第一次准备

### 3.1 加入仓库

1. 仓库管理员在 GitHub 仓库中打开 `Settings → Collaborators`。
2. 邀请成员GitHub账号。
3. 成员在邮件或GitHub通知中接受邀请。

### 3.2 推荐安装

- GitHub Desktop：负责拉取、创建分支、提交和推送。
- VS Code、PyCharm或其他IDE：编辑代码。
- GitHub CLI为可选，不是必须。

### 3.3 克隆仓库

GitHub Desktop：

1. `File → Clone repository`。
2. 选择或输入 `ZhangLennon1207/emergency-RS`。
3. 选择本地文件夹。
4. 点击 `Clone`。

命令行方式：

```powershell
git clone https://github.com/ZhangLennon1207/emergency-RS.git
cd emergency-RS
```

克隆完成后，不要直接在 `main` 上开始修改。

---

## 4. 每次开始工作的标准步骤

### GitHub Desktop

1. 左上角确认仓库为 `emergency-RS`。
2. 顶部切换到 `main`。
3. 点击 `Fetch origin`。
4. 如果出现 `Pull origin`，先点击拉取最新代码。
5. 点击 `Current branch → New branch`。
6. 从最新 `main` 创建自己的功能分支。

### 命令行

```powershell
git switch main
git pull origin main
git switch -c feature/agent1-zhangsan
```

分支命名建议：

```text
feature/agent1-姓名
feature/agent2-姓名
feature/agent3-姓名
feature/agent4-姓名
feature/backend-integration
feature/frontend-task-page
fix/agent3-json-format
docs/update-agent-handoff
```

一个分支只处理一个明确目标，不要把多个无关功能塞进同一个PR。

---

## 5. Agent成员如何放置已有代码

假设你负责Agent2，目标目录是：

```text
backend/agents/agent2/
├── README.md
├── manifest.json
├── adapter.py
├── requirements.txt
├── src/
├── tests/
└── examples/
```

### 5.1 原始代码

将Python源码、提示词模板和必要配置放入：

```text
backend/agents/agent2/src/
```

如果代码来自另一个独立仓库：

- 不要复制原仓库的 `.git/` 隐藏目录。
- 不要复制虚拟环境、缓存、日志、模型权重和输出目录。
- 保留必要的许可证和来源说明。
- 不要把整个压缩包直接提交到仓库。

### 5.2 统一适配入口

在本Agent的 `adapter.py` 中把原始运行方式包装为：

```python
def run(payload: dict, work_dir: str, config: dict | None = None) -> dict:
    result = your_original_inference(payload, work_dir, config)
    return result
```

要求：

- 输入输出必须是清晰的字典结构。
- 返回值必须能被 `json.dumps()` 序列化。
- 图片、Mask和报告文件写入 `work_dir`。
- JSON中不返回个人电脑绝对路径。
- 失败时抛出带有明确说明的异常，不要只返回空字典。

### 5.3 依赖

把本Agent额外依赖写入自己的 `requirements.txt`：

```text
torch==具体版本
transformers==具体版本
pillow==具体版本
```

不要写：

- 本机绝对路径依赖。
- 没有实际使用的整个环境依赖。
- API Key和密码。

如果依赖需要CUDA版本，请在本Agent `README.md` 中单独说明。

### 5.4 manifest.json

至少更新：

```json
{
  "source_version": "你的版本号",
  "owner": "你的GitHub用户名",
  "status": "submitted"
}
```

不要修改 `agent_code` 和 `capability`，除非团队已经批准契约变更。

### 5.5 示例和测试

在 `examples/` 提交：

- 一个小型输入JSON。
- 一个对应输出JSON。
- 必要的字段说明。

在 `tests/` 至少提交：

- 模块能否导入。
- 输出是否为合法JSON结构。
- 必填字段是否存在。
- 无模型或无API Key时是否给出可理解错误。

不要在GitHub提交大型遥感影像。标准小图需要经过团队确认后放到公共测试数据目录。

---

## 6. 绝对不能提交的内容

以下内容已经加入 `.gitignore`，成员仍需要主动检查：

- `.env`、API Key、Token、数据库密码。
- `.venv/`、`venv/`、`__pycache__/`。
- PyTorch、LoRA、Qwen等模型权重。
- `.pt`、`.pth`、`.ckpt`、`.safetensors`、大型 `.onnx`。
- 数据集、大型TIF影像、批量NPY/NPZ概率文件。
- 运行输出、临时文件、日志和个人IDE配置。
- 个人电脑绝对路径。

模型使用环境变量配置，例如：

```env
AGENT1_MODEL_PATH=D:/models/agent1/model.pth
AGENT2_API_KEY=在本机填写
MODEL_DEVICE=cuda:0
```

仓库只提交 `.env.example`，绝不提交真实 `.env`。

如果密钥已经误提交，不能只删除文件；必须立即作废并重新生成密钥，然后通知仓库管理员清理历史。

---

## 7. 提交前自检

### 查看修改范围

GitHub Desktop左侧逐个检查变更文件。

命令行：

```powershell
git status
git diff
```

确认：

- 只修改了本次任务相关文件。
- 没有模型、数据集和密钥。
- 没有临时输出和绝对路径。
- README、依赖和示例已经更新。
- 旧功能仍能运行。

### 查找过大文件

在仓库根目录运行：

```powershell
Get-ChildItem -Recurse -File |
  Where-Object { $_.Length -gt 50MB } |
  Select-Object FullName, Length
```

如果出现模型或数据文件，不要提交。

### 前端成员测试

```powershell
npm install
npm run lint
npm run test:e2e
npm run build
```

### Agent成员测试

根据模块README运行，例如：

```powershell
python -m pytest backend/agents/agent1/tests
```

如果测试必须依赖GPU，应同时提供一个只检查格式的CPU测试。

---

## 8. Commit和Push

### GitHub Desktop

1. 左侧勾选需要提交的文件。
2. Summary填写简短说明。
3. 点击 `Commit to feature/...`。
4. 点击 `Publish branch` 或 `Push origin`。

### 命令行

```powershell
git add backend/agents/agent1
git commit -m "feat(agent1): 提交视觉证据推理模块"
git push -u origin feature/agent1-zhangsan
```

推荐提交信息：

```text
feat(agent1): 接入建筑损伤推理
feat(agent3): 增加五类Claim校验
fix(agent4): 修复报告固定标题
test(agent2): 增加输出格式测试
docs: 更新Agent交付说明
```

不要使用“改了一下”“最终版”“111”等无法理解的提交信息。

---

## 9. 创建Pull Request

Push后在GitHub打开仓库，通常会出现 `Compare & pull request`。

1. `base` 选择 `main`。
2. `compare` 选择自己的功能分支。
3. 标题说明模块和结果。
4. 按PR模板填写修改范围、自测方式和风险。
5. 指定集成人员Review。
6. 点击 `Create pull request`。

PR创建后不要自行点击Merge，等待集成人员检查。

如果审查人提出修改：

1. 继续在原功能分支修改。
2. Commit并Push。
3. PR会自动更新，不需要重新创建PR。

---

## 10. 集成人员操作流程

建议按以下顺序合并：

1. 接口契约和标准样例。
2. Agent1。
3. Agent2。
4. Agent3。
5. Agent4。
6. FastAPI调度和前端真实联调。

每个PR检查：

- 修改是否在成员负责目录内。
- 是否包含密钥、大文件或绝对路径。
- `manifest.json` 是否准确。
- `adapter.run()` 是否可被公共调度调用。
- 示例输出是否符合 `contracts/`。
- 依赖是否与其他Agent冲突。
- 测试命令能否执行。

本地验证PR：

```powershell
gh pr checkout PR编号
```

验证完成后在GitHub点击：

```text
Merge pull request → Confirm merge → Delete branch
```

如果无法通过，使用 `Request changes`，不要直接在审查人的电脑上偷偷修改成员分支。

---

## 11. 合并后其他成员如何同步

GitHub Desktop：

1. 切换到 `main`。
2. 点击 `Fetch origin`。
3. 点击 `Pull origin`。
4. 再从最新 `main` 创建下一个功能分支。

命令行：

```powershell
git switch main
git pull origin main
```

正在开发的分支需要吸收最新 `main` 时：

```powershell
git switch feature/你的分支
git merge main
```

如出现冲突，不要随意删除别人的代码；先确认冲突文件的模块负责人，再决定保留内容。

---

## 12. 冲突处理

冲突文件会出现：

```text
<<<<<<< HEAD
你当前分支的内容
=======
main中的内容
>>>>>>> main
```

处理步骤：

1. 联系该文件负责人确认正确结果。
2. 手工整理为最终内容。
3. 删除冲突标记。
4. 运行测试。
5. Commit并Push。

避免冲突的最好方法：

- 每人只改自己的目录。
- 公共文件先沟通再修改。
- 分支不要长期不更新。
- PR保持小而明确。

---

## 13. 最终集成和联调

代码都进入 `main` 后，由一名集成人员在GPU电脑执行：

```text
拉取main
→ 配置各Agent模型路径和API Key
→ 安装依赖
→ 启动统一FastAPI
→ 启动前端
→ 提交标准灾前/灾后影像
→ 检查Agent1→Agent4完整结果
```

平时开发优先使用Mock和标准JSON，不要求四个模型同时在线。最终GPU联调重点检查：

- `POST /api/v1/jobs` 是否返回 `job_id`。
- 四个Agent是否按顺序运行。
- 单Agent失败是否产生 `partial_success`。
- Artifact是否通过URL访问。
- Agent3是否正确过滤风险描述。
- Agent4是否只使用可信结论。
- 前端是否能展示和下载最终结果。

---

## 14. Agent交付完成检查表

每个Agent负责人提交PR前确认：

- [ ] 源码位于自己的 `src/`。
- [ ] `manifest.json` 已填写版本和负责人。
- [ ] `adapter.py` 已接入真实调用。
- [ ] `requirements.txt` 已更新。
- [ ] README包含环境、模型、输入、输出和运行命令。
- [ ] 提供小型输入输出JSON。
- [ ] 至少有一个格式测试。
- [ ] 没有模型权重、数据集、密钥和绝对路径。
- [ ] 输出符合 `contracts/` 和API文档。
- [ ] PR模板填写完整。

满足以上条件后，集成人员才开始接入公共流水线。
