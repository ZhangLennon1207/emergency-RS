import { ArrowRight, FilterX, Plus, RefreshCw, Search } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import PageHeader from '../components/common/PageHeader.jsx'
import StatusBadge from '../components/common/StatusBadge.jsx'
import {
  isRealApiEnabled,
  listBackendJobs,
  normalizeBackendJobSummary,
} from '../services/backendJobService.js'
import { listTasks } from '../services/taskService.js'

const activeBackendStatuses = new Set([
  'queued', 'starting', 'running_agent1', 'running_agent2', 'assembling',
])

function formatTime(value) {
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

function TasksPage() {
  const [tasks, setTasks] = useState([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('all')
  const [disasterType, setDisasterType] = useState('all')
  const [riskLevel, setRiskLevel] = useState('all')
  const [reloadKey, setReloadKey] = useState(0)
  const [serverTotal, setServerTotal] = useState(0)

  useEffect(() => {
    let active = true
    const request = isRealApiEnabled
      ? listBackendJobs().then((payload) => ({
        items: payload.items.map(normalizeBackendJobSummary),
        total: payload.total,
      }))
      : listTasks().then((items) => ({ items, total: items.length }))

    request
      .then(({ items, total }) => {
        if (!active) return
        setTasks(items)
        setServerTotal(total)
      })
      .catch((reason) => { if (active) setLoadError(reason.message) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [reloadKey])

  const filteredTasks = useMemo(
    () =>
      tasks.filter((task) => {
        const matchesQuery = `${task.name}${task.location}${task.id}`.toLowerCase().includes(query.toLowerCase())
        const matchesStatus = status === 'all'
          || (status === 'running' && activeBackendStatuses.has(task.status))
          || (status === 'pending_review' && task.reviewRequired)
          || task.status === status
        const matchesDisaster = disasterType === 'all' || task.disasterType === disasterType
        const matchesRisk = riskLevel === 'all' || task.riskLevel === riskLevel
        return matchesQuery && matchesStatus && matchesDisaster && matchesRisk
      }),
    [disasterType, query, riskLevel, status, tasks],
  )
  const hasFilters = query || status !== 'all' || disasterType !== 'all' || riskLevel !== 'all'

  function resetFilters() {
    setQuery('')
    setStatus('all')
    setDisasterType('all')
    setRiskLevel('all')
  }

  return (
    <div className="page-stack">
      <PageHeader
        actions={
          <Link className="button button-primary" to="/tasks/new">
            <Plus size={17} />
            新建任务
          </Link>
        }
        description={isRealApiEnabled
          ? '读取 FastAPI 与 SQLite 中的真实任务记录，查看模型队列和已生成结果。'
          : '统一管理影像输入、Agent 执行、可信校验和报告交付。'}
        eyebrow="Assessment tasks"
        title="研判任务中心"
      />

      <section className="panel">
        <div className="filter-bar">
          <label className="search-field">
            <Search size={17} />
            <input
              onChange={(event) => setQuery(event.target.value)}
              placeholder={isRealApiEnabled ? '搜索场景编号、Job ID 或阶段' : '搜索任务名称、地点或编号'}
              value={query}
            />
          </label>
          <select aria-label="执行状态" onChange={(event) => setStatus(event.target.value)} value={status}>
            <option value="all">全部状态</option>
            <option value="running">运行中</option>
            <option value="pending_review">待人工复核</option>
            {isRealApiEnabled ? (
              <>
                <option value="succeeded">执行成功</option>
                <option value="partial_success">部分成功</option>
                <option value="failed">执行失败</option>
              </>
            ) : <option value="completed">已完成</option>}
          </select>
          {!isRealApiEnabled ? (
            <select aria-label="灾害类型" onChange={(event) => setDisasterType(event.target.value)} value={disasterType}>
              <option value="all">全部灾害</option>
              <option value="earthquake">地震</option>
              <option value="flood">洪水</option>
              <option value="wildfire">山火</option>
            </select>
          ) : null}
          <select aria-label="综合风险" onChange={(event) => setRiskLevel(event.target.value)} value={riskLevel}>
            <option value="all">全部风险</option>
            <option value="low">低风险</option>
            <option value="medium">中风险</option>
            <option value="high">高风险</option>
            <option value="critical">极高风险</option>
          </select>
          {hasFilters ? (
            <button className="filter-reset" onClick={resetFilters} type="button">
              <FilterX size={15} />重置
            </button>
          ) : null}
          <span className="result-count">
            {isRealApiEnabled && hasFilters
              ? `匹配 ${filteredTasks.length} / 共 ${serverTotal} 项`
              : `共 ${isRealApiEnabled ? serverTotal : filteredTasks.length} 项`}
          </span>
        </div>

        {loading ? <div className="loading-panel">正在读取任务记录…</div> : null}
        {loadError ? (
          <div className="error-state">
            <strong>任务记录读取失败</strong>
            <span>{loadError}</span>
            <button
              className="button button-primary"
              onClick={() => {
                setLoading(true)
                setLoadError('')
                setReloadKey((value) => value + 1)
              }}
              type="button"
            >
              <RefreshCw size={16} />重新读取
            </button>
          </div>
        ) : null}

        {!loading && !loadError ? (
        <div className="task-table">
          <div className="task-table-head">
            <span>任务</span>
            <span>{isRealApiEnabled ? '流水线范围' : '灾害类型'}</span>
            <span>综合风险</span>
            <span>执行状态</span>
            <span>创建时间</span>
            <span />
          </div>
          {filteredTasks.map((task) => (
            <div className="task-table-row" key={task.id}>
              <div>
                <strong>{task.name}</strong>
                <small>{task.id} · {task.location}{isRealApiEnabled ? ` · ${task.progress}%` : ''}</small>
              </div>
              <span>{task.disasterLabel}</span>
              <StatusBadge value={task.riskLevel} />
              <StatusBadge value={task.status} />
              <span>{formatTime(task.createdAt)}</span>
              <Link
                aria-label={`查看${task.name}`}
                className="icon-link"
                to={isRealApiEnabled ? `/live-jobs/${task.id}` : `/tasks/${task.id}`}
              >
                <ArrowRight size={18} />
              </Link>
            </div>
          ))}
          {filteredTasks.length === 0 ? (
            <div className="empty-state">
              <Search size={28} />
              <strong>没有找到匹配的任务</strong>
              <span>尝试修改关键词或筛选条件。</span>
            </div>
          ) : null}
        </div>
        ) : null}
      </section>
    </div>
  )
}

export default TasksPage
