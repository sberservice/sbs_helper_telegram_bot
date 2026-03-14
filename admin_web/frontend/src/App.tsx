/**
 * Корневой компонент SBS Archie Admin Web.
 * Маршрутизация + навигация.
 */

import { Routes, Route, NavLink, Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from './auth'
import ProtectedRoute from './components/ProtectedRoute'
import LoginPage from './pages/LoginPage'
import DashboardPage from './pages/DashboardPage'
import GKKnowledgePage from './pages/GKKnowledgePage'
import ProcessManagerPage from './pages/ProcessManagerPage'
import HelperPage from './pages/HelperPage.tsx'
import RagPage from './pages/RagPage'

export default function App() {
  const { user, loading, logout } = useAuth()
  const navigate = useNavigate()

  const handleLogout = async () => {
    await logout()
    navigate('/login', { replace: true })
  }

  if (loading) {
    return <div className="loading-screen">Загрузка...</div>
  }

  return (
    <div className="app">
      {/* Навигация (только для авторизованных) */}
      {user && (
        <nav className="nav">
          <span className="nav-logo">🏗️ SBS Archie Admin</span>
          <div className="nav-links">
            <NavLink to="/" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`} end>
              Модули
            </NavLink>
            <NavLink to="/gk" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
              🧠 Group Knowledge
            </NavLink>
            <NavLink to="/processes" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
              ⚙️ Процессы
            </NavLink>
            <NavLink to="/helper" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
              🆘 Helper
            </NavLink>
            <NavLink to="/rag" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
              🧩 RAG
            </NavLink>
          </div>
          <div className="nav-spacer" />
          <div className="nav-user">
            <span className="nav-user-name">
              {user.telegram_first_name || user.telegram_username || `ID ${user.telegram_id}`}
            </span>
            <span className="badge badge-dim">{user.role}</span>
            <button className="btn btn-sm btn-logout" onClick={handleLogout}>Выйти</button>
          </div>
        </nav>
      )}

      <main className="main-content container">
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <DashboardPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/gk"
            element={
              <ProtectedRoute moduleKey="gk_knowledge">
                <GKKnowledgePage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/processes"
            element={
              <ProtectedRoute moduleKey="process_manager">
                <ProcessManagerPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/helper"
            element={
              <ProtectedRoute moduleKey="process_manager">
                <HelperPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/rag"
            element={
              <ProtectedRoute moduleKey="gk_knowledge">
                <RagPage />
              </ProtectedRoute>
            }
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  )
}
