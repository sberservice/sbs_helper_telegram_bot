/**
 * Вкладка «Песочница поиска» — гибридный поиск по Q&A-корпусу.
 */

import { useState } from 'react'
import { api, type GKSearchAnswerPreview, type GKSearchProgressStage, type GKSearchResult } from '../../api'

export default function SearchTab() {
  const [query, setQuery] = useState('')
  const [topK, setTopK] = useState(10)
  const [results, setResults] = useState<GKSearchResult[]>([])
  const [answerPreview, setAnswerPreview] = useState<GKSearchAnswerPreview | null>(null)
  const [searching, setSearching] = useState(false)
  const [error, setError] = useState('')
  const [searched, setSearched] = useState(false)
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [progressStages, setProgressStages] = useState<GKSearchProgressStage[]>([])
  const [searchDurationMs, setSearchDurationMs] = useState<number | null>(null)

  const doSearch = async () => {
    if (!query.trim()) return
    setSearching(true)
    setError('')
    setProgressStages([
      { key: 'init', label: 'Подготовка запроса', status: 'done' },
      { key: 'retrieve', label: 'Гибридный поиск по Q&A', status: 'running' },
      { key: 'answer', label: 'Генерация итогового ответа', status: 'pending' },
    ])
    setSearchDurationMs(null)
    try {
      const res = await api.gkSearch(query.trim(), topK)
      setResults(res.results)
      setAnswerPreview(res.answer_preview)
      setProgressStages(res.progress_stages || [])
      setSearchDurationMs(typeof res.duration_ms === 'number' ? res.duration_ms : null)
      setSearched(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка поиска')
      setProgressStages(prev => prev.map(stage => (
        stage.status === 'running' ? { ...stage, status: 'error' } : stage
      )))
    } finally {
      setSearching(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      doSearch()
    }
  }

  return (
    <div className="gk-search-tab">
      {error && <div className="alert alert-danger">{error}</div>}

      {progressStages.length > 0 && (
        <div className="card" style={{ marginBottom: 12, padding: 12 }}>
          <div className="text-dim" style={{ marginBottom: 8 }}>
            Прогресс поиска{searchDurationMs != null ? ` · ${searchDurationMs} мс` : ''}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {progressStages.map(stage => (
              <div key={stage.key} style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                <span>{stage.label}</span>
                <span className="text-dim">
                  {stage.status === 'done' ? '✓ выполнено' :
                    stage.status === 'running' ? '⏳ выполняется' :
                      stage.status === 'error' ? '✗ ошибка' :
                        stage.status === 'skipped' ? '— пропущено' : '… ожидает'}
                  {typeof stage.duration_ms === 'number' ? ` (${stage.duration_ms} мс)` : ''}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="search-form">
        <div className="search-form-row">
          <input
            type="text"
            className="input"
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Введите поисковый запрос..."
            maxLength={1000}
          />
          <select className="input input-sm search-topk-select" value={topK} onChange={e => setTopK(Number(e.target.value))}>
            <option value={5}>Top 5</option>
            <option value={10}>Top 10</option>
            <option value={20}>Top 20</option>
            <option value={50}>Top 50</option>
          </select>
          <button className="btn btn-primary" onClick={doSearch} disabled={searching || !query.trim()}>
            {searching ? '...' : '🔍 Поиск'}
          </button>
        </div>
      </div>

      {searched && answerPreview && (
        <div className="card" style={{ marginTop: 16 }}>
          <div className="responder-entry-header" style={{ marginBottom: 8 }}>
            <strong>Ответ, который получил бы пользователь</strong>
            {answerPreview.confidence != null && (
              <span className="pair-confidence">{(answerPreview.confidence * 100).toFixed(0)}%</span>
            )}
            <span className="text-dim">
              {answerPreview.would_send
                ? 'Будет отправлено'
                : `Не будет отправлено: порог ${(answerPreview.threshold * 100).toFixed(0)}%`}
            </span>
          </div>

          {answerPreview.final_answer_text ? (
            <pre style={{ whiteSpace: 'pre-wrap', margin: 0, fontFamily: 'inherit' }}>
              {answerPreview.final_answer_text}
            </pre>
          ) : (
            <p style={{ margin: 0 }}>Автоответчик не смог сформировать отправляемый ответ.</p>
          )}
        </div>
      )}

      {/* Результаты */}
      {searched && results.length === 0 && (
        <div className="card empty-state" style={{ marginTop: 16 }}><p>Ничего не найдено</p></div>
      )}

      {results.length > 0 && (
        <div className="search-results" style={{ marginTop: 16 }}>
          <div className="text-dim" style={{ marginBottom: 8 }}>Найдено: {results.length}</div>
          {results.map((r, i) => (
            <div
              key={`${r.qa_pair_id}-${i}`}
              className="card search-result-card"
              onClick={() => setExpandedId(expandedId === i ? null : i)}
              style={{ marginBottom: 8, cursor: 'pointer' }}
            >
              <div className="responder-entry-header">
                <span className="pair-id">#{r.qa_pair_id}</span>
                <span className="pair-confidence">{(r.confidence * 100).toFixed(0)}%</span>
                <span className="text-dim" title="RRF Score">RRF: {r.rrf_score.toFixed(4)}</span>
                <span className="text-dim" title="BM25 Score">BM25: {r.bm25_score.toFixed(4)}</span>
                <span className="text-dim" title="Vector Score">Vec: {r.vector_score.toFixed(4)}</span>
              </div>
              <div className="pair-question">
                <strong>Q:</strong> {expandedId === i ? r.question : r.question.slice(0, 200) + (r.question.length > 200 ? '...' : '')}
              </div>
              {expandedId === i && (
                <div className="pair-answer" style={{ marginTop: 6 }}>
                  <strong>A:</strong> {r.answer}
                  <div className="text-dim" style={{ marginTop: 6 }}>
                    <div>
                      <strong>Fullness:</strong> {r.fullness != null ? r.fullness.toFixed(3) : '—'}
                    </div>
                    <div>
                      <strong>Confidence reason:</strong> {r.confidence_reason?.trim() ? r.confidence_reason : '—'}
                    </div>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
