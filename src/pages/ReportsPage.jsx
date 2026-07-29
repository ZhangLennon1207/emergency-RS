import { ArrowLeft, Download, FileJson2, FileText } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import PageHeader from '../components/common/PageHeader.jsx'
import { buildReport, getTask, listTasks } from '../services/taskService.js'

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
  const report = buildReport(task)

  return (
    <div className="page-stack">
      <PageHeader
        actions={params.taskId ? <Link className="button button-secondary" to={`/tasks/${task.id}`}><ArrowLeft size={17} />返回任务</Link> : null}
        description={`${task.id} · Agent5 结构化成果预览`}
        eyebrow="Report center"
        title="灾害损毁评估报告"
      />

      <section className="report-layout">
        <article className="panel report-document">
          <span className="document-label"><FileText size={16} />Markdown 预览</span>
          <h1>{task.name}</h1>
          <h2>任务摘要</h2>
          <ul>
            <li>任务编号：{task.id}</li>
            <li>灾害类型：{task.disasterLabel}</li>
            <li>研判区域：{task.location}</li>
            <li>综合风险：高风险</li>
          </ul>
          <h2>损毁评估</h2>
          <p>建筑区域共检测 15,820 个有效像素，其中 3—4 级严重损伤占 23%。损伤区域主要集中在研究区中部和东南方向。</p>
          <h2>可信校验</h2>
          <p>系统核验 3 条关键描述：1 条证据支持，1 条存在夸大，1 条缺少证据。未经支持的道路中断结论未写入正式结论。</p>
          <h2>处置建议</h2>
          <p>建议优先对中部连续损毁区域开展人工复核，并结合道路与人口数据进行二次研判。</p>
        </article>

        <aside className="panel export-panel">
          <span className="eyebrow">Deliverables</span>
          <h2>成果文件</h2>
          <p>当前由前端根据 Mock 结果生成，接入 Agent5 后将直接展示后端报告。</p>
          <button className="button button-primary button-full" onClick={() => downloadFile(`${task.id}.md`, report, 'text/markdown')} type="button">
            <Download size={17} />下载 Markdown
          </button>
          <button className="button button-secondary button-full" onClick={() => downloadFile(`${task.id}.json`, JSON.stringify(task, null, 2), 'application/json')} type="button">
            <FileJson2 size={17} />下载结构化 JSON
          </button>
        </aside>
      </section>
    </div>
  )
}

export default ReportsPage
