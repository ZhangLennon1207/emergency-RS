const mockRoot = `${import.meta.env.BASE_URL}mock-data/`

function resolveMockUrl(path) {
  if (!path) return null
  if (/^https?:\/\//i.test(path)) return path
  return `${import.meta.env.BASE_URL}${path.replace(/^\/+/, '')}`
}

function normalizeResult(result) {
  const artifacts = result.visual_evidence?.artifacts ?? []

  return {
    ...result,
    visual_evidence: result.visual_evidence
      ? {
          ...result.visual_evidence,
          artifacts: artifacts.map((artifact) => ({
            ...artifact,
            url: resolveMockUrl(artifact.url),
          })),
        }
      : null,
  }
}

async function readJson(url) {
  const response = await fetch(url)
  if (!response.ok) {
    throw new Error(`Mock 数据加载失败：${response.status}`)
  }
  return response.json()
}

export async function listRealMockSamples() {
  const manifest = await readJson(`${mockRoot}manifest.json`)
  return manifest.samples
}

export async function getRealMockSample(sampleId) {
  const samples = await listRealMockSamples()
  const sample = samples.find((item) => item.sample_id === sampleId)

  if (!sample) {
    throw new Error(`未找到真实 Mock 样本：${sampleId}`)
  }

  const result = await readJson(resolveMockUrl(sample.result_url))
  return normalizeResult(result)
}

