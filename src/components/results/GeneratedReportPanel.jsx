import { AlertTriangle, Download, FileJson2, FileText } from 'lucide-react'
import StatusBadge from '../common/StatusBadge.jsx'

function asText(item) {
  if (typeof item === 'string') return item
  return item?.text ?? item?.claim ?? item?.finding ?? JSON.stringify(item)
}

function FindingGroup({ emptyText, items, title, tone }) {
  return (
    <section className={`report-finding-group tone-${tone}`}>
      <h3>{title}<span>{items.length}</span></h3>
      {items.length ? (
        <ul>{items.map((item, index) => <li key={`${title}-${index}`}>{asText(item)}</li>)}</ul>
      ) : <p>{emptyText}</p>}
    </section>
  )
}

function GeneratedReportPanel({ onDownloadJson, onDownloadMarkdown, pendingReason = '', result }) {
  if (!result) {
    return (
      <section className="panel agent-result-empty">
        <FileText size={24} />
        <div>
          <span className="eyebrow">Agent4 · Report generation</span>
          <h2>等待可信报告</h2>
          <p>{pendingReason || 'Agent4 必须在 Agent3 完成证据校验后运行。当前没有可下载的正式报告。'}</p>
        </div>
      </section>
    )
  }

  return (
    <section className="panel generated-report-panel">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">Agent4 · Report generation</span>
          <h2>可信灾情报告</h2>
        </div>
        <StatusBadge value={result.overallStatus} />
      </div>

      {!result.hasFixedMarkdownSections ? (
        <div className="report-schema-warning">
          <AlertTriangle size={18} />
          <span>Markdown 未完整包含约定的五个固定章节，请在发布前复核后端输出。</span>
        </div>
      ) : null}

      <div className="report-metadata">
        <div><span>报告类型</span><strong>{result.reportType}</strong></div>
        <div><span>报告版本</span><strong>{result.reportVersion ?? '未标注'}</strong></div>
        <div><span>源模型版本</span><strong>{result.sourceVersion}</strong></div>
      </div>

      <div className="report-findings-grid">
        <FindingGroup emptyText="暂无已采纳结论" items={result.keyFindings} title="正式结论" tone="accepted" />
        <FindingGroup emptyText="暂无附条件结论" items={result.qualifiedFindings} title="附条件结论" tone="qualified" />
        <FindingGroup emptyText="暂无被排除结论" items={result.excludedClaims} title="排除项" tone="excluded" />
        <FindingGroup emptyText="未声明证据局限" items={result.limitations} title="证据局限" tone="limitations" />
      </div>

      <div className="final-conclusion">
        <span>最终研判</span>
        <p>{result.finalConclusion || '后端未提供最终研判文本。'}</p>
      </div>

      {onDownloadMarkdown || onDownloadJson ? (
        <div className="report-download-actions">
          {onDownloadMarkdown ? (
            <button className="button button-primary" onClick={onDownloadMarkdown} type="button">
              <Download size={17} />下载 Markdown
            </button>
          ) : null}
          {onDownloadJson ? (
            <button className="button button-secondary" onClick={onDownloadJson} type="button">
              <FileJson2 size={17} />下载结构化 JSON
            </button>
          ) : null}
        </div>
      ) : null}
    </section>
  )
}

export default GeneratedReportPanel
