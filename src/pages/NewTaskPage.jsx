import { ArrowLeft, ArrowRight, CheckCircle2, ImagePlus, UploadCloud } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import PageHeader from '../components/common/PageHeader.jsx'
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
      <span>{file ? `${(file.size / 1024 / 1024).toFixed(2)} MB` : '支持 TIFF、GeoTIFF、PNG 或 JPG'}</span>
      <input
        accept=".tif,.tiff,.png,.jpg,.jpeg,image/*"
        onChange={(event) => onChange(event.target.files?.[0] ?? null)}
        type="file"
      />
    </label>
  )
}

function NewTaskPage() {
  const navigate = useNavigate()
  const [submitting, setSubmitting] = useState(false)
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
    const task = await createTask({
      name: form.name,
      disasterType: form.disasterType,
      disasterLabel: disasterTypes[form.disasterType],
      location: form.location,
      preImageName: form.preImage.name,
      postImageName: form.postImage.name,
    })
    navigate(`/tasks/${task.id}`)
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
        description="录入任务信息和双时相遥感影像，提交后将依次模拟五个 Agent 的协同流程。"
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
            <li>建筑与五级损伤分割</li>
            <li>损伤面积和风险量化</li>
            <li>多模态灾情描述生成</li>
            <li>Claim 与证据可信校验</li>
            <li>Markdown / JSON 报告生成</li>
          </ol>
          <button className="button button-primary button-full" disabled={!canSubmit || submitting} type="submit">
            {submitting ? '正在创建任务…' : '提交研判任务'}
            <ArrowRight size={17} />
          </button>
        </aside>
      </form>
    </div>
  )
}

export default NewTaskPage
