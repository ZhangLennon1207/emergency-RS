const STORAGE_KEY = 'emergency-rs-demo-tasks'

export const agentDefinitions = [
  { id: 'agent1', name: '时空视觉证据感知', shortName: '视觉感知' },
  { id: 'agent2', name: '灾情变化描述生成', shortName: '描述生成' },
  { id: 'agent3', name: '证据可信校验', shortName: '证据校验' },
  { id: 'agent4', name: '可信灾情报告生成', shortName: '报告生成' },
]

const damageLevels = [
  { level: 0, label: '无损', pixels: 6200, ratio: 39, color: '#38bdf8' },
  { level: 1, label: '轻微损伤', pixels: 3100, ratio: 20, color: '#34d399' },
  { level: 2, label: '中度损伤', pixels: 2800, ratio: 18, color: '#facc15' },
  { level: 3, label: '严重损伤', pixels: 2400, ratio: 15, color: '#fb923c' },
  { level: 4, label: '毁坏', pixels: 1320, ratio: 8, color: '#ef4444' },
]

const claims = [
  {
    id: 'claim-1',
    text: '研究区域中部与东南方向存在连续建筑损毁斑块。',
    verdict: 'supported',
    evidence: '损伤 Mask 与建筑 Mask 空间重合',
    reason: '3—4级损伤像素主要集中在中部和东南区域。',
  },
  {
    id: 'claim-2',
    text: '区域内绝大多数建筑已经完全毁坏。',
    verdict: 'exaggerated',
    evidence: 'Agent1 损伤量化结果',
    reason: '4级毁坏占比为 8%，不足以支持“绝大多数”的描述。',
  },
  {
    id: 'claim-3',
    text: '主要道路均已完全中断。',
    verdict: 'unsupported',
    evidence: '当前任务未包含道路检测结果',
    reason: '现有证据仅覆盖建筑及损伤分割，无法验证道路状态。',
  },
]

const createAgents = (statuses) =>
  agentDefinitions.map((agent, index) => ({
    ...agent,
    status: statuses[index] ?? 'pending',
    progress: statuses[index] === 'completed' ? 100 : statuses[index] === 'running' ? 58 : 0,
  }))

const seedTasks = [
  {
    id: 'TASK-20260729-001',
    name: '长沙县震后建筑损毁评估',
    disasterType: 'earthquake',
    disasterLabel: '地震',
    location: '湖南省长沙市长沙县',
    status: 'completed',
    riskLevel: 'high',
    createdAt: '2026-07-29T09:20:00+08:00',
    preImageName: 'changsha_pre.tif',
    postImageName: 'changsha_post.tif',
    agents: createAgents(['completed', 'completed', 'completed', 'completed']),
  },
  {
    id: 'TASK-20260729-002',
    name: '浏阳市洪涝建筑影响研判',
    disasterType: 'flood',
    disasterLabel: '洪水',
    location: '湖南省长沙市浏阳市',
    status: 'running',
    riskLevel: 'medium',
    createdAt: '2026-07-29T10:11:00+08:00',
    preImageName: 'liuyang_pre.tif',
    postImageName: 'liuyang_post.tif',
    agents: createAgents(['completed', 'completed', 'running', 'pending']),
  },
  {
    id: 'TASK-20260728-006',
    name: '岳阳市山火损毁快速评估',
    disasterType: 'wildfire',
    disasterLabel: '山火',
    location: '湖南省岳阳市',
    status: 'pending_review',
    riskLevel: 'high',
    createdAt: '2026-07-28T16:35:00+08:00',
    preImageName: 'yueyang_pre.tif',
    postImageName: 'yueyang_post.tif',
    agents: createAgents(['completed', 'completed', 'completed', 'pending']),
  },
]

const delay = (value, duration = 260) =>
  new Promise((resolve) => {
    window.setTimeout(() => resolve(value), duration)
  })

function readTasks() {
  const stored = window.localStorage.getItem(STORAGE_KEY)
  if (!stored) {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(seedTasks))
    return seedTasks
  }

  try {
    return JSON.parse(stored).map((task) => {
      if (task.agents?.length !== 5) return task
      const legacyAgents = task.agents
      const currentStatuses = [
        legacyAgents[0],
        legacyAgents[2],
        legacyAgents[3],
        legacyAgents[4],
      ]
      return {
        ...task,
        agents: agentDefinitions.map((definition, index) => ({
          ...definition,
          status: currentStatuses[index]?.status ?? 'pending',
          progress: currentStatuses[index]?.progress ?? 0,
        })),
      }
    })
  } catch {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(seedTasks))
    return seedTasks
  }
}

function writeTasks(tasks) {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(tasks))
}

function hydrateProgress(task) {
  if (!task.simulationStartedAt || task.status === 'completed') return task

  const elapsed = Date.now() - task.simulationStartedAt
  const stageDuration = 2200
  const activeIndex = Math.min(Math.floor(elapsed / stageDuration), agentDefinitions.length)
  const agents = task.agents.map((agent, index) => {
    if (index < activeIndex) return { ...agent, status: 'completed', progress: 100 }
    if (index === activeIndex && activeIndex < agentDefinitions.length) {
      return {
        ...agent,
        status: 'running',
        progress: Math.min(95, Math.round(((elapsed % stageDuration) / stageDuration) * 100)),
      }
    }
    return { ...agent, status: 'pending', progress: 0 }
  })
  const completed = activeIndex >= agentDefinitions.length
  return { ...task, agents, status: completed ? 'completed' : 'running' }
}

export async function listTasks() {
  const tasks = readTasks().map(hydrateProgress)
  writeTasks(tasks)
  return delay(tasks)
}

export async function getTask(taskId) {
  const tasks = readTasks()
  const index = tasks.findIndex((task) => task.id === taskId)
  if (index < 0) throw new Error('未找到该研判任务')
  const task = hydrateProgress(tasks[index])
  tasks[index] = task
  writeTasks(tasks)
  return delay({
    ...task,
    damageLevels,
    claims,
    verification: buildVerificationPayload(task),
    report: buildReportPayload(task),
  })
}

export async function createTask(input) {
  const tasks = readTasks()
  const task = {
    id: `TASK-${new Date().toISOString().slice(0, 10).replaceAll('-', '')}-${String(tasks.length + 1).padStart(3, '0')}`,
    ...input,
    status: 'running',
    riskLevel: 'medium',
    createdAt: new Date().toISOString(),
    simulationStartedAt: Date.now(),
    agents: createAgents(['running', 'pending', 'pending', 'pending']),
  }
  writeTasks([task, ...tasks])
  return delay(task, 520)
}

export async function getDashboard() {
  const tasks = await listTasks()
  return {
    kpis: [
      { label: '累计研判任务', value: tasks.length + 24, note: '本周新增 8 项', tone: 'blue' },
      { label: '正在协同研判', value: tasks.filter((task) => task.status === 'running').length, note: '四智能体流水线', tone: 'cyan' },
      { label: '待人工复核', value: tasks.filter((task) => task.status === 'pending_review').length, note: '可信规则已拦截', tone: 'amber' },
      { label: '已生成报告', value: tasks.filter((task) => task.status === 'completed').length + 18, note: '支持 Markdown / JSON', tone: 'green' },
    ],
    trend: [
      { time: '08:00', tasks: 2, completed: 1 },
      { time: '10:00', tasks: 5, completed: 3 },
      { time: '12:00', tasks: 8, completed: 5 },
      { time: '14:00', tasks: 7, completed: 6 },
      { time: '16:00', tasks: 11, completed: 8 },
      { time: '18:00', tasks: 9, completed: 8 },
    ],
    recentTasks: tasks.slice(0, 4),
  }
}

export function buildVerificationPayload(task) {
  if (task.agents[2]?.status !== 'completed') return null

  return {
    task_id: task.id,
    source_agent_id: 'agent4',
    source_version: 'Agent4-V4',
    check_result: {
      task_id: task.id,
      overall_status: 'warning',
      claim_checks: claims.map((claim) => ({
        claim_id: claim.id,
        claim_text: claim.text,
        support_status: claim.verdict,
        evidence_refs: claim.evidence ? [claim.evidence] : [],
        reason: claim.reason,
      })),
      supported_claims: ['claim-1'],
      partially_supported_claims: [],
      unsupported_claims: ['claim-3'],
      contradicted_claims: [],
      exaggerated_claims: ['claim-2'],
      revision_suggestions: [
        '将“绝大多数建筑已经完全毁坏”改为与损伤等级统计一致的比例描述。',
        '删除缺少道路检测证据支撑的道路完全中断结论。',
      ],
    },
    verified_evidence_package: {
      task_id: task.id,
      overall_status: 'warning',
      accepted_claims: ['claim-1'],
      qualified_claims: [],
      rejected_claims: ['claim-2', 'claim-3'],
      source_evidence_ids: ['building_mask', 'damage_mask', 'damage_statistics'],
      limitations: ['当前演示任务未包含可验证道路通行状态的证据。'],
    },
  }
}

export function buildReport(task) {
  return `# ${task.name}

## 1. 报告摘要

- 任务编号：${task.id}
- 灾害类型：${task.disasterLabel}
- 研判区域：${task.location}
- 综合风险：高风险

## 2. 核心灾情指标

建筑区域共检测 15,820 个有效像素，其中 3—4 级严重损伤占 23%。损伤区域主要集中在研究区中部和东南方向。

## 3. 分区评估结果

研究区域中部与东南方向存在连续建筑损毁斑块，建议作为人工复核重点区域。

## 4. 证据支撑与一致性校验

系统核验 3 条关键描述：1 条证据支持，1 条存在夸大，1 条缺少证据。未经支持的道路中断结论未写入正式结论。

## 5. 证据局限与不可下结论事项

当前证据无法确认道路完全中断、人员伤亡、经济损失、政府响应和救援状态。
`
}

export function buildReportPayload(task) {
  if (task.agents[3]?.status !== 'completed') return null

  return {
    task_id: task.id,
    source_agent_id: 'agent5',
    source_version: 'Agent5-V2',
    platform_report_json: {
      task_id: task.id,
      report_type: 'remote_sensing_disaster_assessment',
      report_version: '2.0',
      overall_status: 'warning',
      data_basis: {
        accepted_claims: 1,
        qualified_claims: 0,
        rejected_claims: 2,
      },
      key_findings: ['研究区域中部与东南方向存在连续建筑损毁斑块。'],
      qualified_findings: [],
      excluded_claims: [
        '区域内绝大多数建筑已经完全毁坏。',
        '主要道路均已完全中断。',
      ],
      limitations: ['当前证据无法确认道路完全中断、人员伤亡、经济损失、政府响应和救援状态。'],
      final_conclusion: '现有遥感证据支持研究区存在局部建筑损毁，建议对重点区域开展人工复核。',
    },
    markdown_report: buildReport(task),
  }
}
