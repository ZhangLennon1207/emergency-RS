const labels = {
  pending: '等待中',
  queued: '排队中',
  running: '运行中',
  running_agent1: 'Agent1 分析中',
  running_agent2: 'Agent2 描述中',
  assembling: '整理结果中',
  succeeded: '执行成功',
  success: '执行成功',
  partial_success: '部分成功',
  skipped: '已跳过',
  completed: '已完成',
  failed: '执行失败',
  supported: '证据支持',
  unsupported: '缺少证据',
  partially_supported: '部分支持',
  contradicted: '证据矛盾',
  exaggerated: '存在夸大',
  pending_review: '待人工复核',
  low: '低风险',
  medium: '中风险',
  high: '高风险',
  critical: '极高风险',
}

function StatusBadge({ value }) {
  return <span className={`status-badge status-${value}`}>{labels[value] ?? value}</span>
}

export default StatusBadge
