# 变动日志

## 2026-07-29

### Agent 联调与真实数据

- 根据最新 Agent1+Agent2 后端交接文件，接入 `POST /api/v1/jobs` 和 `GET /api/v1/jobs/{job_id}`
- 新增真实后端调用服务、前端环境变量模板和局域网联调结果页
- 新建任务页支持在 Mock 与真实 API 之间切换；真实模式每2秒轮询任务状态
- 支持 `queued`、`running_agent1`、`running_agent2`、`assembling`、`succeeded`、`partial_success` 和 `failed`
- 支持展示灾前/灾后图、Agent1 融合结果与核心指标、Agent2 英文描述和错误信息
- Agent2 文本在 Agent3 尚未接入时明确标记为“未经证据校验”
- 整理 `EARTHQUAKE-TURKEY_003679` 的 Agent1/2 真实结果和8张必要图片，建立首套前端真实 Mock
- 真实 Mock 已移除原开发电脑绝对路径，并通过 Artifact URL 访问成果

### 方案与接口文档

- 新增 `docs/full-process-plan.md`：从前端完善、数据库建设、Agent 对接到测试部署的全过程实施方案
- 将双智能体联调要求补充到全过程方案：`job_id`、GPU 串行队列、`partial_success`、上传拒绝规则、Artifact URL 和 CORS
- 根据 Agent1～Agent4 交接文档修正全过程方案，并新增 `docs/frontend-agent-integration.md` 前端对接设计
- 扫描 Agent1/2 固定20条输出和140条配对消融实验，新增 `docs/project-data-inventory.md` 记录真实 Schema、可复用资产、标准演示样本和当前缺失项
- 新增 `docs/api-contract.md` 草案，记录当前 Agent1+Agent2 实际接口，并通过契约版本、流水线版本和能力标识兼容未来 Agent3/4
- 新增 `docs/frontend-plan.md`：前端页面、架构、交互、数据接入和分阶段实施方案

### 前端基础功能

- 引入 React Router，并将单页静态看板重构为多页面前端
- 新增态势总览、任务中心、新建研判、任务详情、证据校验和报告中心页面
- 新增前端 Mock 服务；早期五智能体模拟结构保留为待迁移内容，正式联调以当前 Agent1+Agent2 接口为准
- 新增 Markdown 和 JSON 报告下载功能
- 完善桌面端、平板端和移动端响应式布局
- 更新站点中文标题、描述和 GitHub Pages 兼容路由
- 完善桌面端侧栏收起模式：图标栏、悬停提示、状态持久化及主内容平滑扩展
- 完成 ESLint 检查和 Vite 生产构建验证

## 2026-07-14

- 将 README.md 翻译为中文
- 新增 `docs/backend-plan.md`：后端架构实施方案
- 创建 `backend/` 后端项目目录结构
- 新增 `backend/.env.example`：环境变量模板
- 更新 `.gitignore`：添加 Python 相关忽略规则
