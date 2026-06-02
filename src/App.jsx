import {
  Activity,
  AlertTriangle,
  ArrowRight,
  Bot,
  Building2,
  CheckCircle2,
  ChevronRight,
  CircleDashed,
  Clock3,
  CloudRain,
  FileBarChart2,
  Filter,
  Layers3,
  MapPinned,
  Radar,
  Search,
  ShieldCheck,
  Siren,
  Sparkles,
  Triangle,
} from 'lucide-react'
import {
  Area,
  AreaChart,
  CartesianGrid,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import './App.css'

const responseTrend = [
  { time: '00:00', alerts: 18, verified: 11 },
  { time: '04:00', alerts: 26, verified: 18 },
  { time: '08:00', alerts: 42, verified: 31 },
  { time: '12:00', alerts: 58, verified: 44 },
  { time: '16:00', alerts: 63, verified: 52 },
  { time: '20:00', alerts: 47, verified: 39 },
]

const certaintyBreakdown = [
  { name: 'Confirmed', value: 62, color: '#1d9bf0' },
  { name: 'Uncertain', value: 23, color: '#f59e0b' },
  { name: 'Safe', value: 15, color: '#2fbf71' },
]

const incidentCards = [
  {
    title: '洪涝风险热区',
    value: '12',
    delta: '+3 今日新增',
    tone: 'blue',
    icon: CloudRain,
  },
  {
    title: '待人工复核区域',
    value: '07',
    delta: '2 个高优先级',
    tone: 'amber',
    icon: AlertTriangle,
  },
  {
    title: '已闭环处置事件',
    value: '28',
    delta: '本周完成 81%',
    tone: 'green',
    icon: ShieldCheck,
  },
  {
    title: 'AI 研判耗时',
    value: '4.6m',
    delta: '较传统缩短 68%',
    tone: 'slate',
    icon: Bot,
  },
]

const liveIncidents = [
  {
    id: 'INC-240602-01',
    name: '浏阳市沿河镇洪涝异常',
    level: '高',
    status: '研判中',
    statusTone: 'amber',
    time: '2 分钟前',
  },
  {
    id: 'INC-240602-02',
    name: '长沙县物流园建筑受损疑似区',
    level: '中',
    status: '待复核',
    statusTone: 'blue',
    time: '11 分钟前',
  },
  {
    id: 'INC-240602-03',
    name: '岳麓山景区道路阻断告警',
    level: '高',
    status: '已派单',
    statusTone: 'green',
    time: '18 分钟前',
  },
]

const regionAssessments = [
  {
    region: 'Mask_001',
    type: 'Flood',
    severity: 'High',
    confidence: 'Confirmed',
    detail: '灾后区域呈连续水体特征，变化面积 81%，与道路中断图层重合。',
  },
  {
    region: 'Mask_002',
    type: 'Building Damage',
    severity: 'Medium',
    confidence: 'Uncertain',
    detail: '受云影遮挡影响，结构变化显著但纹理不完整，建议人工复核。',
  },
  {
    region: 'Mask_003',
    type: 'Safe Zone',
    severity: 'Low',
    confidence: 'Confirmed',
    detail: '灾前灾后纹理一致，分割模型与视觉复核均未发现明显异常。',
  },
]

const evidenceSteps = [
  {
    title: '变化检测',
    text: '双时相遥感图像锁定候选变化区域并生成 ROI。',
  },
  {
    title: '语义分割',
    text: '多专家模型输出 Mask ID、灾害类别与像素级置信度。',
  },
  {
    title: '主动验证',
    text: '对低置信或视觉冲突区域执行局部放大、重检与阈值微调。',
  },
  {
    title: '证据成文',
    text: '每条结论绑定掩码、原图、理由和不确定性说明。',
  },
]

const reportSections = [
  '事件摘要与等级建议',
  '受灾区域清单与地图定位',
  '图-掩码-文本证据链',
  '不确定区域与人工复核建议',
]

function App() {
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">
            <Siren size={18} />
          </div>
          <div>
            <p className="eyebrow">Emergency OS</p>
            <h1>灾害感知指挥平台</h1>
          </div>
        </div>

        <nav className="nav">
          <button className="nav-item active" type="button">
            <Radar size={18} />
            <span>态势总览</span>
          </button>
          <button className="nav-item" type="button">
            <MapPinned size={18} />
            <span>区域监测</span>
          </button>
          <button className="nav-item" type="button">
            <Layers3 size={18} />
            <span>证据链中心</span>
          </button>
          <button className="nav-item" type="button">
            <Bot size={18} />
            <span>智能研判 Agent</span>
          </button>
          <button className="nav-item" type="button">
            <FileBarChart2 size={18} />
            <span>报告输出</span>
          </button>
        </nav>

        <div className="sidebar-card">
          <div className="sidebar-card-header">
            <Sparkles size={18} />
            <span>当前值班策略</span>
          </div>
          <p>系统已启用“低置信区域强制复核”模式，避免自动误判进入正式报告。</p>
          <button className="ghost-button" type="button">
            查看策略详情
            <ChevronRight size={16} />
          </button>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div>
            <p className="eyebrow">Province Emergency Command</p>
            <h2>多模态遥感灾害智能体协同平台</h2>
          </div>

          <div className="topbar-actions">
            <label className="searchbox">
              <Search size={16} />
              <input placeholder="搜索事件、区域或报告..." />
            </label>
            <button className="toolbar-button" type="button">
              <Filter size={16} />
              筛选
            </button>
            <button className="primary-button" type="button">
              生成处置简报
              <ArrowRight size={16} />
            </button>
          </div>
        </header>

        <section className="hero-panel">
          <div className="hero-copy">
            <div className="status-pill">
              <Activity size={16} />
              实时运行中
            </div>
            <h3>把“遥感识别结果”升级为“可核验、可追踪、会拒判”的应急决策助手</h3>
            <p>
              平台将灾前灾后影像、变化检测、语义分割、主动验证与结构化报告联动起来，
              为应急管理部门提供可信赖的灾损评估闭环。
            </p>

            <div className="hero-metrics">
              <div>
                <span>89.4%</span>
                <small>区域级评估准确率</small>
              </div>
              <div>
                <span>41%</span>
                <small>幻觉陈述下降</small>
              </div>
              <div>
                <span>7 个</span>
                <small>不确定区域已拦截</small>
              </div>
            </div>
          </div>

          <div className="hero-visual">
            <div className="map-card">
              <div className="map-toolbar">
                <span>RS Event Grid</span>
                <span>Hunan / Live</span>
              </div>
              <div className="map-surface">
                <div className="grid-lines" />
                <div className="hotspot hotspot-a">
                  <span>Mask_001</span>
                </div>
                <div className="hotspot hotspot-b">
                  <span>Mask_002</span>
                </div>
                <div className="hotspot hotspot-c">
                  <span>Mask_003</span>
                </div>
              </div>
              <div className="map-legend">
                <span>
                  <i className="dot dot-blue" />
                  已确认灾损
                </span>
                <span>
                  <i className="dot dot-amber" />
                  不确定疑似区
                </span>
                <span>
                  <i className="dot dot-green" />
                  安全区
                </span>
              </div>
            </div>
          </div>
        </section>

        <section className="stats-grid">
          {incidentCards.map(({ title, value, delta, tone, icon: Icon }) => (
            <article className={`stat-card tone-${tone}`} key={title}>
              <div className="stat-icon">
                <Icon size={20} />
              </div>
              <div>
                <p>{title}</p>
                <strong>{value}</strong>
                <small>{delta}</small>
              </div>
            </article>
          ))}
        </section>

        <section className="content-grid">
          <article className="panel wide">
            <div className="panel-head">
              <div>
                <p className="eyebrow">Command Analytics</p>
                <h3>24 小时事件识别与核验趋势</h3>
              </div>
              <button className="text-button" type="button">
                查看历史
              </button>
            </div>

            <div className="chart-wrap">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={responseTrend}>
                  <defs>
                    <linearGradient id="alertsFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#1d9bf0" stopOpacity={0.35} />
                      <stop offset="95%" stopColor="#1d9bf0" stopOpacity={0} />
                    </linearGradient>
                    <linearGradient id="verifiedFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#2fbf71" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#2fbf71" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="#d7dee9" strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="time" tickLine={false} axisLine={false} tick={{ fill: '#6a768a', fontSize: 12 }} />
                  <YAxis tickLine={false} axisLine={false} tick={{ fill: '#6a768a', fontSize: 12 }} />
                  <Tooltip
                    contentStyle={{
                      background: '#0f1724',
                      border: '1px solid rgba(255,255,255,0.08)',
                      borderRadius: '16px',
                      color: '#f7fbff',
                    }}
                  />
                  <Area type="monotone" dataKey="alerts" stroke="#1d9bf0" strokeWidth={3} fill="url(#alertsFill)" />
                  <Area
                    type="monotone"
                    dataKey="verified"
                    stroke="#2fbf71"
                    strokeWidth={3}
                    fill="url(#verifiedFill)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </article>

          <article className="panel">
            <div className="panel-head">
              <div>
                <p className="eyebrow">Trust Status</p>
                <h3>当前判定置信结构</h3>
              </div>
            </div>

            <div className="pie-wrap">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={certaintyBreakdown}
                    dataKey="value"
                    innerRadius={66}
                    outerRadius={92}
                    paddingAngle={4}
                  />
                  <Tooltip
                    contentStyle={{
                      background: '#0f1724',
                      border: '1px solid rgba(255,255,255,0.08)',
                      borderRadius: '16px',
                      color: '#f7fbff',
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
              <div className="pie-center">
                <strong>92</strong>
                <span>Active Regions</span>
              </div>
            </div>

            <div className="legend-list">
              {certaintyBreakdown.map((item) => (
                <div className="legend-row" key={item.name}>
                  <span>
                    <i className="dot" style={{ background: item.color }} />
                    {item.name}
                  </span>
                  <strong>{item.value}%</strong>
                </div>
              ))}
            </div>
          </article>
        </section>

        <section className="content-grid lower">
          <article className="panel">
            <div className="panel-head">
              <div>
                <p className="eyebrow">Live Incidents</p>
                <h3>在办事件</h3>
              </div>
            </div>

            <div className="incident-list">
              {liveIncidents.map((incident) => (
                <div className="incident-item" key={incident.id}>
                  <div>
                    <strong>{incident.name}</strong>
                    <p>
                      {incident.id} · 风险等级 {incident.level}
                    </p>
                  </div>
                  <div className="incident-meta">
                    <span className={`status-tag tone-${incident.statusTone}`}>{incident.status}</span>
                    <small>{incident.time}</small>
                  </div>
                </div>
              ))}
            </div>
          </article>

          <article className="panel">
            <div className="panel-head">
              <div>
                <p className="eyebrow">Evidence Chain</p>
                <h3>智能体工作流</h3>
              </div>
            </div>

            <div className="workflow">
              {evidenceSteps.map((step, index) => (
                <div className="workflow-step" key={step.title}>
                  <div className="workflow-index">{index + 1}</div>
                  <div>
                    <strong>{step.title}</strong>
                    <p>{step.text}</p>
                  </div>
                </div>
              ))}
            </div>
          </article>
        </section>

        <section className="content-grid bottom">
          <article className="panel wide">
            <div className="panel-head">
              <div>
                <p className="eyebrow">Region Assessment</p>
                <h3>区域级灾害研判结果</h3>
              </div>
              <button className="text-button" type="button">
                导出 JSON
              </button>
            </div>

            <div className="table">
              <div className="table-head">
                <span>Region ID</span>
                <span>Disaster Type</span>
                <span>Severity</span>
                <span>Confidence</span>
                <span>Reasoning Basis</span>
              </div>

              {regionAssessments.map((item) => (
                <div className="table-row" key={item.region}>
                  <span className="mono">{item.region}</span>
                  <span>{item.type}</span>
                  <span>{item.severity}</span>
                  <span>
                    <mark className={`badge ${item.confidence === 'Uncertain' ? 'warn' : 'ok'}`}>
                      {item.confidence}
                    </mark>
                  </span>
                  <span>{item.detail}</span>
                </div>
              ))}
            </div>
          </article>

          <article className="panel">
            <div className="panel-head">
              <div>
                <p className="eyebrow">Report Center</p>
                <h3>自动报告组成</h3>
              </div>
            </div>

            <div className="report-card">
              <div className="report-preview">
                <div className="report-title">
                  <FileBarChart2 size={18} />
                  Disaster Briefing - 2026.06.02
                </div>
                {reportSections.map((item) => (
                  <div className="report-line" key={item}>
                    <CheckCircle2 size={14} />
                    <span>{item}</span>
                  </div>
                ))}
              </div>

              <div className="assistant-note">
                <div className="assistant-head">
                  <Bot size={16} />
                  Agent 解释
                </div>
                <p>
                  本次报告共引用 12 个 Mask 证据，拦截 2 条高风险不确定结论，已自动附加人工复核建议。
                </p>
              </div>

              <button className="primary-button full" type="button">
                发布在线简报
                <ArrowRight size={16} />
              </button>
            </div>
          </article>
        </section>

        <section className="footer-ribbon">
          <div className="ribbon-item">
            <Clock3 size={16} />
            <span>平均识别到报告生成耗时 4.6 分钟</span>
          </div>
          <div className="ribbon-item">
            <Triangle size={16} />
            <span>不确定区域将被强制标注，不进入自动确诊结论</span>
          </div>
          <div className="ribbon-item">
            <CircleDashed size={16} />
            <span>支持接入本地遥感模型、VLM 和应急业务系统</span>
          </div>
          <div className="ribbon-item">
            <Building2 size={16} />
            <span>适用于省市区三级应急管理部门演示与落地</span>
          </div>
        </section>
      </main>
    </div>
  )
}

export default App
