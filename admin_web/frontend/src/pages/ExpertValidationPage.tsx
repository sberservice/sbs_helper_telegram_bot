/**
 * Страница экспертной валидации Q&A-пар Group Knowledge.
 *
 * Основные функции:
 * - Просмотр Q&A-пар с фильтрацией и пагинацией
 * - Реконструкция и просмотр цепочки сообщений
 * - Валидация через hotkeys: Y (одобрить), N (отклонить), S (пропустить)
 * - Статистика валидации
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import {
  api,
  type QAPairDetail,
  type ExpertValidationStats,
  type ChainMessage,
  type GroupInfo,
} from '../api'
import { useAuth } from '../auth'

export default function ExpertValidationPage() {
  const { user, hasPermission } = useAuth()
  const canEdit = hasPermission('expert_validation', 'edit')

  // Данные
  const [pairs, setPairs] = useState<QAPairDetail[]>([])
  const [total, setTotal] = useState(0)
  const [stats, setStats] = useState<ExpertValidationStats | null>(null)
  const [groups, setGroups] = useState<GroupInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  // Текущая пара (для детального просмотра)
  const [currentPair, setCurrentPair] = useState<QAPairDetail | null>(null)
  const [currentIndex, setCurrentIndex] = useState(0)
  const [chainExpanded, setChainExpanded] = useState(false)
  const [comment, setComment] = useState('')
  const [validating, setValidating] = useState(false)
  const [lastAction, setLastAction] = useState<{verdict: string; pairId: number} | null>(null)
  const [pendingVerdict, setPendingVerdict] = useState<{ verdict: 'approved' | 'rejected'; expiresAt: number } | null>(null)

  // Фильтры
  const [page, setPage] = useState(1)
  const [pageSize] = useState(20)
  const [groupId, setGroupId] = useState<number | null>(null)
  const [extractionType, setExtractionType] = useState<string | null>(null)
  const [questionTextInput, setQuestionTextInput] = useState('')
  const [questionText, setQuestionText] = useState<string | null>(null)
  const [expertStatus, setExpertStatus] = useState<string | null>('unvalidated')
  const [minConfidence, setMinConfidence] = useState<number | null>(null)
  const [sortBy, setSortBy] = useState('created_at')
  const [sortOrder, setSortOrder] = useState('desc')

  // Режим: list | review
  const [mode, setMode] = useState<'list' | 'review'>('list')

  const reviewContainerRef = useRef<HTMLDivElement>(null)

  // Загрузка списка пар
  const loadPairs = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const result = await api.listPairs({
        page,
        page_size: pageSize,
        group_id: groupId,
        extraction_type: extractionType,
        question_text: questionText,
        expert_status: expertStatus,
        min_confidence: minConfidence,
        sort_by: sortBy,
        sort_order: sortOrder,
      })
      setPairs(result.pairs)
      setTotal(result.total)
      setStats(result.stats)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка загрузки')
    } finally {
      setLoading(false)
    }
  }, [page, pageSize, groupId, extractionType, questionText, expertStatus, minConfidence, sortBy, sortOrder])

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      const normalized = questionTextInput.trim()
      setQuestionText(normalized || null)
      setPage(1)
    }, 300)

    return () => {
      window.clearTimeout(timeoutId)
    }
  }, [questionTextInput])

  // Загрузка групп
  useEffect(() => {
    api.getEVGroups().then(setGroups).catch(() => {})
  }, [])

  // Загрузка при изменении фильтров
  useEffect(() => {
    loadPairs()
  }, [loadPairs])

  // Загрузить детали текущей пары
  const loadPairDetail = useCallback(async (pairId: number) => {
    try {
      const detail = await api.getPairDetail(pairId)
      setCurrentPair(detail)
      setComment('')
      setChainExpanded(false)
      setPendingVerdict(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка загрузки пары')
    }
  }, [])

  // Перейти в режим review
  const startReview = useCallback((index: number) => {
    setCurrentIndex(index)
    setMode('review')
    if (pairs[index]) {
      loadPairDetail(pairs[index].id)
    }
  }, [pairs, loadPairDetail])

  // Навигация между парами
  const goToNext = useCallback(() => {
    if (currentIndex < pairs.length - 1) {
      const nextIndex = currentIndex + 1
      setCurrentIndex(nextIndex)
      loadPairDetail(pairs[nextIndex].id)
    } else if (page * pageSize < total) {
      // Загрузить следующую страницу
      setPage(p => p + 1)
      setCurrentIndex(0)
    } else {
      setMode('list')
    }
  }, [currentIndex, pairs, loadPairDetail, page, pageSize, total])

  const goToPrev = useCallback(() => {
    if (currentIndex > 0) {
      const prevIndex = currentIndex - 1
      setCurrentIndex(prevIndex)
      loadPairDetail(pairs[prevIndex].id)
    }
  }, [currentIndex, pairs, loadPairDetail])

  // Валидация
  const submitVerdict = useCallback(async (verdict: 'approved' | 'rejected' | 'skipped') => {
    if (!currentPair || !canEdit || validating) return

    setValidating(true)
    setPendingVerdict(null)
    try {
      await api.validatePair({
        qa_pair_id: currentPair.id,
        verdict,
        comment: comment.trim() || undefined,
      })

      setLastAction({ verdict, pairId: currentPair.id })

      // Обновить пару в списке
      setPairs(prev => prev.map(p =>
        p.id === currentPair.id
          ? { ...p, existing_verdict: verdict, expert_status: verdict === 'skipped' ? p.expert_status : verdict }
          : p
      ))

      // Перейти к следующей
      setTimeout(() => {
        setLastAction(null)
        goToNext()
      }, 300)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка валидации')
    } finally {
      setValidating(false)
    }
  }, [currentPair, canEdit, validating, comment, goToNext])

  const armOrSubmitVerdict = useCallback((verdict: 'approved' | 'rejected') => {
    if (!currentPair || !canEdit || validating) return

    const now = Date.now()
    const isConfirmingSameVerdict =
      pendingVerdict &&
      pendingVerdict.verdict === verdict &&
      pendingVerdict.expiresAt >= now

    if (isConfirmingSameVerdict) {
      submitVerdict(verdict)
      return
    }

    setPendingVerdict({
      verdict,
      expiresAt: now + 2000,
    })
  }, [currentPair, canEdit, validating, pendingVerdict, submitVerdict])

  useEffect(() => {
    if (!pendingVerdict) return

    const timeoutMs = pendingVerdict.expiresAt - Date.now()
    if (timeoutMs <= 0) {
      setPendingVerdict(null)
      return
    }

    const timeoutId = window.setTimeout(() => {
      setPendingVerdict(current =>
        current && current.expiresAt <= Date.now() ? null : current
      )
    }, timeoutMs + 10)

    return () => window.clearTimeout(timeoutId)
  }, [pendingVerdict])

  useEffect(() => {
    if (mode !== 'review') {
      setPendingVerdict(null)
    }
  }, [mode])

  // Hotkeys
  useEffect(() => {
    if (mode !== 'review' || !canEdit) return

    const handler = (e: KeyboardEvent) => {
      // Не перехватываем если фокус в текстовом поле
      const target = e.target as HTMLElement
      if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.tagName === 'SELECT') return

      switch (e.key.toLowerCase()) {
        case 'y':
          e.preventDefault()
          armOrSubmitVerdict('approved')
          break
        case 'n':
          e.preventDefault()
          armOrSubmitVerdict('rejected')
          break
        case 's':
          e.preventDefault()
          submitVerdict('skipped')
          break
        case 'c':
          e.preventDefault()
          setChainExpanded(prev => !prev)
          break
        case 'arrowleft':
          e.preventDefault()
          goToPrev()
          break
        case 'arrowright':
          e.preventDefault()
          goToNext()
          break
        case 'escape':
          e.preventDefault()
          setMode('list')
          break
      }
    }

    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [mode, canEdit, armOrSubmitVerdict, submitVerdict, goToPrev, goToNext])

  // Фокус на контейнер при входе в review
  useEffect(() => {
    if (mode === 'review' && reviewContainerRef.current) {
      reviewContainerRef.current.focus()
    }
  }, [mode, currentPair])

  const totalPages = Math.ceil(total / pageSize)

  // ---------------------------------------------------------------------------
  // Render: Режим List
  // ---------------------------------------------------------------------------
  if (mode === 'list') {
    return (
      <div className="expert-page">
        <div className="page-header">
          <h1>🔍 Экспертная валидация</h1>
          <p className="text-dim">
            Проверка Q&A-пар Group Knowledge
            {user && <span> · {user.telegram_first_name || user.telegram_username}</span>}
          </p>
        </div>

        {/* Статистика */}
        {stats && (
          <div className="stats-bar">
            <div className="stat">
              <span className="stat-value">{stats.total_pairs}</span>
              <span className="stat-label">Всего пар</span>
            </div>
            <div className="stat stat-success">
              <span className="stat-value">{stats.approved_pairs}</span>
              <span className="stat-label">Одобрено</span>
            </div>
            <div className="stat stat-danger">
              <span className="stat-value">{stats.rejected_pairs}</span>
              <span className="stat-label">Отклонено</span>
            </div>
            <div className="stat">
              <span className="stat-value">{stats.unvalidated_pairs}</span>
              <span className="stat-label">Не проверено</span>
            </div>
            <div className="stat stat-accent">
              <span className="stat-value">{stats.approval_rate}%</span>
              <span className="stat-label">Одобрение</span>
            </div>
          </div>
        )}

        {/* Фильтры */}
        <div className="filters-bar">
          <select
            className="input input-sm"
            value={groupId ?? ''}
            onChange={e => { setGroupId(e.target.value ? Number(e.target.value) : null); setPage(1) }}
          >
            <option value="">Все группы</option>
            {groups.map(g => (
              <option key={g.group_id} value={g.group_id}>
                {g.group_title || `Группа ${g.group_id}`} ({g.pair_count})
              </option>
            ))}
          </select>

          <select
            className="input input-sm"
            value={extractionType ?? ''}
            onChange={e => { setExtractionType(e.target.value || null); setPage(1) }}
          >
            <option value="">Все типы</option>
            <option value="thread_reply">Thread Reply</option>
            <option value="llm_inferred">LLM Inferred</option>
          </select>

          <input
            type="text"
            className="input input-sm"
            value={questionTextInput}
            onChange={e => setQuestionTextInput(e.target.value)}
            placeholder="Поиск по тексту вопроса"
            maxLength={500}
          />

          <select
            className="input input-sm"
            value={expertStatus ?? ''}
            onChange={e => { setExpertStatus(e.target.value || null); setPage(1) }}
          >
            <option value="">Все статусы</option>
            <option value="unvalidated">Не проверено</option>
            <option value="approved">Одобрено</option>
            <option value="rejected">Отклонено</option>
          </select>

          <select
            className="input input-sm"
            value={minConfidence ?? ''}
            onChange={e => { setMinConfidence(e.target.value ? Number(e.target.value) : null); setPage(1) }}
          >
            <option value="">Любая уверенность</option>
            <option value="0.9">≥ 0.9</option>
            <option value="0.8">≥ 0.8</option>
            <option value="0.7">≥ 0.7</option>
            <option value="0.5">≥ 0.5</option>
          </select>

          <select
            className="input input-sm"
            value={`${sortBy}-${sortOrder}`}
            onChange={e => {
              const [sb, so] = e.target.value.split('-')
              setSortBy(sb)
              setSortOrder(so)
              setPage(1)
            }}
          >
            <option value="created_at-desc">Сначала новые</option>
            <option value="created_at-asc">Сначала старые</option>
            <option value="confidence-desc">Уверенность ↓</option>
            <option value="confidence-asc">Уверенность ↑</option>
          </select>

          {canEdit && pairs.length > 0 && (
            <button className="btn btn-primary" onClick={() => startReview(0)}>
              ▶ Начать проверку
            </button>
          )}
        </div>

        {error && <div className="alert alert-danger">{error}</div>}

        {/* Список пар */}
        {loading ? (
          <div className="loading-text">Загрузка Q&A-пар...</div>
        ) : pairs.length === 0 ? (
          <div className="card empty-state">
            <p>Нет Q&A-пар, соответствующих фильтрам</p>
          </div>
        ) : (
          <>
            <div className="pairs-list">
              {pairs.map((pair, index) => (
                <div
                  key={pair.id}
                  className={`pair-card ${pair.expert_status ? `pair-${pair.expert_status}` : ''}`}
                  onClick={() => startReview(index)}
                >
                  <div className="pair-card-header">
                    <span className="pair-id">#{pair.id}</span>
                    <span className={`badge badge-${pair.extraction_type === 'thread_reply' ? 'info' : 'warning'}`}>
                      {pair.extraction_type === 'thread_reply' ? 'Thread' : 'LLM'}
                    </span>
                    <span className="pair-confidence" title="Уверенность LLM">
                      {(pair.confidence * 100).toFixed(0)}%
                    </span>
                    {pair.expert_status && (
                      <span className={`badge badge-${pair.expert_status === 'approved' ? 'success' : 'danger'}`}>
                        {pair.expert_status === 'approved' ? '✓ Одобрено' : '✗ Отклонено'}
                      </span>
                    )}
                    {pair.existing_verdict && (
                      <span className="badge badge-dim" title="Ваш вердикт">
                        Вы: {pair.existing_verdict === 'approved' ? '✓' : pair.existing_verdict === 'rejected' ? '✗' : '⏭'}
                      </span>
                    )}
                  </div>
                  <div className="pair-question">
                    <strong>Q:</strong> {pair.question_text.slice(0, 200)}
                    {pair.question_text.length > 200 && '...'}
                  </div>
                  <div className="pair-answer">
                    <strong>A:</strong> {pair.answer_text.slice(0, 200)}
                    {pair.answer_text.length > 200 && '...'}
                  </div>
                </div>
              ))}
            </div>

            {/* Пагинация */}
            {totalPages > 1 && (
              <div className="pagination">
                <button
                  className="btn btn-sm"
                  disabled={page <= 1}
                  onClick={() => setPage(p => p - 1)}
                >
                  ← Назад
                </button>
                <span className="text-dim">
                  Страница {page} из {totalPages} · {total} пар
                </span>
                <button
                  className="btn btn-sm"
                  disabled={page >= totalPages}
                  onClick={() => setPage(p => p + 1)}
                >
                  Далее →
                </button>
              </div>
            )}
          </>
        )}
      </div>
    )
  }

  // ---------------------------------------------------------------------------
  // Render: Режим Review
  // ---------------------------------------------------------------------------
  return (
    <div className="expert-page review-mode" ref={reviewContainerRef} tabIndex={-1}>
      {/* Верхняя панель */}
      <div className="review-header">
        <button className="btn btn-sm" onClick={() => setMode('list')}>
          ← К списку <kbd>Esc</kbd>
        </button>
        <div className="review-progress">
          <span>{currentIndex + 1}</span> / <span>{pairs.length}</span>
          {total > pairs.length && <span className="text-dim"> (из {total})</span>}
        </div>
        <div className="review-nav">
          <button className="btn btn-sm" onClick={goToPrev} disabled={currentIndex <= 0}>
            ← <kbd>←</kbd>
          </button>
          <button className="btn btn-sm" onClick={goToNext} disabled={currentIndex >= pairs.length - 1 && page * pageSize >= total}>
            → <kbd>→</kbd>
          </button>
        </div>
      </div>

      {error && <div className="alert alert-danger">{error}</div>}

      {lastAction && (
        <div className={`alert alert-${lastAction.verdict === 'approved' ? 'success' : lastAction.verdict === 'rejected' ? 'danger' : 'info'} flash`}>
          {lastAction.verdict === 'approved' ? '✓ Одобрено' : lastAction.verdict === 'rejected' ? '✗ Отклонено' : '⏭ Пропущено'}
          {' '}· пара #{lastAction.pairId}
        </div>
      )}

      {currentPair ? (
        <div className="review-content">
          {/* Метаданные пары */}
          <div className="pair-meta">
            <span className="pair-id">Пара #{currentPair.id}</span>
            <span className={`badge badge-${currentPair.extraction_type === 'thread_reply' ? 'info' : 'warning'}`}>
              {currentPair.extraction_type === 'thread_reply' ? 'Thread Reply' : 'LLM Inferred'}
            </span>
            <span className="pair-confidence-large">
              Уверенность: <strong>{(currentPair.confidence * 100).toFixed(1)}%</strong>
            </span>
            {currentPair.group_title && (
              <span className="badge badge-dim">{currentPair.group_title}</span>
            )}
            {currentPair.llm_model_used && (
              <span className="text-dim">{currentPair.llm_model_used}</span>
            )}
            {currentPair.expert_status && (
              <span className={`badge badge-${currentPair.expert_status === 'approved' ? 'success' : 'danger'}`}>
                {currentPair.expert_status === 'approved' ? '✓ Одобрено экспертом' : '✗ Отклонено экспертом'}
              </span>
            )}
          </div>

          {/* Вопрос */}
          <div className="qa-block qa-question">
            <div className="qa-label">📝 Вопрос</div>
            <div className="qa-text">{currentPair.question_text}</div>
          </div>

          {/* Ответ */}
          <div className="qa-block qa-answer">
            <div className="qa-label">💡 Ответ</div>
            <div className="qa-text">{currentPair.answer_text}</div>
          </div>

          {/* Цепочка сообщений */}
          {currentPair.chain_messages.length > 0 && (
            <div className="chain-section">
              <button
                className="btn btn-chain-toggle"
                onClick={() => setChainExpanded(!chainExpanded)}
              >
                {chainExpanded ? '▼' : '▶'} Цепочка сообщений
                ({currentPair.chain_messages.length})
                <kbd>C</kbd>
              </button>

              {chainExpanded && (
                <div className="chain-messages">
                  {currentPair.chain_messages.map((msg) => (
                    <ChainMessageCard
                      key={msg.telegram_message_id}
                      message={msg}
                      isQuestion={currentPair?.question_message_id != null}
                    />
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Комментарий */}
          {canEdit && (
            <div className="comment-section">
              <input
                type="text"
                className="input"
                value={comment}
                onChange={e => setComment(e.target.value)}
                placeholder="Комментарий (необязательно)..."
                maxLength={2000}
              />
            </div>
          )}

          {/* Кнопки валидации */}
          {canEdit && (
            <div className="verdict-buttons">
              <button
                className={`btn btn-verdict btn-approve ${pendingVerdict?.verdict === 'approved' ? 'btn-armed' : ''}`}
                onClick={() => armOrSubmitVerdict('approved')}
                disabled={validating}
              >
                {pendingVerdict?.verdict === 'approved' ? '✓ Подтвердить одобрение' : '✓ Одобрить'} <kbd>Y</kbd>
              </button>
              <button
                className={`btn btn-verdict btn-reject ${pendingVerdict?.verdict === 'rejected' ? 'btn-armed' : ''}`}
                onClick={() => armOrSubmitVerdict('rejected')}
                disabled={validating}
              >
                {pendingVerdict?.verdict === 'rejected' ? '✗ Подтвердить отклонение' : '✗ Отклонить'} <kbd>N</kbd>
              </button>
              <button
                className="btn btn-verdict btn-skip"
                onClick={() => submitVerdict('skipped')}
                disabled={validating}
              >
                ⏭ Пропустить <kbd>S</kbd>
              </button>
            </div>
          )}

          {canEdit && pendingVerdict && (
            <div className="verdict-confirm-hint" role="status" aria-live="polite">
              Нажмите {pendingVerdict.verdict === 'approved' ? '«Одобрить» (Y)' : '«Отклонить» (N)'} ещё раз в течение 2 секунд для подтверждения
            </div>
          )}

          {!canEdit && (
            <div className="card" style={{ textAlign: 'center', marginTop: 16 }}>
              <p className="text-dim">У вас нет прав на валидацию. Режим просмотра.</p>
            </div>
          )}
        </div>
      ) : (
        <div className="loading-text">Загрузка пары...</div>
      )}
    </div>
  )
}


// ---------------------------------------------------------------------------
// Компонент сообщения из цепочки
// ---------------------------------------------------------------------------

function ChainMessageCard({ message }: { message: ChainMessage; isQuestion: boolean }) {
  const timestamp = message.message_date
    ? new Date(message.message_date * 1000).toLocaleString('ru-RU', {
        day: '2-digit', month: '2-digit', year: 'numeric',
        hour: '2-digit', minute: '2-digit',
      })
    : ''

  const fullText = [
    message.message_text,
    message.caption ? `[Подпись] ${message.caption}` : null,
    message.image_description ? `[Изображение] ${message.image_description}` : null,
  ].filter(Boolean).join('\n')

  return (
    <div className={`chain-msg ${message.is_question ? 'chain-msg-question' : ''}`}>
      <div className="chain-msg-header">
        <span className="chain-msg-id">[{message.telegram_message_id}]</span>
        <span className="chain-msg-sender">{message.sender_name || `User ${message.sender_id}`}</span>
        <span className="chain-msg-time">{timestamp}</span>
        {message.reply_to_message_id && (
          <span className="chain-msg-reply">→ ответ на {message.reply_to_message_id}</span>
        )}
        {message.has_image && <span className="badge badge-dim">📷</span>}
        {message.is_question && (
          <span className="badge badge-info" title={`Уверенность: ${(message.question_confidence ?? 0) * 100}%`}>
            ❓ {((message.question_confidence ?? 0) * 100).toFixed(0)}%
          </span>
        )}
      </div>
      <div className="chain-msg-text">{fullText || '(пустое сообщение)'}</div>
    </div>
  )
}
