import { ArrowLeft, CheckCircle2, ShieldCheck } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import PageHeader from '../components/common/PageHeader.jsx'
import StatusBadge from '../components/common/StatusBadge.jsx'
import { getTask, listTasks } from '../services/taskService.js'

function EvidencePage() {
  const params = useParams()
  const [task, setTask] = useState(null)

  useEffect(() => {
    const load = params.taskId
      ? getTask(params.taskId)
      : listTasks().then((tasks) => getTask((tasks.find((item) => item.status === 'completed') ?? tasks[0]).id))
    load.then(setTask)
  }, [params.taskId])

  if (!task) return <div className="loading-panel">正在加载证据校验结果…</div>

  return (
    <div className="page-stack">
      <PageHeader
        actions={params.taskId ? <Link className="button button-secondary" to={`/tasks/${task.id}`}><ArrowLeft size={17} />返回任务</Link> : null}
        description={`${task.name} · Agent4 将图文 Claim 与 Mask、统计结果逐条对齐。`}
        eyebrow="Evidence verification"
        title="证据可信校验"
      />

      <section className="trust-banner">
        <ShieldCheck size={26} />
        <div><strong>可信规则已拦截 2 条风险描述</strong><span>不支持或存在夸大的结论不会自动进入正式报告。</span></div>
      </section>

      <section className="panel">
        <div className="claim-table">
          <div className="claim-table-head">
            <span>待校验描述</span><span>判定</span><span>证据来源</span><span>校验说明</span>
          </div>
          {task.claims.map((claim) => (
            <div className="claim-row" key={claim.id}>
              <strong>{claim.text}</strong>
              <StatusBadge value={claim.verdict} />
              <span>{claim.evidence}</span>
              <span>{claim.reason}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="panel audit-card">
        <CheckCircle2 size={22} />
        <div><strong>运行时规则兜底已启用</strong><p>像素比例、空间重合和能力边界规则会在 Agent4 输出后再次检查高风险表述。</p></div>
      </section>
    </div>
  )
}

export default EvidencePage
