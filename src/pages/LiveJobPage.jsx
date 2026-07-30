import { AlertTriangle, ArrowLeft, RefreshCw } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import PageHeader from '../components/common/PageHeader.jsx'
import StatusBadge from '../components/common/StatusBadge.jsx'
import ArtifactGallery from '../components/results/ArtifactGallery.jsx'
import EvidenceVerificationPanel from '../components/results/EvidenceVerificationPanel.jsx'
import GeneratedReportPanel from '../components/results/GeneratedReportPanel.jsx'
import { normalizeEvidenceVerification, normalizeGeneratedReport } from '../services/agentResultAdapter.js'
import { getBackendJob, resolveBackendArtifactUrl } from '../services/backendJobService.js'

const terminalStatuses = new Set(['succeeded', 'partial_success', 'failed'])

const stageLabels = {
  queued: '等待 GPU 队列',
  running_agent1: '正在分析建筑和道路视觉证据',
  running_agent2: '正在生成灾前—灾后变化描述',
  assembling: '正在整理统一结果',
  succeeded: 'Agent1 和 Agent2 均已完成',
  partial_success: '部分智能体完成',
  failed: '分析失败',
}

function getAgentRuns(job) {
  const declaredRuns = job?.agent_runs ?? job?.result?.agent_runs ?? []
  if (declaredRuns.length) return declaredRuns

  const result = job?.result
  if (!result) return []

  return [
    {
      agent_code: 'agent1',
      display_name: '时空视觉证据感知',
      status: result.agent1?.status ?? (job.status === 'running_agent1' ? 'running' : 'pending'),
      progress: result.agent1?.status ? 100 : job.status === 'running_agent1' ? job.progress : 0,
    },
    {
      agent_code: 'agent2',
      display_name: '灾情变化描述生成',
      status: result.agent2?.status ?? (job.status === 'running_agent2' ? 'running' : 'pending'),
      progress: result.agent2?.status ? 100 : job.status === 'running_agent2' ? job.progress : 0,
    },
  ]
}

function LiveJobPage() {
  const { jobId } = useParams()
  const [job, setJob] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    let timer

    async function load() {
      try {
        const data = await getBackendJob(jobId)
        if (!active) return
        setJob(data)
        setError('')
        if (!terminalStatuses.has(data.status)) {
          timer = window.setTimeout(load, 2000)
        }
      } catch (reason) {
        if (active) setError(reason.message)
      }
    }

    load()
    return () => {
      active = false
      window.clearTimeout(timer)
    }
  }, [jobId])

  const artifacts = job?.result?.artifacts ?? {}
  const summary = job?.result?.agent1?.summary
  const description = job?.result?.agent2?.description
  const verificationPayload = job?.result?.verification ?? job?.result?.agent3?.result ?? null
  const reportPayload = job?.result?.report ?? job?.result?.agent4?.result ?? null
  const verification = normalizeEvidenceVerification(verificationPayload)
  const report = normalizeGeneratedReport(reportPayload)
  const errors = useMemo(() => job?.errors ?? [], [job])
  const agentRuns = useMemo(() => getAgentRuns(job), [job])

  if (error) {
    return (
      <div className="error-state">
        <strong>后端任务读取失败</strong>
        <span>{error}</span>
      </div>
    )
  }

  if (!job) return <div className="loading-panel">正在连接模型电脑并读取任务…</div>

  return (
    <div className="page-stack">
      <PageHeader
        actions={<Link className="button button-secondary" to="/tasks"><ArrowLeft size={17} />返回任务中心</Link>}
        description={`${job.job_id} · 当前 Agent1 + Agent2 局域网联调`}
        eyebrow="Live backend job"
        title="真实模型分析任务"
      />

      <section className="task-summary panel">
        <div><span>当前状态</span><StatusBadge value={job.status} /></div>
        <div><span>执行阶段</span><strong>{job.stage ?? stageLabels[job.status] ?? job.status}</strong></div>
        <div><span>总体进度</span><strong>{job.progress ?? 0}%</strong></div>
        <div><span>轮询频率</span><strong>每 2 秒自动更新</strong></div>
      </section>

      {!terminalStatuses.has(job.status) ? (
        <section className="panel live-progress">
          <RefreshCw className="spin" size={20} />
          <div>
            <strong>{stageLabels[job.status] ?? '后端正在处理任务'}</strong>
            <span>请保持后端终端开启，页面会自动获取最新结果。</span>
          </div>
        </section>
      ) : null}

      {errors.length ? (
        <section className="panel backend-errors">
          <AlertTriangle size={21} />
          <div>
            <strong>部分阶段出现错误</strong>
            {errors.map((item, index) => (
              <p key={`${item.agent ?? 'agent'}-${index}`}>{item.message ?? JSON.stringify(item)}</p>
            ))}
          </div>
        </section>
      ) : null}

      {agentRuns.length ? (
        <section className="panel">
          <div className="panel-heading">
            <div><span className="eyebrow">Agent runs</span><h2>智能体执行状态</h2></div>
            {job.status === 'partial_success' ? <StatusBadge value="partial_success" /> : null}
          </div>
          <div className="agent-pipeline live-agent-pipeline">
            {agentRuns.map((run, index) => (
              <article className={`agent-stage agent-${run.status}`} key={run.agent_run_id ?? run.agent_code}>
                <div className="agent-stage-head">
                  <span>{index + 1}</span>
                  <StatusBadge value={run.status} />
                </div>
                <strong>{run.display_name ?? run.agent_code}</strong>
                <small>{run.agent_code}</small>
                <div className="progress-track"><i style={{ width: `${run.progress ?? 0}%` }} /></div>
                <p>{run.error?.message
                  ?? (run.status === 'failed' ? '该阶段执行失败，请查看错误信息。' : null)
                  ?? (run.status === 'skipped' ? '因上游结果不可用，本阶段未执行。' : null)
                  ?? (['succeeded', 'success', 'completed'].includes(run.status) ? '阶段输出已生成。' : null)
                  ?? (run.status === 'running' ? `正在执行，当前进度 ${run.progress ?? 0}%` : '等待执行。')}</p>
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {job.result ? (
        <>
          <section className="panel">
            <div className="panel-heading">
              <div><span className="eyebrow">Artifacts</span><h2>遥感影像与 Agent1 成果</h2></div>
            </div>
            <ArtifactGallery artifacts={artifacts} resolveUrl={resolveBackendArtifactUrl} />
          </section>

          <section className="result-grid">
            <article className="panel">
              <div className="panel-heading">
                <div><span className="eyebrow">Agent1 summary</span><h2>核心损毁指标</h2></div>
                <StatusBadge value={job.result.agent1?.status ?? 'failed'} />
              </div>
              {summary ? (
                <div className="metric-grid">
                  <div><span>建筑总数</span><strong>{summary.total_buildings}</strong></div>
                  <div><span>受损建筑</span><strong>{summary.damaged_buildings}</strong></div>
                  <div><span>建筑受损比例</span><strong>{(summary.building_damage_ratio * 100).toFixed(2)}%</strong></div>
                  <div><span>疑似受影响道路</span><strong>{(summary.affected_road_ratio * 100).toFixed(2)}%</strong></div>
                  <div><span>场景风险</span><StatusBadge value={summary.scene_risk_level} /></div>
                  <div><span>人工复核</span><strong>{summary.review_required ? '需要' : '暂不需要'}</strong></div>
                </div>
              ) : <p className="muted-copy">Agent1 未返回可展示的统计结果。</p>}
            </article>

            <article className="panel">
              <div className="panel-heading">
                <div><span className="eyebrow">Agent2 description</span><h2>英文变化描述</h2></div>
                <StatusBadge value={job.result.agent2?.status ?? 'failed'} />
              </div>
              {description ? <p className="description-copy">{description}</p> : <p className="muted-copy">Agent2 未返回变化描述。</p>}
              <div className="unverified-note">
                <AlertTriangle size={17} />
                <span>模型生成的变化描述，尚未经过 Agent3 证据校验。</span>
              </div>
            </article>
          </section>

          <EvidenceVerificationPanel result={verification} />
          <GeneratedReportPanel result={report} />
        </>
      ) : null}
    </div>
  )
}

export default LiveJobPage
