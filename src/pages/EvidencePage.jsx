import { ArrowLeft, ArrowRight } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import PageHeader from '../components/common/PageHeader.jsx'
import EvidenceVerificationPanel from '../components/results/EvidenceVerificationPanel.jsx'
import { normalizeEvidenceVerification } from '../services/agentResultAdapter.js'
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
  const verification = normalizeEvidenceVerification(task.verification)

  return (
    <div className="page-stack">
      <PageHeader
        actions={
          <>
            <Link className="button button-secondary" to={`/tasks/${task.id}`}><ArrowLeft size={17} />返回任务</Link>
            <Link className="button button-primary" to={`/tasks/${task.id}/report`}>查看报告<ArrowRight size={17} /></Link>
          </>
        }
        description={`${task.name} · Agent3 将图文 Claim 与 Mask、统计结果逐条对齐。`}
        eyebrow="Evidence verification"
        title="证据可信校验"
      />

      <EvidenceVerificationPanel result={verification} />
    </div>
  )
}

export default EvidencePage
