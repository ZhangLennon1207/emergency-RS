import { ArrowRight, Bot, CheckCircle2, Clock3, FileCheck2, RefreshCw, ShieldAlert } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import PageHeader from '../components/common/PageHeader.jsx'
import StatusBadge from '../components/common/StatusBadge.jsx'
import {
  getBackendDashboard,
  isRealApiEnabled,
  normalizeBackendJobSummary,
} from '../services/backendJobService.js'
import { getDashboard } from '../services/taskService.js'

const kpiIcons = [FileCheck2, Bot, ShieldAlert, CheckCircle2]

function normalizeRealDashboard(payload) {
  return {
    kpis: [
      { label: '累计真实任务', value: payload.counts.total, note: 'SQLite 持久化记录', tone: 'blue' },
      { label: '排队或运行中', value: payload.counts.active, note: '本地 GPU 串行队列', tone: 'cyan' },
      { label: '待人工复核', value: payload.counts.review_required, note: '来自 Agent1 review_flags', tone: 'amber' },
      { label: '当前范围成功', value: payload.counts.succeeded, note: '仅表示 Agent1 + Agent2', tone: 'green' },
    ],
    trend: payload.trend,
    recentTasks: payload.recent_jobs.map(normalizeBackendJobSummary),
  }
}

function OverviewPage() {
  const [dashboard, setDashboard] = useState(null)
  const [loadError, setLoadError] = useState('')
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    let active = true
    const request = isRealApiEnabled
      ? getBackendDashboard().then(normalizeRealDashboard)
      : getDashboard()
    request
      .then((payload) => { if (active) setDashboard(payload) })
      .catch((reason) => { if (active) setLoadError(reason.message) })
    return () => { active = false }
  }, [reloadKey])

  if (loadError) {
    return (
      <div className="error-state">
        <strong>态势数据读取失败</strong>
        <span>{loadError}</span>
        <button
          className="button button-primary"
          onClick={() => {
            setLoadError('')
            setDashboard(null)
            setReloadKey((value) => value + 1)
          }}
          type="button"
        >
          <RefreshCw size={16} />重新读取
        </button>
      </div>
    )
  }

  if (!dashboard) return <div className="loading-panel">正在加载研判态势…</div>

  return (
    <div className="page-stack">
      <PageHeader
        actions={
          <Link className="button button-primary" to="/tasks/new">
            新建研判任务
            <ArrowRight size={17} />
          </Link>
        }
        description="聚合遥感损毁识别、量化评估、证据校验与报告生成状态。"
        eyebrow="Situation overview"
        title="多智能体研判态势总览"
      />

      <section className="hero-summary">
        <div>
          <span className="live-pill">
            <i />
            {isRealApiEnabled ? '真实后端模式已启用' : 'Mock 演示链路已就绪'}
          </span>
          <h2>让每一条灾情结论都能回到遥感证据</h2>
          <p>
            {isRealApiEnabled
              ? '当前首页统计来自 FastAPI 与 SQLite；Agent3/4 未进入编排前，成功数量仅代表 Agent1+Agent2。'
              : '前端已按照四智能体业务链路组织任务、结果、证据和报告。Agent 后端接入后，只需替换服务层数据源。'}
          </p>
        </div>
        <div className="hero-flow" aria-label="四智能体流程">
          {['视觉感知与量化', '变化描述', '证据校验', '报告生成'].map((name, index) => (
            <div key={name}>
              <span>{index + 1}</span>
              <small>{name}</small>
            </div>
          ))}
        </div>
      </section>

      <section className="kpi-grid">
        {dashboard.kpis.map((item, index) => {
          const Icon = kpiIcons[index]
          return (
            <article className={`kpi-card tone-${item.tone}`} key={item.label}>
              <div className="kpi-icon"><Icon size={20} /></div>
              <div>
                <span>{item.label}</span>
                <strong>{item.value}</strong>
                <small>{item.note}</small>
              </div>
            </article>
          )
        })}
      </section>

      <section className="dashboard-grid">
        <article className="panel panel-wide">
          <div className="panel-heading">
            <div>
              <span className="eyebrow">24H Throughput</span>
              <h2>{isRealApiEnabled ? '真实任务创建与当前范围完成趋势' : '任务创建与报告完成趋势'}</h2>
            </div>
            <span className="muted-inline"><Clock3 size={15} />每两小时统计</span>
          </div>
          <div className="chart-container">
            <ResponsiveContainer
              height="100%"
              initialDimension={{ width: 800, height: 285 }}
              minWidth={0}
              width="100%"
            >
              <AreaChart data={dashboard.trend}>
                <defs>
                  <linearGradient id="taskFill" x1="0" x2="0" y1="0" y2="1">
                    <stop offset="5%" stopColor="#2f8cff" stopOpacity={0.35} />
                    <stop offset="95%" stopColor="#2f8cff" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="#dce5ef" strokeDasharray="4 4" vertical={false} />
                <XAxis axisLine={false} dataKey="time" tickLine={false} />
                <YAxis axisLine={false} tickLine={false} />
                <Tooltip />
                <Area dataKey="tasks" fill="url(#taskFill)" name="研判任务" stroke="#2f8cff" strokeWidth={3} type="monotone" />
                <Area
                  dataKey="completed"
                  fill="transparent"
                  name={isRealApiEnabled ? '当前范围完成' : '完成报告'}
                  stroke="#1fb981"
                  strokeWidth={3}
                  type="monotone"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </article>

        <article className="panel">
          <div className="panel-heading">
            <div>
              <span className="eyebrow">Recent tasks</span>
              <h2>最近研判任务</h2>
            </div>
            <Link className="text-link" to="/tasks">查看全部</Link>
          </div>
          <div className="compact-task-list">
            {dashboard.recentTasks.map((task) => (
              <Link key={task.id} to={isRealApiEnabled ? `/live-jobs/${task.id}` : `/tasks/${task.id}`}>
                <div>
                  <strong>{task.name}</strong>
                  <span>{task.location}</span>
                </div>
                <StatusBadge value={task.status} />
              </Link>
            ))}
            {dashboard.recentTasks.length === 0 ? <p className="muted-copy">暂无真实任务记录。</p> : null}
          </div>
        </article>
      </section>
    </div>
  )
}

export default OverviewPage
