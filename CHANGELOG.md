# 变动日志

## 2026-07-31

### 团队协作与仓库结构

- 新建四个Agent独立提交区，每个模块包含README、manifest、adapter、依赖、源码、测试和样例目录
- 新增统一流水线编排目录、公共接口契约区和标准任务结果样例
- 新增GitHub Pull Request模板，统一修改范围、自测、验证方式和集成风险说明
- 扩展 `.gitignore`，阻止模型权重、数据集、运行输出和大型遥感中间文件进入仓库
- 新增详细团队协作与Agent交付指南，覆盖首次准备、分支、提交、PR、审查、冲突和最终集成
- 更新README项目结构及四智能体编号

## 2026-07-29

### Agent 联调与真实数据

- 接收最新证据校验和报告格式：当前 Agent3 映射源版本 Agent4-V4，当前 Agent4 映射源版本 Agent5-V2
- 固定 Agent3 的五类 `support_status`、`check_result` 和 `verified_evidence_package` 结构
- 固定 Agent4 的 `platform_report_json` 与五段式 `markdown_report`，并新增前端结果适配器
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

- 新建 Mock 任务会生成并持久化轻量双时相缩略图，任务详情可显示真实上传预览和已校验尺寸
- 新增通用 Artifact 成果图组件，支持结果图切换、原图打开和文件下载，并兼容对象与数组两种后端结构
- 任务详情和真实任务页补充 Agent 失败、跳过、部分成功及错误原因展示，下游未完成时明确显示等待状态
- 统一顶部、侧栏和首页的 Mock/真实后端运行模式提示，并保证侧栏只有一个当前导航项
- 完善新建任务上传组件：增加图片预览、格式解码、宽高读取、双时相尺寸一致性和提交条件反馈
- 任务中心增加灾害类型、综合风险筛选和一键重置，并补充加载与读取失败状态
- 证据校验页增加风险 Claim 筛选、最终证据包分组、任务/报告跳转，并修正损伤量化归属为 Agent1
- 接入 Playwright + Chromium 自动化测试，覆盖总览导航、任务筛选、新建任务、Agent3 校验和 Agent4 报告下载
- 新增自动启动 Vite、失败截图、Trace、视频和 HTML 测试报告配置
- 新增 Agent3 证据校验结果组件：支持五类判定统计、逐条 Claim、证据引用、拦截提示和修订建议
- 新增 Agent4 可信报告结果组件：支持正式结论、附条件结论、排除项、证据局限、固定章节检查和成果下载
- 将证据校验页、报告中心和真实后端任务页接入统一结果适配器；无正式结果时显示等待状态，不生成伪造结论
- 将旧五智能体 Mock 演示流程迁移为当前四智能体编号，并兼容浏览器中已有的旧版本地任务数据
- 将 GitHub Pages 部署迁移到官方 `configure-pages`、`upload-pages-artifact` 和 `deploy-pages` 工作流
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
