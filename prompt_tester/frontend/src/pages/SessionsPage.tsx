import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, type SessionListItem } from '../api'

export default function SessionsPage() {
  const navigate = useNavigate()
  const [sessions, setSessions] = useState<SessionListItem[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.listSessions().then(setSessions).finally(() => setLoading(false))
  }, [])

  const statusBadge = (status: string) => {
    switch (status) {
      case 'generating': return <span className="badge badge-warning">Генерация</span>
      case 'judging': return <span className="badge badge-warning">LLM оценка</span>
      case 'in_progress': return <span className="badge badge-info">В процессе</span>
      case 'completed': return <span className="badge badge-success">Завершена</span>
      case 'abandoned': return <span className="badge badge-danger">Отменена</span>
      default: return <span className="badge">{status}</span>
    }
  }

  if (loading) return <div className="loading">Загрузка сессий...</div>

  return (
    <>
      <div className="page-header">
        <h1 className="page-title">Тестовые сессии</h1>
        <button className="btn btn-primary" onClick={() => navigate('/setup')}>
          + Новый тест
        </button>
      </div>

      {sessions.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-icon">🧪</div>
          <p>Нет тестовых сессий. Создайте промпты и запустите тест.</p>
        </div>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Название</th>
              <th>Статус</th>
              <th>Промптов</th>
              <th>Документов</th>
              <th>Прогресс</th>
              <th>Режим</th>
              <th>Создана</th>
              <th>Действия</th>
            </tr>
          </thead>
          <tbody>
            {sessions.map(s => {
              const pct = s.total_comparisons > 0
                ? Math.round((s.completed_comparisons / s.total_comparisons) * 100)
                : 0

              return (
                <tr key={s.id}>
                  <td>{s.id}</td>
                  <td><strong>{s.name}</strong></td>
                  <td>{statusBadge(s.status)}</td>
                  <td>{s.prompt_count}</td>
                  <td>{s.document_count}</td>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <div className="progress-bar" style={{ width: 80 }}>
                        <div className="progress-fill" style={{ width: `${pct}%` }} />
                      </div>
                      <span className="text-dim" style={{ fontSize: 12 }}>
                        {s.completed_comparisons}/{s.total_comparisons}
                      </span>
                    </div>
                  </td>
                  <td>
                    <span className="badge badge-info">{s.judge_mode}</span>
                  </td>
                  <td className="text-dim">{new Date(s.created_at).toLocaleDateString('ru')}</td>
                  <td>
                    <div className="btn-group">
                      {s.status === 'in_progress' && (
                        <button className="btn btn-primary" onClick={() => navigate(`/test/${s.id}`)}>
                          ▶ Продолжить
                        </button>
                      )}
                      {(s.status === 'completed' || s.completed_comparisons > 0) && (
                        <button className="btn" onClick={() => navigate(`/results/${s.id}`)}>
                          📊 Результаты
                        </button>
                      )}
                      <button className="btn" onClick={() => navigate(`/setup?clone=${s.id}`)} title="Клонировать настройки">
                        🔄 Клонировать
                      </button>
                      {s.status === 'generating' && (
                        <button className="btn" disabled>
                          ⏳ Генерация...
                        </button>
                      )}
                      {s.status === 'judging' && (
                        <button className="btn" disabled>
                          ⏳ LLM оценка...
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
    </>
  )
}
