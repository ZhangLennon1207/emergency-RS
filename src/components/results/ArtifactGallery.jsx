import { Download, ExternalLink, FileText, Images } from 'lucide-react'
import { useMemo, useState } from 'react'

const artifactLabels = {
  input_pre: '灾前影像',
  pre_image: '灾前影像',
  input_post: '灾后影像',
  post_image: '灾后影像',
  agent1_fused_overlay: 'Agent1 融合叠加图',
  fused_overlay: '融合叠加图',
  agent1_visual_compare: 'Agent1 六宫格对比图',
  visual_compare: '六宫格对比图',
  agent1_damage_instance_color: '建筑实例损伤图',
  damage_instance_color: '建筑实例损伤图',
  agent1_road_status_color: '道路状态图',
  road_status_color: '道路状态图',
  agent1_road_affected_probability: '道路疑似受影响概率图',
  road_affected_probability: '道路受影响概率图',
  agent1_fused_color: 'Agent1 融合分类图',
  fused_color: '融合分类图',
  agent1_evidence_ledger: 'Agent1 证据账本',
  agent1_report_summary: 'Agent1 汇总数据',
  agent1_review_flags: '人工复核提示',
  agent1_run_manifest: 'Agent1 运行追踪',
  agent2_change_description: 'Agent2 变化描述',
  agent2_raw_model_response: 'Agent2 原始模型响应',
  agent2_prompt_snapshot: 'Agent2 Prompt 快照',
  agent2_run_manifest: 'Agent2 运行追踪',
}

const imageArtifactTypes = new Set([
  'input_pre', 'pre_image', 'input_post', 'post_image',
  'agent1_damage_instance_color', 'damage_instance_color',
  'agent1_road_status_color', 'road_status_color',
  'agent1_road_affected_probability', 'road_affected_probability',
  'agent1_fused_color', 'fused_color',
  'agent1_fused_overlay', 'fused_overlay',
  'agent1_visual_compare', 'visual_compare',
])

const textArtifactTypes = new Set(['agent2_raw_model_response', 'agent2_prompt_snapshot'])

function inferFileName(type, url, mimeType = '') {
  if (mimeType.includes('json') || (!mimeType && !imageArtifactTypes.has(type) && !textArtifactTypes.has(type))) {
    return `${type}.json`
  }
  if (mimeType.startsWith('text/') || textArtifactTypes.has(type)) return `${type}.txt`
  const urlExtension = url.match(/\.([A-Za-z0-9]+)(?:\?|$)/)?.[1]
  return `${type}.${urlExtension ?? 'png'}`
}

function normalizeArtifacts(artifacts) {
  if (Array.isArray(artifacts)) {
    return artifacts
      .map((artifact, index) => ({
        id: artifact.artifact_id ?? `${artifact.artifact_type}-${index}`,
        type: artifact.artifact_type ?? 'artifact',
        label: artifact.label ?? artifactLabels[artifact.artifact_type] ?? artifact.file_name ?? '成果文件',
        fileName: artifact.file_name ?? inferFileName(
          artifact.artifact_type ?? 'artifact',
          artifact.preview_url ?? artifact.url ?? '',
          artifact.mime_type ?? '',
        ),
        mimeType: artifact.mime_type ?? '',
        url: artifact.preview_url ?? artifact.url,
        isImage: (artifact.mime_type ?? '').startsWith('image/') || imageArtifactTypes.has(artifact.artifact_type),
      }))
      .filter((artifact) => artifact.url)
  }

  return Object.entries(artifacts ?? {})
    .filter(([, url]) => typeof url === 'string' && url)
    .map(([type, url]) => ({
      id: type,
      type,
      label: artifactLabels[type] ?? type,
      fileName: inferFileName(type, url),
      mimeType: '',
      url,
      isImage: imageArtifactTypes.has(type),
    }))
}

function ArtifactGallery({ artifacts, resolveUrl = (url) => url }) {
  const items = useMemo(() => normalizeArtifacts(artifacts), [artifacts])
  const imageItems = items.filter((item) => item.isImage)
  const fileItems = items.filter((item) => !item.isImage)
  const [selectedId, setSelectedId] = useState(imageItems[0]?.id ?? null)
  const selected = imageItems.find((item) => item.id === selectedId) ?? imageItems[0]

  if (!items.length) {
    return (
      <div className="artifact-empty">
        <Images size={24} />
        <strong>暂无可展示成果图</strong>
        <span>后端返回 Artifact URL 后会在这里显示。</span>
      </div>
    )
  }

  const selectedUrl = selected ? resolveUrl(selected.url) : null

  return (
    <div className="artifact-sections">
      {selected ? (
        <div className="artifact-gallery">
          <div className="artifact-tabs" aria-label="成果图选择">
            {imageItems.map((item) => (
              <button
                className={item.id === selected.id ? 'active' : ''}
                key={item.id}
                onClick={() => setSelectedId(item.id)}
                type="button"
              >
                {item.label}
              </button>
            ))}
          </div>

          <figure className="artifact-preview">
            <img alt={selected.label} src={selectedUrl} />
            <figcaption>
              <div>
                <strong>{selected.label}</strong>
                <span>{selected.fileName}{selected.mimeType ? ` · ${selected.mimeType}` : ''}</span>
              </div>
              <div className="artifact-actions">
                <a href={selectedUrl} rel="noreferrer" target="_blank"><ExternalLink size={16} />打开原图</a>
                <a download={selected.fileName} href={selectedUrl}><Download size={16} />下载</a>
              </div>
            </figcaption>
          </figure>
        </div>
      ) : (
        <div className="artifact-empty"><Images size={24} /><strong>暂无可展示成果图</strong><span>当前仅返回数据文件。</span></div>
      )}

      {fileItems.length ? (
        <section className="artifact-downloads">
          <div><strong>数据与运行追踪文件</strong><span>仅列出后端实际返回的安全链接</span></div>
          <ul>
            {fileItems.map((item) => (
              <li key={item.id}>
                <FileText size={18} />
                <div><strong>{item.label}</strong><span>{item.fileName}</span></div>
                <a download={item.fileName} href={resolveUrl(item.url)}><Download size={15} />下载</a>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  )
}

export default ArtifactGallery
