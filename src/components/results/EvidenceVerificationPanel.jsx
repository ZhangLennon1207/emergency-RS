import { AlertTriangle, CheckCircle2, FileSearch, ShieldCheck } from 'lucide-react'
import { useState } from 'react'
import StatusBadge from '../common/StatusBadge.jsx'

const statusOrder = [
  ['supported', '证据支持'],
  ['partially_supported', '部分支持'],
  ['unsupported', '缺少证据'],
  ['contradicted', '证据矛盾'],
  ['exaggerated', '存在夸大'],
]

function EvidenceVerificationPanel({ result, compact = false }) {
  const [claimFilter, setClaimFilter] = useState('all')

  if (!result) {
    return (
      <section className="panel agent-result-empty">
        <FileSearch size={24} />
        <div>
          <span className="eyebrow">Agent3 · Evidence verification</span>
          <h2>等待证据校验结果</h2>
          <p>Agent3 尚未返回正式结果。当前描述只能作为模型生成内容展示，不能进入可信结论。</p>
        </div>
      </section>
    )
  }

  const counts = result.claimChecks.reduce((summary, claim) => {
    summary[claim.status] = (summary[claim.status] ?? 0) + 1
    return summary
  }, {})
  const riskCount =
    (counts.unsupported ?? 0) +
    (counts.contradicted ?? 0) +
    (counts.exaggerated ?? 0)
  const visibleClaims = result.claimChecks.filter((claim) =>
    claimFilter === 'risk'
      ? ['unsupported', 'contradicted', 'exaggerated'].includes(claim.status)
      : true,
  )
  const verifiedPackage = result.verifiedEvidencePackage

  return (
    <section className="panel verification-panel">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">Agent3 · Evidence verification</span>
          <h2>证据可信校验</h2>
        </div>
        <StatusBadge value={result.overallStatus} />
      </div>

      <div className={`verification-summary ${riskCount ? 'has-risk' : 'is-trusted'}`}>
        {riskCount ? <AlertTriangle size={22} /> : <ShieldCheck size={22} />}
        <div>
          <strong>{riskCount ? `${riskCount} 条风险描述已被拦截` : '全部描述均有证据支撑'}</strong>
          <span>正式报告只接收“已采纳”和“附条件采纳”的结论。</span>
        </div>
      </div>

      <div className="verification-counts">
        {statusOrder.map(([status, label]) => (
          <div key={status}>
            <StatusBadge value={status} />
            <strong>{counts[status] ?? 0}</strong>
            <span>{label}</span>
          </div>
        ))}
      </div>

      {!compact && result.claimChecks.length ? (
        <>
          <div className="claim-toolbar" aria-label="校验结果筛选">
            <strong>Claim 明细</strong>
            <div>
              <button className={claimFilter === 'all' ? 'active' : ''} onClick={() => setClaimFilter('all')} type="button">
                全部 {result.claimChecks.length}
              </button>
              <button className={claimFilter === 'risk' ? 'active' : ''} onClick={() => setClaimFilter('risk')} type="button">
                只看风险 {riskCount}
              </button>
            </div>
          </div>
          <div className="claim-cards">
          {visibleClaims.map((claim) => (
            <article key={claim.id}>
              <div className="claim-card-head">
                <code>{claim.id}</code>
                <StatusBadge value={claim.status} />
              </div>
              <strong>{claim.text || '未提供 Claim 文本'}</strong>
              <p>{claim.reason || '未提供校验说明。'}</p>
              <div className="evidence-ref-list">
                <span>证据来源</span>
                {claim.evidenceRefs.length
                  ? claim.evidenceRefs.map((ref) => <code key={ref}>{ref}</code>)
                  : <em>无可引用证据</em>}
              </div>
            </article>
          ))}
          </div>
        </>
      ) : null}

      {!compact && verifiedPackage ? (
        <div className="verified-package">
          <div><span>已采纳</span><strong>{verifiedPackage.acceptedClaims.length}</strong></div>
          <div><span>附条件采纳</span><strong>{verifiedPackage.qualifiedClaims.length}</strong></div>
          <div><span>已排除</span><strong>{verifiedPackage.rejectedClaims.length}</strong></div>
          <p>Agent4 将只使用已采纳与附条件采纳结论生成正式报告。</p>
        </div>
      ) : null}

      {!compact && result.revisionSuggestions.length ? (
        <div className="revision-box">
          <CheckCircle2 size={19} />
          <div>
            <strong>修订建议</strong>
            <ul>
              {result.revisionSuggestions.map((item) => <li key={item}>{item}</li>)}
            </ul>
          </div>
        </div>
      ) : null}

      <footer className="result-provenance">
        <span>当前能力：Agent3</span>
        <span>历史模型版本：{result.sourceVersion}</span>
      </footer>
    </section>
  )
}

export default EvidenceVerificationPanel
