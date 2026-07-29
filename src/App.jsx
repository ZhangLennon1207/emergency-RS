import { HashRouter, Navigate, Route, Routes } from 'react-router-dom'
import AppShell from './components/layout/AppShell.jsx'
import EvidencePage from './pages/EvidencePage.jsx'
import NewTaskPage from './pages/NewTaskPage.jsx'
import OverviewPage from './pages/OverviewPage.jsx'
import ReportsPage from './pages/ReportsPage.jsx'
import TaskDetailPage from './pages/TaskDetailPage.jsx'
import TasksPage from './pages/TasksPage.jsx'
import './App.css'

function App() {
  return (
    <HashRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<Navigate replace to="/overview" />} />
          <Route path="/overview" element={<OverviewPage />} />
          <Route path="/tasks" element={<TasksPage />} />
          <Route path="/tasks/new" element={<NewTaskPage />} />
          <Route path="/tasks/:taskId" element={<TaskDetailPage />} />
          <Route path="/tasks/:taskId/evidence" element={<EvidencePage />} />
          <Route path="/tasks/:taskId/report" element={<ReportsPage />} />
          <Route path="/evidence" element={<EvidencePage />} />
          <Route path="/reports" element={<ReportsPage />} />
          <Route path="*" element={<Navigate replace to="/overview" />} />
        </Route>
      </Routes>
    </HashRouter>
  )
}

export default App
