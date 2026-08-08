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
  starting: '正在准备模型任务',
  running_agent1: '正在分析建筑和道路视觉证据',
  running_agent2: '正在生成灾前—灾后变化描述',
  assembling: '正在整理统一结果',
  succeeded: 'Agent1 和 Agent2 均已完成',
  partial_success: '部分智能体完成',
  failed: '分析失败',
}

const agentDefinitions = [
  { agent_code: 'agent1', display_name: '时空视觉证据感知' },
  { agent_code: 'agent2', display_name: '灾情变化描述生成' },
  { agent_code: 'agent3', display_name: '证据可信校验' },
  { agent_code: 'agent4', display_name: '可信报告生成' },
]

function inferredRun(job, definition) {
  const code = definition.agent_code
  const result = job?.result?.[code]
  const error = (job?.errors ?? []).find((item) => item.agent === code || item.agent_code === code)

  if (result) {
    const waitingForIntegration = ['agent3', 'agent4'].includes(code)
      && result.status === 'skipped'
      && job?.result?.four_agent_pipeline_complete === false
    return {
      ...definition,
      status: waitingForIntegration ? 'not_integrated' : result.status,
      progress: ['succeeded', 'success', 'completed', 'failed'].includes(result.status) ? 100 : 0,
      error,
      reason: result.reason,
    }
  }

  if (code === 'agent1') {
    if (job?.status === 'running_agent1') return { ...definition, status: 'running', progress: job.progress ?? 0 }
    if (['running_agent2', 'assembling'].includes(job?.status)) return { ...definition, status: 'succeeded', progress: 100 }
    if (error) return { ...definition, status: 'failed', progress: 100, error }
    return { ...definition, status: 'pending', progress: 0 }
  }

  if (code === 'agent2') {
    if (job?.status === 'running_agent2') return { ...definition, status: 'running', progress: job.progress ?? 0 }
    if (job?.status === 'assembling') return { ...definition, status: 'succeeded', progress: 100 }
    if (error) return { ...definition, status: 'failed', progress: 100, error }
    return { ...definition, status: 'pending', progress: 0 }
  }

  return {
    ...definition,
    status: 'not_integrated',
    progress: 0,
    reason: '当前双智能体联调范围尚未接入该阶段。',
  }
}

function getAgentRuns(job) {
  const declaredRuns = job?.agent_runs ?? job?.result?.agent_runs ?? []
  const declaredByCode = new Map(declaredRuns.map((run) => [run.agent_code, run]))

  return agentDefinitions.map((definition) => {
    const declared = declaredByCode.get(definition.agent_code)
    return declared ? { ...definition, ...declared } : inferredRun(job, definition)
  })
}

function LiveJobPage() {
  const { jobId } = useParams()
  const [job, setJob] = useState(null)
  const [error, setError] = useState('')
  const [reloadKey, setReloadKey] = useState(0)

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
        if (active) {
          setError(reason.message)
          timer = window.setTimeout(load, 5000)
        }
      }
    }

    load()
    return () => {
      active = false
      window.clearTimeout(timer)
    }
  }, [jobId, reloadKey])

  const artifacts = job?.result?.artifacts ?? {}
  const summary = job?.result?.agent1?.summary
  const reviewFlags = job?.result?.agent1?.review_flags
  const description = job?.result?.agent2?.description
  const claimList = job?.result?.agent2?.claim_list ?? []
  const verificationPayload = job?.result?.verification ?? job?.result?.agent3?.result ?? null
  const reportPayload = job?.result?.report ?? job?.result?.agent4?.result ?? null
  const verification = normalizeEvidenceVerification(verificationPayload)
  const report = normalizeGeneratedReport(reportPayload)
  const errors = useMemo(() => job?.errors ?? [], [job])
  const agentRuns = useMemo(() => getAgentRuns(job), [job])
  const fourAgentPipelineComplete = job?.result?.four_agent_pipeline_complete === true

  function retryNow() {
    setError('')
    setReloadKey((current) => current + 1)
  }

  if (error && !job) {
    return (
      <div className="error-state">
        <strong>后端任务读取失败</strong>
        <span>{error}</span>
        <div className="error-state-actions">
          <button className="button button-primary" onClick={retryNow} type="button"><RefreshCw size={16} />重新连接</button>
          <Link className="button button-secondary" to="/tasks">返回任务中心</Link>
        </div>
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

      {!fourAgentPipelineComplete ? (
        <section className="panel pipeline-scope-note">
          <AlertTriangle size={21} />
          <div>
            <strong>当前为 Agent1 + Agent2 联调结果</strong>
            <span>Agent3 证据校验与 Agent4 报告生成尚未接入；即使任务显示执行成功，也不代表四智能体完整研判完成。</span>
          </div>
        </section>
      ) : null}

      {error ? (
        <section className="panel backend-errors connection-warning">
          <AlertTriangle size={21} />
          <div><strong>最新状态读取失败，页面将在 5 秒后重试</strong><p>{error}</p></div>
          <button className="button button-secondary" onClick={retryNow} type="button"><RefreshCw size={15} />立即重试</button>
        </section>
      ) : null}

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
                  ?? (run.status === 'not_integrated' ? run.reason ?? '当前阶段等待后端接入。' : null)
                  ?? (['succeeded', 'success', 'completed'].includes(run.status) ? '阶段输出已生成。' : null)
                  ?? (run.status === 'running' ? `正在执行，当前进度 ${run.progress ?? 0}%` : '等待执行。')}</p>
              </article>
            ))}
          </div>
      </section>

      {job.result ? (
        <>
          <section className="panel">
            <div className="panel-heading">
              <div><span className="eyebrow">Artifacts</span><h2>遥感影像与 Agent1 成果</h2></div>
            </div>
            <ArtifactGallery artifacts={artifacts} resolveUrl={resolveBackendArtifactUrl} />
          </section>

          {reviewFlags?.review_required ? (
            <section className="panel manual-review-panel">
              <div className="panel-heading">
                <div><span className="eyebrow">Manual review</span><h2>建议人工复核</h2></div>
                <StatusBadge value="pending_review" />
              </div>
              <p>该标志表示结果存在需要人工关注的不确定区域，不等同于模型结论错误。</p>
              {reviewFlags.review_reasons?.length ? (
                <ul>{reviewFlags.review_reasons.map((item, index) => <li key={`${item.code ?? 'reason'}-${index}`}>{item.message ?? item.reason ?? String(item)}</li>)}</ul>
              ) : <p className="muted-copy">后端建议复核，但未返回具体原因。</p>}
              {reviewFlags.report_instruction?.recommended_wording ? (
                <blockquote>{reviewFlags.report_instruction.recommended_wording}</blockquote>
              ) : null}
            </section>
          ) : null}

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
              {claimList.length ? (
                <div className="unverified-claims">
                  <strong>待核验 Claim（{claimList.length}）</strong>
                  <ol>
                    {claimList.map((claim, index) => (
                      <li key={claim.claim_id ?? index}>
                        <div><code>{claim.claim_id ?? `C${String(index + 1).padStart(3, '0')}`}</code><StatusBadge value="not_integrated" /></div>
                        <p>{claim.claim ?? claim.text}</p>
                        {claim.related_evidence_ids?.length ? <small>关联证据：{claim.related_evidence_ids.join('、')}</small> : <small>尚未关联已核验证据</small>}
                      </li>
                    ))}
                  </ol>
                </div>
              ) : null}
            </article>
          </section>

          <EvidenceVerificationPanel pendingReason={job.result.agent3?.reason} result={verification} />
          <GeneratedReportPanel pendingReason={job.result.agent4?.reason} result={report} />
        </>
      ) : null}
    </div>
  )
}

export default LiveJobPage
