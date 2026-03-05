import { Routes, Route, NavLink } from 'react-router-dom'
import PromptsPage from './pages/PromptsPage'
import SetupPage from './pages/SetupPage'
import TestPage from './pages/TestPage'
import ResultsPage from './pages/ResultsPage'
import SessionsPage from './pages/SessionsPage'

export default function App() {
  return (
    <>
      <nav className="nav">
        <span className="nav-logo">⚡ Prompt Tester</span>
        <div className="nav-links">
          <NavLink to="/" end className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
            Промпты
          </NavLink>
          <NavLink to="/sessions" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
            Сессии
          </NavLink>
          <NavLink to="/setup" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
            Новый тест
          </NavLink>
          <NavLink to="/results" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
            Агрегат
          </NavLink>
        </div>
      </nav>
      <div className="container">
        <Routes>
          <Route path="/" element={<PromptsPage />} />
          <Route path="/prompts" element={<PromptsPage />} />
          <Route path="/sessions" element={<SessionsPage />} />
          <Route path="/setup" element={<SetupPage />} />
          <Route path="/test/:sessionId" element={<TestPage />} />
          <Route path="/results" element={<ResultsPage />} />
          <Route path="/results/:sessionId" element={<ResultsPage />} />
        </Routes>
      </div>
    </>
  )
}
