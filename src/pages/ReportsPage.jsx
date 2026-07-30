import { ArrowLeft, FileText } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import PageHeader from '../components/common/PageHeader.jsx'
import GeneratedReportPanel from '../components/results/GeneratedReportPanel.jsx'
import { normalizeGeneratedReport } from '../services/agentResultAdapter.js'
import { getTask, listTasks } from '../services/taskService.js'

function downloadFile(name, content, type) {
  const url = URL.createObjectURL(new Blob([content], { type }))
  const link = document.createElement('a')
  link.href = url
  link.download = name
  link.click()
  URL.revokeObjectURL(url)
}

function ReportsPage() {
  const params = useParams()
  const [task, setTask] = useState(null)

  useEffect(() => {
    const load = params.taskId
      ? getTask(params.taskId)
      : listTasks().then((tasks) => getTask((tasks.find((item) => item.status === 'completed') ?? tasks[0]).id))
    load.then(setTask)
  }, [params.taskId])

  if (!task) return <div className="loading-panel">正在生成报告预览…</div>
  const report = normalizeGeneratedReport(task.report)

  return (
    <div className="page-stack">
      <PageHeader
        actions={params.taskId ? <Link className="button button-secondary" to={`/tasks/${task.id}`}><ArrowLeft size={17} />返回任务</Link> : null}
        description={`${task.id} · Agent4 结构化可信成果预览`}
        eyebrow="Report center"
        title="灾害损毁评估报告"
      />

      <section className="report-layout">
        <article className="panel report-document">
          <span className="document-label"><FileText size={16} />Markdown 预览</span>
          {report ? (
            <>
              <h1>{task.name}</h1>
              <h2>1. 报告摘要</h2>
              <p>任务 {task.id} 面向{task.location}开展{task.disasterLabel}遥感灾情评估。</p>
              <h2>2. 核心灾情指标</h2>
              <p>建筑区域共检测 15,820 个有效像素，其中 3—4 级严重损伤占 23%。</p>
              <h2>3. 分区评估结果</h2>
              <p>{report.keyFindings[0] ?? '当前没有可进入正式报告的分区结论。'}</p>
              <h2>4. 证据支撑与一致性校验</h2>
              <p>报告仅采用经 Agent3 校验后进入 accepted 或 qualified 集合的结论。</p>
              <h2>5. 证据局限与不可下结论事项</h2>
              <p>{report.limitations.join('；') || '当前未声明证据局限。'}</p>
            </>
          ) : <div className="report-preview-empty">Agent4 尚未生成可预览的正式报告。</div>}
        </article>

        <aside className="report-side">
          <GeneratedReportPanel
            onDownloadJson={report ? () => downloadFile(`${task.id}.json`, JSON.stringify(task.report, null, 2), 'application/json') : null}
            onDownloadMarkdown={report ? () => downloadFile(`${task.id}.md`, report.markdownReport, 'text/markdown') : null}
            result={report}
          />
        </aside>
      </section>
    </div>
  )
}

export default ReportsPage
