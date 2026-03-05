import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api, type SessionResultsData, type AggregateResultsData, type PromptResult } from '../api'

interface PromptPreview {
  label: string
  system_prompt_template: string
  user_message: string
  model_name: string | null
  temperature: number | null
}

export default function ResultsPage() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const [sessionResults, setSessionResults] = useState<SessionResultsData | null>(null)
  const [aggregateResults, setAggregateResults] = useState<AggregateResultsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [expandedDocs, setExpandedDocs] = useState<Set<number>>(new Set())
  const [previewPrompt, setPreviewPrompt] = useState<PromptPreview | null>(null)

  useEffect(() => {
    setLoading(true)
    if (sessionId) {
      api.getSessionResults(Number(sessionId))
        .then(setSessionResults)
        .finally(() => setLoading(false))
    } else {
      api.getAggregateResults()
        .then(setAggregateResults)
        .finally(() => setLoading(false))
    }
  }, [sessionId])

  const toggleDoc = (docId: number) => {
    setExpandedDocs(prev => {
      const next = new Set(prev)
      if (next.has(docId)) next.delete(docId)
      else next.add(docId)
      return next
    })
  }

  const handlePromptClick = async (promptId: number) => {
    try {
      const p = await api.getPrompt(promptId)
      setPreviewPrompt({
        label: p.label,
        system_prompt_template: p.system_prompt_template,
        user_message: p.user_message,
        model_name: p.model_name,
        temperature: p.temperature,
      })
    } catch {
      // Промпт мог быть удалён — показываем из snapshot если есть
      if (sessionResults) {
        const cfg = sessionResults.human_results.find(r => r.prompt_id === promptId)
          || sessionResults.llm_results.find(r => r.prompt_id === promptId)
        if (cfg) {
          setPreviewPrompt({
            label: cfg.label,
            system_prompt_template: '(промпт недоступен)',
            user_message: '(промпт недоступен)',
            model_name: cfg.model_name,
            temperature: cfg.temperature,
          })
        }
      }
    }
  }

  if (loading) return <div className="loading">Загрузка результатов...</div>

  // Aggregate view
  if (!sessionId) {
    if (!aggregateResults || aggregateResults.prompt_results.length === 0) {
      return (
        <div className="empty-state">
          <div className="empty-state-icon">📊</div>
          <p>Нет данных для агрегации. Проведите хотя бы одну тестовую сессию.</p>
        </div>
      )
    }

    return (
      <>
        <div className="page-header">
          <h1 className="page-title">Агрегированные результаты</h1>
          <span className="text-dim">
            {aggregateResults.sessions_count} сессий, {aggregateResults.total_votes} голосов
          </span>
        </div>
        <ResultsTable results={aggregateResults.prompt_results} title="Все промпты" onPromptClick={handlePromptClick} />
      </>
    )
  }

  // Session view
  if (!sessionResults) {
    return <div className="empty-state">Результаты не найдены</div>
  }

  return (
    <>
      <div className="page-header">
        <h1 className="page-title">Результаты: {sessionResults.session_name}</h1>
        <span className={`badge ${sessionResults.status === 'completed' ? 'badge-success' : 'badge-warning'}`}>
          {sessionResults.status}
        </span>
      </div>

      {sessionResults.human_results.length > 0 && (
        <ResultsTable results={sessionResults.human_results} title="Оценка человека 👤" onPromptClick={handlePromptClick} />
      )}

      {sessionResults.llm_results.length > 0 && (
        <ResultsTable results={sessionResults.llm_results} title="Оценка LLM 🤖" onPromptClick={handlePromptClick} />
      )}

      {/* Document breakdown */}
      {sessionResults.document_breakdown.length > 0 && (
        <div className="card mt-4">
          <h3 className="card-title mb-4">Разбивка по документам</h3>
          {sessionResults.document_breakdown.map(doc => (
            <div key={doc.document_id} style={{ marginBottom: 8 }}>
              <button
                className="btn"
                onClick={() => toggleDoc(doc.document_id)}
                style={{ width: '100%', justifyContent: 'flex-start' }}
              >
                {expandedDocs.has(doc.document_id) ? '▼' : '▶'} Документ #{doc.document_id}
                <span className="text-dim" style={{ marginLeft: 8 }}>
                  ({doc.comparisons.length} сравнений)
                </span>
              </button>
              {expandedDocs.has(doc.document_id) && (
                <table className="table" style={{ marginTop: 4 }}>
                  <thead>
                    <tr>
                      <th>Промпт A</th>
                      <th>Промпт B</th>
                      <th>Победитель</th>
                    </tr>
                  </thead>
                  <tbody>
                    {doc.comparisons.map((c, i) => (
                      <tr key={i}>
                        <td>{c.prompt_a_label}</td>
                        <td>{c.prompt_b_label}</td>
                        <td>
                          {c.winner === 'a' && <span className="badge badge-success">{c.prompt_a_label}</span>}
                          {c.winner === 'b' && <span className="badge badge-success">{c.prompt_b_label}</span>}
                          {c.winner === 'tie' && <span className="badge badge-info">Ничья</span>}
                          {c.winner === 'skip' && <span className="badge" style={{ opacity: 0.5 }}>Пропуск</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Prompt preview modal */}
      {previewPrompt && (
        <div className="modal-overlay" onClick={() => setPreviewPrompt(null)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h2 className="modal-title">Промпт: {previewPrompt.label}</h2>
              <button className="modal-close" onClick={() => setPreviewPrompt(null)}>&times;</button>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
              <div>
                <span className="text-dim" style={{ fontSize: 12 }}>Модель:</span>{' '}
                <span className="badge badge-info">{previewPrompt.model_name || 'default'}</span>
              </div>
              <div>
                <span className="text-dim" style={{ fontSize: 12 }}>Temperature:</span>{' '}
                {previewPrompt.temperature != null ? previewPrompt.temperature.toFixed(1) : '—'}
              </div>
            </div>
            <div className="form-group">
              <label className="form-label">System Prompt Template</label>
              <pre style={{ background: 'var(--bg)', padding: 12, borderRadius: 'var(--radius)', whiteSpace: 'pre-wrap', fontSize: 12, maxHeight: 300, overflow: 'auto' }}>
                {previewPrompt.system_prompt_template}
              </pre>
            </div>
            <div className="form-group">
              <label className="form-label">User Message</label>
              <pre style={{ background: 'var(--bg)', padding: 12, borderRadius: 'var(--radius)', whiteSpace: 'pre-wrap', fontSize: 12 }}>
                {previewPrompt.user_message}
              </pre>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

function ResultsTable({ results, title, onPromptClick }: { results: PromptResult[]; title: string; onPromptClick?: (id: number) => void }) {
  return (
    <div className="card">
      <h3 className="card-title mb-4">{title}</h3>
      <table className="table">
        <thead>
          <tr>
            <th>#</th>
            <th>Промпт</th>
            <th>Модель</th>
            <th>Temp</th>
            <th>Побед</th>
            <th>Поражений</th>
            <th>Ничьих</th>
            <th>Пропусков</th>
            <th>Win Rate</th>
            <th>Elo</th>
          </tr>
        </thead>
        <tbody>
          {results.map((r, i) => (
            <tr key={r.prompt_id}>
              <td>
                {i === 0 ? '🥇' : i === 1 ? '🥈' : i === 2 ? '🥉' : i + 1}
              </td>
              <td>
                <strong
                  style={{ cursor: 'pointer', textDecoration: 'underline', textDecorationStyle: 'dotted' }}
                  onClick={() => onPromptClick?.(r.prompt_id)}
                  title="Нажмите для предпросмотра"
                >
                  {r.label}
                </strong>
              </td>
              <td><span className="badge badge-info">{r.model_name || 'default'}</span></td>
              <td>{r.temperature != null ? r.temperature.toFixed(1) : '—'}</td>
              <td style={{ color: 'var(--success)' }}>{r.wins}</td>
              <td style={{ color: 'var(--danger)' }}>{r.losses}</td>
              <td>{r.ties}</td>
              <td className="text-dim">{r.skips}</td>
              <td>
                <strong>{(r.win_rate * 100).toFixed(1)}%</strong>
              </td>
              <td>
                <strong style={{ color: r.elo >= 1500 ? 'var(--success)' : 'var(--danger)' }}>
                  {r.elo.toFixed(0)}
                </strong>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
