const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/+$/, '')

export const isRealApiEnabled =
  import.meta.env.VITE_USE_MOCK === 'false' && Boolean(apiBaseUrl)

function buildApiUrl(path) {
  if (!apiBaseUrl) {
    throw new Error('尚未配置 VITE_API_BASE_URL')
  }
  return `${apiBaseUrl}${path.startsWith('/') ? path : `/${path}`}`
}

async function parseResponse(response) {
  const payload = await response.json().catch(() => null)
  if (!response.ok) {
    const message = payload?.detail?.message
      ?? payload?.message
      ?? `后端请求失败（HTTP ${response.status}）`
    throw new Error(message)
  }
  return payload
}

export async function createBackendJob(preImage, postImage, sampleId = '') {
  const body = new FormData()
  body.append('pre_image', preImage)
  body.append('post_image', postImage)
  if (sampleId.trim()) body.append('sample_id', sampleId.trim())

  const response = await fetch(buildApiUrl('/api/v1/jobs'), {
    method: 'POST',
    body,
  })
  return parseResponse(response)
}

export async function getBackendJob(jobId) {
  const response = await fetch(buildApiUrl(`/api/v1/jobs/${jobId}`))
  return parseResponse(response)
}

export async function listBackendJobs({ page = 1, pageSize = 100 } = {}) {
  const query = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  })
  const response = await fetch(buildApiUrl(`/api/v1/jobs?${query}`))
  return parseResponse(response)
}

export async function getBackendDashboard() {
  const response = await fetch(buildApiUrl('/api/v1/dashboard'))
  return parseResponse(response)
}

export function normalizeBackendJobSummary(job) {
  return {
    id: job.job_id,
    name: job.sample_id,
    location: job.stage,
    status: job.status,
    riskLevel: job.scene_risk_level ?? 'unknown',
    reviewRequired: job.review_required,
    disasterType: 'unknown',
    disasterLabel: job.scope === 'agent1_agent2_local_only' ? 'Agent1 + Agent2' : '四智能体',
    createdAt: job.created_at,
    progress: job.progress,
  }
}

export function resolveBackendArtifactUrl(path) {
  if (!path) return null
  if (/^https?:\/\//i.test(path)) return path
  return buildApiUrl(path)
}
