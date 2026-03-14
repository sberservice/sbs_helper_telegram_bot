/**
 * Дашборд — главная страница после авторизации.
 * Показывает те же разделы, что и верхнее меню.
 */

import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth'

const DASHBOARD_BUTTONS = [
  { key: 'gk_knowledge', icon: '🧠', title: 'Group Knowledge', subtitle: 'Аналитика и инструменты GK', route: '/gk' },
  { key: 'process_manager', icon: '⚙️', title: 'Процессы', subtitle: 'Управление демонами и скриптами', route: '/processes' },
  { key: 'process_manager', icon: '🆘', title: 'Helper', subtitle: 'Настройки The Helper', route: '/helper' },
  { key: 'gk_knowledge', icon: '🧩', title: 'RAG', subtitle: 'Prompt Tester и RAG-инструменты', route: '/rag' },
] as const

export default function DashboardPage() {
  const { user, hasPermission } = useAuth()
  const navigate = useNavigate()
  const visibleButtons = DASHBOARD_BUTTONS.filter((button) =>
    hasPermission(button.key, 'view'),
  )

  return (
    <div className="dashboard-page">
      <div className="page-header">
        <h1>SBS Archie · Админ-панель</h1>
        <p className="text-dim">
          {user?.telegram_first_name || user?.telegram_username || 'Пользователь'}
          {user?.role && <span className="badge badge-dim" style={{ marginLeft: 8 }}>{user.role}</span>}
        </p>
      </div>

      {visibleButtons.length === 0 ? (
        <div className="card empty-state">
          <p>Нет доступных разделов.</p>
          <p className="text-dim">Обратитесь к администратору для получения доступа.</p>
        </div>
      ) : (
        <div className="modules-grid">
          {visibleButtons.map(button => (
            <div
              key={`${button.route}-${button.title}`}
              className="module-card"
              onClick={() => navigate(button.route)}
            >
              <div className="module-icon">{button.icon}</div>
              <div className="module-info">
                <h3>{button.title}</h3>
                <p className="text-dim">{button.subtitle}</p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
