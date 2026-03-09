/**
 * Дашборд — главная страница после авторизации.
 * Показывает доступные модули в виде карточек.
 */

import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, type ModuleInfo } from '../api'
import { useAuth } from '../auth'

/* Маршруты модулей (фронтенд). */
const MODULE_ROUTES: Record<string, string> = {
  gk_knowledge: '/gk',
  process_manager: '/processes',
  prompt_tester: '/prompt-tester',
}

export default function DashboardPage() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [modules, setModules] = useState<ModuleInfo[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.listModules()
      .then(setModules)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="page-center">
        <div className="loading-text">Загрузка...</div>
      </div>
    )
  }

  return (
    <div className="dashboard-page">
      <div className="page-header">
        <h1>SBS Archie · Админ-панель</h1>
        <p className="text-dim">
          {user?.telegram_first_name || user?.telegram_username || 'Пользователь'}
          {user?.role && <span className="badge badge-dim" style={{ marginLeft: 8 }}>{user.role}</span>}
        </p>
      </div>

      {modules.length === 0 ? (
        <div className="card empty-state">
          <p>Нет доступных модулей.</p>
          <p className="text-dim">Обратитесь к администратору для получения доступа.</p>
        </div>
      ) : (
        <div className="modules-grid">
          {modules.map(mod => {
            const route = MODULE_ROUTES[mod.key] || `/${mod.key}`
            return (
              <div
                key={mod.key}
                className="module-card"
                onClick={() => {
                  if (mod.external_url) {
                    window.location.assign(mod.external_url)
                  } else {
                    navigate(route)
                  }
                }}
              >
                <div className="module-icon">{mod.icon}</div>
                <div className="module-info">
                  <h3>{mod.name}</h3>
                  {mod.description && <p className="text-dim">{mod.description}</p>}
                </div>
                {mod.can_edit && <span className="badge badge-success">edit</span>}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
