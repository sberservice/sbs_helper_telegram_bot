import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api, type ComparisonData, type DocumentContent } from '../api'

interface WaitingProgress {
  generated: number
  total: number
  phase: 'generating' | 'judging'
}

export default function TestPage() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const navigate = useNavigate()
  const sid = Number(sessionId)

  const [comparison, setComparison] = useState<ComparisonData | null>(null)
  const [docContent, setDocContent] = useState<DocumentContent | null>(null)
  const [loading, setLoading] = useState(true)
  const [voting, setVoting] = useState(false)
  const [error, setError] = useState('')
  const [waiting, setWaiting] = useState<WaitingProgress | null>(null)
  const retryTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const loadNext = useCallback(async () => {
    setLoading(true)
    setError('')
    setDocContent(null)
    try {
      const data = await api.getNextComparison(sid)
      setWaiting(null)
      setComparison(data)
      // Автоматически загружаем документ
      if (data.has_more && data.document_id) {
        const doc = await api.getDocumentContent(sid, data.document_id)
        setDocContent(doc)
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      // Пробуем распарсить JSON-объект из HTTPException detail
      let isWaiting = false
      try {
        const parsed = JSON.parse(msg)
        if (parsed.message && parsed.total !== undefined) {
          setWaiting({ generated: parsed.generated, total: parsed.total, phase: parsed.phase || 'generating' })
          isWaiting = true
        }
      } catch {
        // detail — простая строка, проверяем текст
        if (msg.includes('Генерация') || msg.includes('не завершена') || msg.includes('Judge')) {
          setWaiting({ generated: 0, total: 0, phase: 'generating' })
          isWaiting = true
        }
      }
      if (isWaiting) {
        retryTimer.current = setTimeout(loadNext, 3000)
      } else {
        setError(msg)
      }
    } finally {
      setLoading(false)
    }
  }, [sid])

  useEffect(() => {
    loadNext()
    return () => { if (retryTimer.current) clearTimeout(retryTimer.current) }
  }, [loadNext])

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (voting || !comparison?.has_more) return
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return

      switch (e.key) {
        case '1': handleVote('a'); break
        case '2': handleVote('tie'); break
        case '3': handleVote('b'); break
        case 's': case 'S': handleVote('skip'); break
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  })

  const handleVote = async (winner: string) => {
    if (!comparison?.generation_a || !comparison?.generation_b || voting) return
    setVoting(true)
    try {
      await api.vote(sid, {
        generation_a_id: comparison.generation_a.id,
        generation_b_id: comparison.generation_b.id,
        winner,
      })
      loadNext()
    } catch (e) {
      setError(String(e))
    } finally {
      setVoting(false)
    }
  }

  if (waiting) {
    const pct = waiting.total > 0 ? (waiting.generated / waiting.total) * 100 : 0
    const isJudging = waiting.phase === 'judging'
    return (
      <div className="empty-state">
        <div className="empty-state-icon">{isJudging ? '🤖' : '⏳'}</div>
        <h2>{isJudging ? 'LLM\u2011as\u2011Judge оценивает...' : 'Генерация summary...'}</h2>
        <p className="text-dim mt-4">
          {waiting.total > 0
            ? isJudging
              ? `Оценено ${waiting.generated} из ${waiting.total}`
              : `Сгенерировано ${waiting.generated} из ${waiting.total}`
            : 'Подготовка...'}
        </p>
        {waiting.total > 0 && (
          <div className="progress-bar" style={{ width: 300, margin: '16px auto' }}>
            <div className="progress-fill" style={{ width: `${pct}%` }} />
          </div>
        )}
        <p className="text-dim" style={{ fontSize: 12 }}>Страница обновится автоматически</p>
      </div>
    )
  }

  if (loading && !comparison) {
    return <div className="loading">Загрузка...</div>
  }

  if (error && !comparison) {
    return (
      <div className="empty-state">
        <div className="empty-state-icon">❌</div>
        <p>{error}</p>
      </div>
    )
  }

  if (!comparison?.has_more) {
    return (
      <div className="empty-state">
        <div className="empty-state-icon">🎉</div>
        <h2>Тестирование завершено!</h2>
        <p className="mt-4 text-dim">
          Оценено: {comparison?.progress.completed} / {comparison?.progress.total}
        </p>
        <button className="btn btn-primary btn-lg mt-8" onClick={() => navigate(`/results/${sid}`)}>
          Посмотреть результаты
        </button>
      </div>
    )
  }

  const progress = comparison.progress
  const pct = progress.total > 0 ? (progress.completed / progress.total) * 100 : 0

  return (
    <div style={{ height: 'calc(100vh - 60px)', display: 'flex', flexDirection: 'column', padding: '12px 0' }}>
      {/* Progress */}
      <div style={{ flexShrink: 0, marginBottom: 12 }}>
        <div className="flex items-center justify-between mb-4" style={{ marginBottom: 6 }}>
          <span className="text-dim" style={{ fontSize: 12 }}>
            Прогресс: {progress.completed} / {progress.total}
          </span>
          <span className="text-dim" style={{ fontSize: 12 }}>
            Документ: <strong>{comparison.document_name}</strong>
          </span>
        </div>
        <div className="progress-bar">
          <div className="progress-fill" style={{ width: `${pct}%` }} />
        </div>
      </div>

      {/* Split layout */}
      <div className="split-layout" style={{ flex: 1, padding: 0 }}>
        {/* Document panel (left) */}
        <div className="doc-panel split-left">
          <div className="doc-panel-header">
            📄 {docContent?.filename || comparison.document_name}
            {docContent && <span className="text-dim" style={{ marginLeft: 8 }}>({docContent.chunks_count} чанков)</span>}
          </div>
          <div className="doc-panel-content">
            {docContent ? docContent.chunks.join('\n\n---\n\n') : 'Загрузка документа...'}
          </div>
        </div>

        {/* Summaries (right) */}
        <div className="split-right">
          <div className="summary-card" style={{ flex: 1 }}>
            <div className="summary-card-label">Summary A</div>
            <div className="summary-card-text">
              {comparison.generation_a?.summary_text || 'Ошибка генерации'}
            </div>
          </div>

          <div className="summary-card" style={{ flex: 1 }}>
            <div className="summary-card-label">Summary B</div>
            <div className="summary-card-text">
              {comparison.generation_b?.summary_text || 'Ошибка генерации'}
            </div>
          </div>

          {/* Vote buttons */}
          <div className="vote-buttons">
            <button
              className="btn btn-lg"
              onClick={() => handleVote('a')}
              disabled={voting}
              style={{ borderColor: '#6366f1', minWidth: 140 }}
            >
              <span className="kbd">1</span> A лучше
            </button>
            <button
              className="btn btn-lg"
              onClick={() => handleVote('tie')}
              disabled={voting}
              style={{ minWidth: 140 }}
            >
              <span className="kbd">2</span> Одинаково
            </button>
            <button
              className="btn btn-lg"
              onClick={() => handleVote('b')}
              disabled={voting}
              style={{ borderColor: '#8b5cf6', minWidth: 140 }}
            >
              <span className="kbd">3</span> B лучше
            </button>
            <button
              className="btn btn-lg"
              onClick={() => handleVote('skip')}
              disabled={voting}
              style={{ minWidth: 120, opacity: 0.7 }}
            >
              <span className="kbd">S</span> Пропустить
            </button>
          </div>
        </div>
      </div>

      {error && (
        <div className="card" style={{ background: 'rgba(239,68,68,0.1)', borderColor: 'var(--danger)', flexShrink: 0 }}>
          {error}
        </div>
      )}
    </div>
  )
}
