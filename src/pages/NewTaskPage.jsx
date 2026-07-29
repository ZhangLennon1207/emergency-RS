import { ArrowLeft, ArrowRight, CheckCircle2, ImagePlus, UploadCloud } from 'lucide-react'
import { useState } from 'react'
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

function UploadField({ label, file, onChange }) {
  return (
    <label className={`upload-box ${file ? 'has-file' : ''}`}>
      {file ? <CheckCircle2 size={30} /> : <UploadCloud size={30} />}
      <strong>{file ? file.name : label}</strong>
      <span>{file ? `${(file.size / 1024 / 1024).toFixed(2)} MB` : '当前后端支持 PNG、JPG 或 JPEG'}</span>
      <input
        accept=".png,.jpg,.jpeg,image/png,image/jpeg"
        onChange={(event) => onChange(event.target.files?.[0] ?? null)}
        type="file"
      />
    </label>
  )
}

function NewTaskPage() {
  const navigate = useNavigate()
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState('')
  const [form, setForm] = useState({
    name: '',
    disasterType: 'earthquake',
    location: '',
    preImage: null,
    postImage: null,
  })

  const update = (key, value) => setForm((current) => ({ ...current, [key]: value }))
  const canSubmit = form.name && form.location && form.preImage && form.postImage

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
            <UploadField file={form.preImage} label="上传灾前影像" onChange={(file) => update('preImage', file)} />
            <UploadField file={form.postImage} label="上传灾后影像" onChange={(file) => update('postImage', file)} />
          </div>
          <div className="upload-note">
            <ImagePlus size={18} />
            <span>当前仅保存文件名称用于前端演示，不会上传真实影像。</span>
          </div>
        </section>

        <aside className="panel submit-panel">
          <span className="eyebrow">Agent pipeline</span>
          <h2>提交后将模拟执行</h2>
          <ol>
            <li>Agent1 建筑、道路与损伤视觉证据</li>
            <li>Agent1 核心指标和复核标志</li>
            <li>Agent2 英文变化描述</li>
            <li>后续预留 Agent3 校验和 Agent4 报告</li>
          </ol>
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
