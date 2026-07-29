import { ArrowLeft, ArrowRight, FileJson2, Image, RefreshCw } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts'
import PageHeader from '../components/common/PageHeader.jsx'
import StatusBadge from '../components/common/StatusBadge.jsx'
import { getTask } from '../services/taskService.js'

function TaskDetailPage() {
  const { taskId } = useParams()
  const [task, setTask] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    const load = () => {
      getTask(taskId)
        .then((data) => {
          if (active) setTask(data)
        })
        .catch((reason) => active && setError(reason.message))
    }
    load()
    const timer = window.setInterval(load, 1000)
    return () => {
      active = false
      window.clearInterval(timer)
    }
  }, [taskId])

  if (error) return <div className="error-state"><strong>任务加载失败</strong><span>{error}</span></div>
  if (!task) return <div className="loading-panel">正在读取任务和 Agent 状态…</div>

  const completedAgents = task.agents.filter((agent) => agent.status === 'completed').length

  return (
    <div className="page-stack">
      <PageHeader
        actions={
          <Link className="button button-secondary" to="/tasks">
            <ArrowLeft size={17} />
            返回列表
          </Link>
        }
        description={`${task.id} · ${task.location}`}
        eyebrow={`${task.disasterLabel} damage assessment`}
        title={task.name}
      />

      <section className="task-summary panel">
        <div>
          <span>当前状态</span>
          <StatusBadge value={task.status} />
        </div>
        <div><span>协同进度</span><strong>{completedAgents} / 5 Agent</strong></div>
        <div><span>综合风险</span><StatusBadge value={task.riskLevel} /></div>
        <div><span>影像输入</span><strong>{task.preImageName} / {task.postImageName}</strong></div>
      </section>

      <section className="panel">
        <div className="panel-heading">
          <div>
            <span className="eyebrow">Agent orchestration</span>
            <h2>多智能体协同执行链</h2>
          </div>
          {task.status === 'running' ? <span className="muted-inline"><RefreshCw className="spin" size={15} />实时更新</span> : null}
        </div>

        <div className="agent-pipeline">
          {task.agents.map((agent, index) => (
            <article className={`agent-stage agent-${agent.status}`} key={agent.id}>
              <div className="agent-stage-head">
                <span>{index + 1}</span>
                <StatusBadge value={agent.status} />
              </div>
              <strong>{agent.name}</strong>
              <small>Agent{index + 1}</small>
              <div className="progress-track"><i style={{ width: `${agent.progress}%` }} /></div>
              <p>
                {agent.status === 'completed' && '阶段输出已生成，可进入下游智能体。'}
                {agent.status === 'running' && `正在执行，当前进度 ${agent.progress}%`}
                {agent.status === 'pending' && '等待上游智能体完成。'}
              </p>
            </article>
          ))}
        </div>
      </section>

      <section className="result-grid">
        <article className="panel">
          <div className="panel-heading">
            <div><span className="eyebrow">Agent1 evidence</span><h2>遥感视觉证据</h2></div>
            <FileJson2 size={20} />
          </div>
          <div className="image-comparison">
            <div><Image size={24} /><span>灾前影像</span><small>{task.preImageName}</small></div>
            <div className="damage-preview"><Image size={24} /><span>五级损伤图</span><small>建筑 Mask 约束已启用</small></div>
          </div>
          <div className="legend-strip">
            {task.damageLevels.map((item) => <span key={item.level}><i style={{ background: item.color }} />{item.level}级</span>)}
          </div>
        </article>

        <article className="panel">
          <div className="panel-heading">
            <div><span className="eyebrow">Agent2 assessment</span><h2>损伤量化评估</h2></div>
          </div>
          <div className="damage-chart-row">
            <div className="mini-pie">
              <ResponsiveContainer height="100%" width="100%">
                <PieChart>
                  <Pie data={task.damageLevels} dataKey="ratio" innerRadius={48} outerRadius={70} paddingAngle={2}>
                    {task.damageLevels.map((item) => <Cell fill={item.color} key={item.level} />)}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
              <strong>15,820<small>建筑像素</small></strong>
            </div>
            <div className="damage-list">
              {task.damageLevels.map((item) => (
                <div key={item.level}>
                  <span><i style={{ background: item.color }} />{item.level}级 {item.label}</span>
                  <strong>{item.ratio}%</strong>
                </div>
              ))}
            </div>
          </div>
        </article>
      </section>

      <section className="next-actions">
        <Link className="action-card" to={`/tasks/${task.id}/evidence`}>
          <div><span>下一步</span><strong>查看证据可信校验</strong></div><ArrowRight size={20} />
        </Link>
        <Link className="action-card" to={`/tasks/${task.id}/report`}>
          <div><span>成果</span><strong>预览最终研判报告</strong></div><ArrowRight size={20} />
        </Link>
      </section>
    </div>
  )
}

export default TaskDetailPage
