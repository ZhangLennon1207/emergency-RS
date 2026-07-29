const labels = {
  pending: '等待中',
  running: '运行中',
  completed: '已完成',
  failed: '执行失败',
  supported: '证据支持',
  unsupported: '缺少证据',
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
