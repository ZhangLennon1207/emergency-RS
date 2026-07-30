import { AlertCircle, ArrowLeft, ArrowRight, CheckCircle2, ImagePlus, UploadCloud } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import PageHeader from '../components/common/PageHeader.jsx'
import { createBackendJob, isRealApiEnabled } from '../services/backendJobService.js'
import { createTask } from '../services/taskService.js'

const disasterTypes = {
  earthquake: '地震',
  flood: '洪水',
  typhoon: '台风',
  wildfire: '山火',
  explosion: '爆炸',
  fire: '火灾',
  chemical: '化学泄漏',
  conflict: '冲突战损',
}

const supportedImageTypes = new Set(['image/png', 'image/jpeg'])

function inspectImage(file, previewUrl) {
  return new Promise((resolve, reject) => {
    const image = new Image()
    image.onload = () => {
      const maxPreviewSize = 480
      const scale = Math.min(1, maxPreviewSize / Math.max(image.naturalWidth, image.naturalHeight))
      const canvas = document.createElement('canvas')
      canvas.width = Math.max(1, Math.round(image.naturalWidth * scale))
      canvas.height = Math.max(1, Math.round(image.naturalHeight * scale))
      canvas.getContext('2d').drawImage(image, 0, 0, canvas.width, canvas.height)
      resolve({
        width: image.naturalWidth,
        height: image.naturalHeight,
        previewUrl,
        thumbnailUrl: canvas.toDataURL('image/jpeg', 0.72),
      })
    }
    image.onerror = () => reject(new Error('图片无法解码，请重新选择有效的 PNG 或 JPEG 文件。'))
    image.src = previewUrl
  })
}

function UploadField({ error, file, label, metadata, onChange }) {
  return (
    <div className="upload-field">
      <label className={`upload-box ${file ? 'has-file' : ''} ${error ? 'has-error' : ''}`}>
        {metadata ? <img alt={`${label}预览`} src={metadata.previewUrl} /> : null}
        {file ? <CheckCircle2 size={26} /> : <UploadCloud size={30} />}
        <strong>{file ? file.name : label}</strong>
        <span>
          {file
            ? `${(file.size / 1024 / 1024).toFixed(2)} MB${metadata ? ` · ${metadata.width} × ${metadata.height}` : ' · 正在读取尺寸'}`
            : '支持 PNG、JPG 或 JPEG'}
        </span>
        <input
          accept=".png,.jpg,.jpeg,image/png,image/jpeg"
          aria-label={label}
          onChange={(event) => onChange(event.target.files?.[0] ?? null)}
          type="file"
        />
      </label>
      {error ? <span className="upload-error"><AlertCircle size={14} />{error}</span> : null}
    </div>
  )
}

function NewTaskPage() {
  const navigate = useNavigate()
  const previewUrls = useRef(new Set())
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState('')
  const [fileErrors, setFileErrors] = useState({ preImage: '', postImage: '' })
  const [imageMetadata, setImageMetadata] = useState({ preImage: null, postImage: null })
  const [form, setForm] = useState({
    name: '',
    disasterType: 'earthquake',
    location: '',
    preImage: null,
    postImage: null,
  })

  useEffect(() => () => {
    previewUrls.current.forEach((url) => URL.revokeObjectURL(url))
  }, [])

  const update = (key, value) => setForm((current) => ({ ...current, [key]: value }))
  const dimensionsMatch =
    imageMetadata.preImage
    && imageMetadata.postImage
    && imageMetadata.preImage.width === imageMetadata.postImage.width
    && imageMetadata.preImage.height === imageMetadata.postImage.height
  const missingRequirements = [
    !form.name.trim() && '填写任务名称',
    !form.location.trim() && '填写研判区域',
    !form.preImage && '选择灾前影像',
    !form.postImage && '选择灾后影像',
    form.preImage && !imageMetadata.preImage && !fileErrors.preImage && '等待灾前影像读取完成',
    form.postImage && !imageMetadata.postImage && !fileErrors.postImage && '等待灾后影像读取完成',
    imageMetadata.preImage && imageMetadata.postImage && !dimensionsMatch && '两张影像尺寸必须一致',
    (fileErrors.preImage || fileErrors.postImage) && '修正影像文件错误',
  ].filter(Boolean)
  const canSubmit = missingRequirements.length === 0

  async function updateImage(key, file) {
    setSubmitError('')
    setFileErrors((current) => ({ ...current, [key]: '' }))
    setImageMetadata((current) => ({ ...current, [key]: null }))

    if (!file) {
      update(key, null)
      return
    }

    if (!supportedImageTypes.has(file.type)) {
      update(key, null)
      setFileErrors((current) => ({ ...current, [key]: '仅支持 PNG、JPG 或 JPEG 图片。' }))
      return
    }

    update(key, file)
    const previewUrl = URL.createObjectURL(file)
    previewUrls.current.add(previewUrl)

    try {
      const metadata = await inspectImage(file, previewUrl)
      setImageMetadata((current) => ({ ...current, [key]: metadata }))
    } catch (reason) {
      update(key, null)
      setFileErrors((current) => ({ ...current, [key]: reason.message }))
      URL.revokeObjectURL(previewUrl)
      previewUrls.current.delete(previewUrl)
    }
  }

  async function handleSubmit(event) {
    event.preventDefault()
    if (!canSubmit) return
    setSubmitting(true)
    setSubmitError('')
    try {
      if (isRealApiEnabled) {
        const job = await createBackendJob(form.preImage, form.postImage)
        navigate(`/live-jobs/${job.job_id}`)
        return
      }

      const task = await createTask({
        name: form.name,
        disasterType: form.disasterType,
        disasterLabel: disasterTypes[form.disasterType],
        location: form.location,
        preImageName: form.preImage.name,
        postImageName: form.postImage.name,
        preImagePreview: imageMetadata.preImage.thumbnailUrl,
        postImagePreview: imageMetadata.postImage.thumbnailUrl,
        imageWidth: imageMetadata.preImage.width,
        imageHeight: imageMetadata.preImage.height,
      })
      navigate(`/tasks/${task.id}`)
    } catch (reason) {
      setSubmitError(reason.message)
      setSubmitting(false)
    }
  }

  return (
    <div className="page-stack">
      <PageHeader
        actions={
          <Link className="button button-secondary" to="/tasks">
            <ArrowLeft size={17} />
            返回任务中心
          </Link>
        }
        description={isRealApiEnabled
          ? '上传双时相影像后，将提交到模型电脑并依次运行 Agent1 和 Agent2。'
          : '当前使用本地 Mock；配置后端环境变量后可切换到真实 Agent1 + Agent2。'}
        eyebrow="Create assessment"
        title="新建损毁研判任务"
      />

      <form className="create-grid" onSubmit={handleSubmit}>
        <section className="panel form-panel">
          <div className="section-title">
            <span>01</span>
            <div><strong>任务信息</strong><small>用于标识本次应急研判</small></div>
          </div>
          <label className="form-field">
            <span>任务名称</span>
            <input
              onChange={(event) => update('name', event.target.value)}
              placeholder="例如：长沙县震后建筑损毁评估"
              value={form.name}
            />
          </label>
          <div className="form-row">
            <label className="form-field">
              <span>灾害类型</span>
              <select onChange={(event) => update('disasterType', event.target.value)} value={form.disasterType}>
                {Object.entries(disasterTypes).map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
            </label>
            <label className="form-field">
              <span>研判区域</span>
              <input
                onChange={(event) => update('location', event.target.value)}
                placeholder="省 / 市 / 区县或坐标"
                value={form.location}
              />
            </label>
          </div>
        </section>

        <section className="panel form-panel">
          <div className="section-title">
            <span>02</span>
            <div><strong>双时相遥感影像</strong><small>灾前与灾后影像应覆盖相同区域</small></div>
          </div>
          <div className="upload-grid">
            <UploadField
              error={fileErrors.preImage}
              file={form.preImage}
              label="上传灾前影像"
              metadata={imageMetadata.preImage}
              onChange={(file) => updateImage('preImage', file)}
            />
            <UploadField
              error={fileErrors.postImage}
              file={form.postImage}
              label="上传灾后影像"
              metadata={imageMetadata.postImage}
              onChange={(file) => updateImage('postImage', file)}
            />
          </div>
          <div className="upload-note">
            <ImagePlus size={18} />
            <span>{isRealApiEnabled
              ? '提交前会检查图片格式、可解码性和双时相尺寸一致性。'
              : 'Mock 模式仅保存文件名称；提交前仍会检查图片格式和双时相尺寸。'}</span>
          </div>
        </section>

        <aside className="panel submit-panel">
          <span className="eyebrow">Agent pipeline</span>
          <h2>{isRealApiEnabled ? '提交至真实后端' : '提交后将模拟执行'}</h2>
          <ol>
            <li>Agent1 视觉证据、量化指标与复核标志</li>
            <li>Agent2 英文变化描述</li>
            <li>Agent3 证据可信校验</li>
            <li>Agent4 可信报告生成</li>
          </ol>
          {!canSubmit ? (
            <div className="submit-requirements" role="status">
              <strong>提交前还需要：</strong>
              <ul>{missingRequirements.map((item) => <li key={item}>{item}</li>)}</ul>
            </div>
          ) : (
            <div className="submit-ready"><CheckCircle2 size={16} />输入检查已通过，可以提交任务。</div>
          )}
          {submitError ? <p className="form-error">{submitError}</p> : null}
          <button className="button button-primary button-full" disabled={!canSubmit || submitting} type="submit">
            {submitting ? '正在创建任务…' : isRealApiEnabled ? '开始真实分析' : '提交模拟任务'}
            <ArrowRight size={17} />
          </button>
        </aside>
      </form>
    </div>
  )
}

export default NewTaskPage
