import { Download, ExternalLink, Images } from 'lucide-react'
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
  damage_instance_color: '建筑实例损伤图',
  road_status_color: '道路状态图',
  road_affected_probability: '道路受影响概率图',
  fused_color: '融合分类图',
}

function normalizeArtifacts(artifacts) {
  if (Array.isArray(artifacts)) {
    return artifacts
      .map((artifact, index) => ({
        id: artifact.artifact_id ?? `${artifact.artifact_type}-${index}`,
        type: artifact.artifact_type ?? 'artifact',
        label: artifact.label ?? artifactLabels[artifact.artifact_type] ?? artifact.file_name ?? '成果文件',
        fileName: artifact.file_name ?? `${artifact.artifact_type ?? 'artifact'}.png`,
        mimeType: artifact.mime_type ?? '',
        url: artifact.preview_url ?? artifact.url,
      }))
      .filter((artifact) => artifact.url)
  }

  return Object.entries(artifacts ?? {})
    .filter(([, url]) => typeof url === 'string' && url)
    .map(([type, url]) => ({
      id: type,
      type,
      label: artifactLabels[type] ?? type,
      fileName: `${type}.${url.split('.').pop()?.split('?')[0] || 'png'}`,
      mimeType: '',
      url,
    }))
}

function ArtifactGallery({ artifacts, resolveUrl = (url) => url }) {
  const items = useMemo(() => normalizeArtifacts(artifacts), [artifacts])
  const [selectedId, setSelectedId] = useState(items[0]?.id ?? null)
  const selected = items.find((item) => item.id === selectedId) ?? items[0]

  if (!selected) {
    return (
      <div className="artifact-empty">
        <Images size={24} />
        <strong>暂无可展示成果图</strong>
        <span>后端返回 Artifact URL 后会在这里显示。</span>
      </div>
    )
  }

  const selectedUrl = resolveUrl(selected.url)

  return (
    <div className="artifact-gallery">
      <div className="artifact-tabs" aria-label="成果图选择">
        {items.map((item) => (
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
  )
}

export default ArtifactGallery
