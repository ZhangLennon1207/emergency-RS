# Emergency RS 后端架构实施方案

## 上下文

当前项目是一个纯前端演示 Dashboard（React 19 + Vite 8），所有数据硬编码在 `src/App.jsx`（~560 行）中，部署于 GitHub Pages。目标是将其升级为完整的应急遥感智能体平台，具备：

- Python FastAPI 后端 + 数据 API + 遥感变化检测/语义分割模型集成
- React Router 多页路由重构前端
- 云平台部署（阿里云/华为云）

---

## 1. 整体架构

```
┌──────────────┐     ┌──────────────┐     ┌───────────────┐
│  React SPA   │────▶│  Nginx       │────▶│  FastAPI      │
│  (Vite)      │     │  (反向代理)   │     │  (Port 8000)  │
└──────────────┘     └──────────────┘     └───────┬───────┘
                                                  │
                          ┌───────────────────────┼───────────────────────┐
                          │                       │                       │
                   ┌──────▼──────┐        ┌──────▼──────┐        ┌──────▼──────┐
                   │ PostgreSQL  │        │  Redis      │        │  OSS/MinIO  │
                   │ + PostGIS   │        │  (WS/pub)   │        │  (影像存储)  │
                   └─────────────┘        └─────────────┘        └─────────────┘
```

**关键技术决策：**

| 决策 | 选择 | 理由 |
|------|------|------|
| 异步 ORM | SQLAlchemy 2.0 async + asyncpg | FastAPI 原生非阻塞 |
| 对象存储 | MinIO(dev) / 阿里云 OSS(prod) | 卫星影像 10-100MB，不能放 API 服务器 |
| 模型推理 | 线程池 + DB 任务队列 | 不阻塞 asyncio 事件循环 |
| WebSocket | FastAPI + Redis pub/sub | 实时推送事件状态变更 |
| 认证 | JWT access + refresh token | 无状态，SPA 标准方案 |
| GIS | PostGIS + GeoJSON | 空间查询 + Leaflet 原生消费 |
| 状态管理 | React Context | 只需管理 auth + WebSocket 两个全局状态 |

---

## 2. 项目目录结构

```
emergency-RS/
├── package.json              # React 依赖：+react-router-dom, axios, leaflet
├── vite.config.js            # +proxy 配置到 127.0.0.1:8000
├── src/
│   ├── App.jsx               # 改为纯路由配置
│   ├── pages/
│   │   ├── Login.jsx
│   │   ├── SituationOverview.jsx   # 态势总览（现 Dashboard）
│   │   ├── RegionMonitoring.jsx    # 区域监测 + Leaflet 地图
│   │   ├── EvidenceCenter.jsx      # 证据链中心
│   │   ├── AgentJudgment.jsx       # 智能研判 Agent
│   │   └── ReportOutput.jsx        # 报告输出
│   ├── components/
│   │   ├── layout/{Shell,Sidebar,Topbar}.jsx
│   │   ├── dashboard/{HeroPanel,StatCards,TrendChart,CertaintyPie,
│   │   │              LiveIncidents,AgentWorkflow,RegionAssessTable,
│   │   │              ReportCenter,FooterRibbon}.jsx
│   │   └── common/{ProtectedRoute,StatusTag,Panel}.jsx
│   ├── services/{apiClient,auth,dashboard,region,evidence,report,upload}Service.js
│   └── store/AuthContext.jsx
│
├── backend/
│   ├── pyproject.toml        # FastAPI + SQLAlchemy + GDAL + torch 等
│   ├── Dockerfile
│   ├── docker-compose.yml    # api + db + redis + nginx
│   ├── nginx.conf
│   ├── alembic.ini
│   └── app/
│       ├── main.py           # FastAPI 工厂 + lifespan（加载模型）
│       ├── config.py         # pydantic-settings
│       ├── database.py       # AsyncSQLAlchemy engine + session
│       ├── models/           # SQLAlchemy ORM：user, region, incident,
│       │                       assessment, evidence, report, audit_log, kpi_snapshot
│       ├── schemas/          # Pydantic 请求/响应模型
│       ├── api/
│       │   ├── router.py     # 聚合所有子路由
│       │   ├── deps.py       # get_current_user, require_role
│       │   └── v1/{auth,dashboard,regions,incidents,assessments,
│       │           evidence,reports,uploads,ws}.py
│       ├── services/
│       │   ├── change_detection.py      # 变化检测模型（ChangeFormer/BIT）
│       │   ├── semantic_segmentation.py # 语义分割模型（SegFormer）
│       │   ├── evidence_chain.py        # 证据链自动生成
│       │   └── report_generator.py      # 中文简报模板生成
│       ├── middleware/cors.py
│       └── tests/
```

---

## 3. 数据库设计（PostgreSQL + PostGIS）

### 核心表

- **users** — 用户认证与指挥中心人员
- **regions** — 地理区域（Mask 多边形），含 PostGIS GEOMETRY 列
- **incidents** — 在办事件（INC-240602-01 等）
- **satellite_images** — 灾前/灾后卫星影像（OSS 对象键）
- **assessments** — AI 研判结果（灾害类型、严重度、置信度、推理文本）
- **evidence_chain** — 四步证据链：变化检测→语义分割→主动验证→证据成文
- **reports** — 自动生成的结构化灾情简报（JSONB）
- **audit_logs** — 操作审计日志
- **kpi_snapshots** — 定时聚合快照（支撑 24h 趋势图）

### 关键枚举类型

```sql
disaster_type: Flood | Building Damage | Landslide | Fire | Safe Zone | Other
severity_level: Low | Medium | High | Critical
confidence_level: Confirmed | Uncertain | Safe
incident_status: Opened | Judging | PendingReview | Dispatched | Closed
user_role: admin | analyst | commander | viewer
```

---

## 4. API 端点设计（`/api/v1`）

### 认证
- `POST /auth/login` → JWT access + refresh token
- `POST /auth/refresh` → 刷新 access token
- `GET /auth/me` → 当前用户信息

### 态势总览 Dashboard
- `GET /dashboard/kpi` → 4 个统计卡片数据
- `GET /dashboard/trend?hours=24` → 24h 趋势时序数据
- `GET /dashboard/certainty` → 置信度饼图 + active_regions
- `GET /dashboard/incidents/live` → 在办事件列表
- `GET /dashboard/hero-stats` → Hero 面板 3 个指标

### 区域监测 Regions
- `GET /regions` → 分页列表（支持省/市筛选）
- `GET /regions/{id}` → 详情 + 最新研判
- `POST /regions` → 创建区域（含 GeoJSON）
- `DELETE /regions/{id}` → 删除

### 研判结果 Assessments
- `GET /assessments` → 分页列表
- `POST /assessments/trigger` → **触发模型推理**（异步，返回 task_id）
- `GET /assessments/tasks/{task_id}` → 查询推理任务状态
- `PATCH /assessments/{id}/review` → 人工复核（覆盖置信度）

### 事件、证据链、报告、文件上传（标准 CRUD）

完整 CRUD 见下方详细 API 文档。

### WebSocket
- `/ws/incidents` → 实时推送新事件、状态变更、KPI 更新

---

## 5. 模型集成方案

```
POST /assessments/trigger {region_id, pre_image_id, post_image_id}
  │
  ├─ 立即返回 {task_id, status: "pending"}（HTTP 202）
  │
  └─ Background Task:
      1. 从 OSS 下载灾前/灾后影像
      2. ChangeDetectionService.detect() → 变化 mask
      3. SemanticSegmentationService.segment() → 灾害类型 + 损坏 mask
      4. 按变化面积百分比判定严重度
      5. 按云覆盖率/模型熵值判定置信度（>30% 云 → Uncertain）
      6. 模板生成中文推理文本
      7. 写入 Assessment + EvidenceChain（4步）记录
      8. 更新 task 状态为 done/failed
```

**模型选型建议：**
- 变化检测：ChangeFormer / BIT / SNUNet（PyTorch）
- 语义分割：SegFormer / DeepLabV3+
- 过渡方案：先用规则代理（像素差分 + NDWI 阈值），再替换为真实模型

---

## 6. 前端重构

### 路由设计
```
/login          → Login.jsx
/               → Shell (layout)
  /situation    → SituationOverview.jsx  （默认首页）
  /regions      → RegionMonitoring.jsx
  /evidence     → EvidenceCenter.jsx
  /agent        → AgentJudgment.jsx
  /reports      → ReportOutput.jsx
```

### 组件提取策略
- `Shell.jsx`：侧边栏 + Topbar + `<Outlet />`
- `Sidebar.jsx`：导航按钮改用 `useNavigate` + `useLocation`
- 每个 dashboard 区块拆为独立组件，数据通过 `props` 传入
- 保留 `App.css` 全部样式不变

### API 调用模式
- `apiClient.js`：axios 实例，自动附加 JWT，401 自动 refresh
- 每个 Service 文件对应一组 API 端点
- `SituationOverview.jsx` 中用 `useEffect` + `Promise.all` 并行请求 4 个 dashboard API

### 新增 npm 依赖
```
axios, react-router-dom, leaflet, react-leaflet
```

---

## 7. 分阶段实施计划

### Phase 1：基础搭建（第 1-2 周）
1. 初始化 `backend/` 项目结构 + pyproject.toml + Dockerfile
2. 创建所有 SQLAlchemy ORM 模型 + Alembic 初始迁移
3. 实现 JWT 认证三件套：login / refresh / me
4. 实现 Dashboard 6 个 Mock API（返回与当前硬编码相同的数据）
5. 前端安装 React Router + Axios
6. 拆分 Shell/Sidebar/Topbar，创建 SituationOverview 页面从 API 取数据
7. **验证时机**：`npm run dev` + `uvicorn` 同时跑，确认 API 打通

### Phase 2：完整数据模型（第 3-4 周）
8. 实现真实 DB 查询替换 Mock API
9. 创建 KPI 快照定时任务（APScheduler，每 15 分钟）
10. 实现 Regions / Incidents / Assessments 完整 CRUD
11. 构建其余 4 个页面 + Leaflet 地图集成
12. ProtectedRoute + Login 页面 + AuthContext 全流程打通

### Phase 3：模型集成（第 5-6 周）
13. 文件上传服务（OSS/MinIO）+ 前端拖拽组件
14. 实现 ChangeDetectionService + SemanticSegmentationService
15. 实现 `POST /assessments/trigger` 异步推理管线
16. 证据链自动生成逻辑
17. 前端 AgentJudgment 页面连接真实推理

### Phase 4：报告与完善（第 7-8 周）
18. 中文简报模板生成器
19. WebSocket 实时推送替代轮询
20. 全局错误边界 + 骨架屏 + 空状态
21. 后端 pytest + 前端 Vitest 测试

### Phase 5：部署（第 9 周）
22. Docker Compose 本地全栈验证
23. 云平台部署：ECS + 托管 PostgreSQL + OSS + SSL + CDN
24. 日志采集 + 监控配置

---

## 8. 关键文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/App.jsx` | **重构** | 560行单文件拆分为路由+15个组件 |
| `src/App.css` | **保留** | 719行设计系统 CSS，不修改 |
| `package.json` | **扩展** | 新增 axios, react-router-dom, leaflet |
| `vite.config.js` | **扩展** | 新增 dev proxy 到 127.0.0.1:8000 |
| `backend/app/main.py` | **新建** | FastAPI 入口 |
| `backend/app/config.py` | **新建** | 环境配置 |
| `backend/app/database.py` | **新建** | 异步数据库引擎 |
| `backend/app/models/*.py` | **新建** | 9 个 ORM 模型 |
| `backend/app/api/v1/*.py` | **新建** | 8 个路由模块 |
| `backend/app/services/*.py` | **新建** | 4 个服务（模型推理+证据链+报告） |
| `backend/docker-compose.yml` | **新建** | 4 服务编排 |
| `backend/nginx.conf` | **新建** | 反向代理配置 |

---

## 9. 验证方式

1. **Phase 1 验证**：`npm run dev`（前端 :5173）+ `uvicorn app.main:app`（后端 :8000），浏览器打开 http://localhost:5173，确认 Dashboard 数据来自 API
2. **Phase 2 验证**：通过 Swagger UI（http://localhost:8000/docs）测试所有 CRUD，前端 5 个页面均可导航且数据正确
3. **Phase 3 验证**：上传测试卫星影像 → 触发推理 → 轮询 task 状态 → 结果写入 → 证据链显示完整
4. **Phase 4 验证**：`docker compose up` → 浏览器访问 nginx:80 → 全栈联通
5. **Phase 5 验证**：通过域名访问线上系统，跑通完整业务流程
