import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api, type Prompt } from '../api'

export default function SetupPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const cloneSessionId = searchParams.get('clone')
  const [prompts, setPrompts] = useState<Prompt[]>([])
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [name, setName] = useState('')
  const [docCount, setDocCount] = useState(10)
  const [judgeMode, setJudgeMode] = useState('human')
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState('')
  const [cloneInfo, setCloneInfo] = useState('')

  useEffect(() => {
    const init = async () => {
      const allPrompts = await api.listPrompts(true)
      setPrompts(allPrompts)

      // Клонирование настроек из предыдущей сессии
      if (cloneSessionId) {
        try {
          const session = await api.getSession(Number(cloneSessionId))
          const snapshotIds = session.prompt_ids_snapshot || []
          const activeIds = new Set(allPrompts.map(p => p.id))
          const validIds = snapshotIds.filter((id: number) => activeIds.has(id))
          setSelectedIds(new Set(validIds))
          setJudgeMode(session.judge_mode || 'human')
          const docIds = session.document_ids || []
          setDocCount(docIds.length > 0 ? docIds.length : 10)
          setName(`${session.name} (копия)`)

          const skipped = snapshotIds.length - validIds.length
          if (skipped > 0) {
            setCloneInfo(`Настройки скопированы из сессии #${cloneSessionId}. ${skipped} промптов недоступны (архивированы).`)
          } else {
            setCloneInfo(`Настройки скопированы из сессии #${cloneSessionId}`)
          }
        } catch {
          setError('Не удалось загрузить сессию для клонирования')
        }
      }

      setLoading(false)
    }
    init()
  }, [cloneSessionId])

  const togglePrompt = (id: number) => {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const handleStart = async () => {
    if (selectedIds.size < 2) {
      setError('Выберите минимум 2 промпта')
      return
    }
    if (!name.trim()) {
      setError('Введите название сессии')
      return
    }

    setCreating(true)
    setError('')
    try {
      const result = await api.createSession({
        name: name.trim(),
        prompt_ids: Array.from(selectedIds),
        document_count: docCount,
        judge_mode: judgeMode,
      })
      navigate(`/test/${result.id}`)
    } catch (e) {
      setError(`Ошибка: ${e}`)
    } finally {
      setCreating(false)
    }
  }

  const numPairs = selectedIds.size >= 2
    ? (selectedIds.size * (selectedIds.size - 1)) / 2
    : 0
  const totalComparisons = numPairs * docCount

  if (loading) return <div className="loading">Загрузка промптов...</div>

  return (
    <>
      <div className="page-header">
        <h1 className="page-title">{cloneSessionId ? 'Клонировать тест' : 'Новый тест'}</h1>
      </div>

      {cloneInfo && (
        <div className="card" style={{ background: 'rgba(99,102,241,0.08)', marginBottom: 16 }}>
          🔄 {cloneInfo}
        </div>
      )}

      {prompts.length < 2 ? (
        <div className="empty-state">
          <div className="empty-state-icon">⚠️</div>
          <p>Создайте минимум 2 пары промптов перед запуском теста.</p>
          <button className="btn btn-primary mt-4" onClick={() => navigate('/')}>
            Перейти к промптам
          </button>
        </div>
      ) : (
        <>
          <div className="card">
            <h3 className="card-title mb-4">Настройки сессии</h3>

            <div className="form-group">
              <label className="form-label">Название сессии</label>
              <input
                className="form-input"
                placeholder="Тест промптов v2 vs v3"
                value={name}
                onChange={e => setName(e.target.value)}
              />
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
              <div className="form-group">
                <label className="form-label">Документов: {docCount}</label>
                <input
                  type="range"
                  min={2}
                  max={50}
                  value={docCount}
                  onChange={e => setDocCount(+e.target.value)}
                  style={{ width: '100%' }}
                />
                <div className="form-hint">Стратифицированная выборка: малые, средние, крупные документы</div>
              </div>

              <div className="form-group">
                <label className="form-label">Режим оценки</label>
                <select className="form-select" value={judgeMode} onChange={e => setJudgeMode(e.target.value)}>
                  <option value="human">Только ручная</option>
                  <option value="llm">Только LLM-judge</option>
                  <option value="both">Ручная + LLM</option>
                </select>
              </div>
            </div>
          </div>

          <div className="card">
            <div className="card-header">
              <h3 className="card-title">Выберите промпты для сравнения</h3>
              <span className="text-dim">Выбрано: {selectedIds.size} (мин. 2)</span>
            </div>

            <table className="table">
              <thead>
                <tr>
                  <th style={{ width: 40 }}></th>
                  <th>Название</th>
                  <th>Модель</th>
                  <th>Temp</th>
                  <th>System prompt (начало)</th>
                </tr>
              </thead>
              <tbody>
                {prompts.map(p => (
                  <tr key={p.id} onClick={() => togglePrompt(p.id)} style={{ cursor: 'pointer' }}>
                    <td>
                      <input
                        type="checkbox"
                        checked={selectedIds.has(p.id)}
                        onChange={() => togglePrompt(p.id)}
                      />
                    </td>
                    <td><strong>{p.label}</strong></td>
                    <td><span className="badge badge-info">{p.model_name || 'default'}</span></td>
                    <td>{p.temperature != null ? p.temperature.toFixed(1) : '—'}</td>
                    <td className="text-dim" style={{ maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {p.system_prompt_template.slice(0, 80)}...
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {selectedIds.size >= 2 && (
            <div className="card" style={{ background: 'rgba(99,102,241,0.08)' }}>
              <div className="flex items-center justify-between">
                <div>
                  <strong>Итого:</strong> {totalComparisons} попарных сравнений
                  ({docCount} документов × {numPairs} пар промптов)
                </div>
                <button
                  className="btn btn-primary btn-lg"
                  onClick={handleStart}
                  disabled={creating}
                >
                  {creating ? 'Создание...' : '🚀 Запустить тест'}
                </button>
              </div>
            </div>
          )}

          {error && (
            <div className="card" style={{ background: 'rgba(239,68,68,0.1)', borderColor: 'var(--danger)' }}>
              {error}
            </div>
          )}
        </>
      )}
    </>
  )
}
