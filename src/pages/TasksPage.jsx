import { ArrowRight, Plus, Search } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import PageHeader from '../components/common/PageHeader.jsx'
import StatusBadge from '../components/common/StatusBadge.jsx'
import { listTasks } from '../services/taskService.js'

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
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('all')

  useEffect(() => {
    listTasks().then(setTasks)
  }, [])

  const filteredTasks = useMemo(
    () =>
      tasks.filter((task) => {
        const matchesQuery = `${task.name}${task.location}${task.id}`.toLowerCase().includes(query.toLowerCase())
        const matchesStatus = status === 'all' || task.status === status
        return matchesQuery && matchesStatus
      }),
    [query, status, tasks],
  )

  return (
    <div className="page-stack">
      <PageHeader
        actions={
          <Link className="button button-primary" to="/tasks/new">
            <Plus size={17} />
            新建任务
          </Link>
        }
        description="统一管理影像输入、Agent 执行、可信校验和报告交付。"
        eyebrow="Assessment tasks"
        title="研判任务中心"
      />

      <section className="panel">
        <div className="filter-bar">
          <label className="search-field">
            <Search size={17} />
            <input
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索任务名称、地点或编号"
              value={query}
            />
          </label>
          <select onChange={(event) => setStatus(event.target.value)} value={status}>
            <option value="all">全部状态</option>
            <option value="running">运行中</option>
            <option value="pending_review">待人工复核</option>
            <option value="completed">已完成</option>
          </select>
          <span className="result-count">共 {filteredTasks.length} 项</span>
        </div>

        <div className="task-table">
          <div className="task-table-head">
            <span>任务</span>
            <span>灾害类型</span>
            <span>综合风险</span>
            <span>执行状态</span>
            <span>创建时间</span>
            <span />
          </div>
          {filteredTasks.map((task) => (
            <div className="task-table-row" key={task.id}>
              <div>
                <strong>{task.name}</strong>
                <small>{task.id} · {task.location}</small>
              </div>
              <span>{task.disasterLabel}</span>
              <StatusBadge value={task.riskLevel} />
              <StatusBadge value={task.status} />
              <span>{formatTime(task.createdAt)}</span>
              <Link aria-label={`查看${task.name}`} className="icon-link" to={`/tasks/${task.id}`}>
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
      </section>
    </div>
  )
}

export default TasksPage
