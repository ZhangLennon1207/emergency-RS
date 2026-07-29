import {
  Activity,
  Bot,
  FileBarChart2,
  Layers3,
  ListChecks,
  PanelLeftClose,
  PanelLeftOpen,
  Radar,
  Siren,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'

const SIDEBAR_STORAGE_KEY = 'emergency-rs-sidebar-collapsed'

const navigation = [
  { to: '/overview', label: '态势总览', icon: Radar },
  { to: '/tasks', label: '任务中心', icon: ListChecks },
  { to: '/tasks/new', label: '智能研判', icon: Bot },
  { to: '/evidence', label: '证据校验', icon: Layers3 },
  { to: '/reports', label: '报告中心', icon: FileBarChart2 },
]

function AppShell() {
  const [collapsed, setCollapsed] = useState(
    () => window.localStorage.getItem(SIDEBAR_STORAGE_KEY) === 'true',
  )

  useEffect(() => {
    window.localStorage.setItem(SIDEBAR_STORAGE_KEY, String(collapsed))
  }, [collapsed])

  return (
    <div className={`app-shell ${collapsed ? 'sidebar-collapsed' : ''}`}>
      <aside className="sidebar" id="primary-sidebar">
        <div className="brand">
          <div className="brand-mark">
            <Siren size={20} />
          </div>
          <div className="brand-copy">
            <span>Emergency RS</span>
            <strong>可信遥感研判平台</strong>
          </div>
        </div>

        <nav className="sidebar-nav" aria-label="主导航">
          {navigation.map(({ to, label, icon: Icon }) => (
            <NavLink
              className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
              data-label={label}
              key={to}
              to={to}
            >
              <Icon size={19} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-status">
          <div className="status-line">
            <Activity size={16} />
            <span>演示环境运行中</span>
          </div>
          <p>当前使用 Mock 数据，后续可直接切换 FastAPI 服务。</p>
        </div>

        <button
          aria-controls="primary-sidebar"
          aria-expanded={!collapsed}
          aria-label={collapsed ? '展开侧边栏' : '收起侧边栏'}
          className="sidebar-toggle"
          onClick={() => setCollapsed((value) => !value)}
          type="button"
        >
          {collapsed ? <PanelLeftOpen size={19} /> : <PanelLeftClose size={19} />}
          <span>{collapsed ? '展开导航' : '收起导航'}</span>
        </button>
      </aside>

      <div className="workspace">
        <header className="topbar">
          <div>
            <span className="eyebrow">Multi-agent damage assessment</span>
            <strong>可信遥感损毁评估与应急研判多智能体系统</strong>
          </div>
          <div className="system-state">
            <i />
            Agent 服务待接入
          </div>
        </header>
        <main className="page-container">
          <Outlet />
        </main>
      </div>
    </div>
  )
}

export default AppShell
