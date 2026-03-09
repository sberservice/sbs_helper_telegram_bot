/**
 * Вкладка «Q&A-пары» — просмотр всех Q&A-пар с фильтрацией и пагинацией.
 */

import { useCallback, useEffect, useState } from 'react'
import { api, type QAPairDetail, type GKGroup } from '../../api'

function formatDebugPayload(payload: string | null | undefined): string {
  if (!payload) {
    return ''
  }

  try {
    return JSON.stringify(JSON.parse(payload), null, 2)
  } catch {
    return payload
  }
}

export default function QAPairsTab() {
  const [pairs, setPairs] = useState<QAPairDetail[]>([])
  const [pairDetails, setPairDetails] = useState<Record<number, QAPairDetail>>({})
  const [total, setTotal] = useState(0)
  const [groups, setGroups] = useState<GKGroup[]>([])
  const [loading, setLoading] = useState(true)
  const [detailLoadingId, setDetailLoadingId] = useState<number | null>(null)
  const [error, setError] = useState('')

  /* Фильтры */
  const [page, setPage] = useState(1)
  const [pageSize] = useState(20)
  const [groupId, setGroupId] = useState<number | null>(null)
  const [extractionType, setExtractionType] = useState<string | null>(null)
  const [searchInput, setSearchInput] = useState('')
  const [searchText, setSearchText] = useState<string | null>(null)
  const [expertStatus, setExpertStatus] = useState<string | null>(null)
  const [minConfidence, setMinConfidence] = useState<number | null>(null)
  const [sortBy, setSortBy] = useState('created_at')
  const [sortOrder, setSortOrder] = useState('desc')

  /* Развёрнутые карточки */
  const [expandedId, setExpandedId] = useState<number | null>(null)

  /* Debounce поиска по тексту */
  useEffect(() => {
    const t = window.setTimeout(() => {
      const val = searchInput.trim()
      setSearchText(val || null)
      setPage(1)
    }, 300)
    return () => window.clearTimeout(t)
  }, [searchInput])

  useEffect(() => {
    api.gkGroups().then(setGroups).catch(() => {})
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const res = await api.gkQAPairs({
        page, page_size: pageSize, group_id: groupId,
        extraction_type: extractionType, search_text: searchText,
        expert_status: expertStatus, min_confidence: minConfidence,
        sort_by: sortBy, sort_order: sortOrder,
      })
      setPairs(res.pairs)
      setTotal(res.total)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка загрузки')
    } finally {
      setLoading(false)
    }
  }, [page, pageSize, groupId, extractionType, searchText, expertStatus, minConfidence, sortBy, sortOrder])

  useEffect(() => { load() }, [load])

  const toggleExpanded = useCallback(async (pairId: number) => {
    if (expandedId === pairId) {
      setExpandedId(null)
      return
    }

    setExpandedId(pairId)
    if (pairDetails[pairId] || detailLoadingId === pairId) {
      return
    }

    setDetailLoadingId(pairId)
    try {
      const detail = await api.gkQAPairDetail(pairId)
      setPairDetails(prev => ({ ...prev, [pairId]: detail }))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка загрузки деталей пары')
    } finally {
      setDetailLoadingId(current => current === pairId ? null : current)
    }
  }, [detailLoadingId, expandedId, pairDetails])

  const totalPages = Math.ceil(total / pageSize)

  return (
    <div className="gk-qa-tab">
      {error && <div className="alert alert-danger">{error}</div>}

      {/* Фильтры */}
      <div className="filters-bar">
        <select className="input input-sm" value={groupId ?? ''} onChange={e => { setGroupId(e.target.value ? Number(e.target.value) : null); setPage(1) }}>
          <option value="">Все группы</option>
          {groups.map(g => (
            <option key={g.group_id} value={g.group_id}>{g.group_title || `Группа ${g.group_id}`}</option>
          ))}
        </select>

        <select className="input input-sm" value={extractionType ?? ''} onChange={e => { setExtractionType(e.target.value || null); setPage(1) }}>
          <option value="">Все типы</option>
          <option value="thread_reply">Thread Reply</option>
          <option value="llm_inferred">LLM Inferred</option>
        </select>

        <input
          type="text" className="input input-sm"
          value={searchInput} onChange={e => setSearchInput(e.target.value)}
          placeholder="Поиск по тексту" maxLength={500}
        />

        <select className="input input-sm" value={expertStatus ?? ''} onChange={e => { setExpertStatus(e.target.value || null); setPage(1) }}>
          <option value="">Все статусы</option>
          <option value="unvalidated">Не проверено</option>
          <option value="approved">Одобрено</option>
          <option value="rejected">Отклонено</option>
        </select>

        <select className="input input-sm" value={minConfidence ?? ''} onChange={e => { setMinConfidence(e.target.value ? Number(e.target.value) : null); setPage(1) }}>
          <option value="">Любая уверенность</option>
          <option value="0.9">≥ 0.9</option>
          <option value="0.8">≥ 0.8</option>
          <option value="0.7">≥ 0.7</option>
          <option value="0.5">≥ 0.5</option>
        </select>

        <select className="input input-sm" value={`${sortBy}-${sortOrder}`} onChange={e => { const [sb, so] = e.target.value.split('-'); setSortBy(sb); setSortOrder(so); setPage(1) }}>
          <option value="created_at-desc">Сначала новые</option>
          <option value="created_at-asc">Сначала старые</option>
          <option value="confidence-desc">Уверенность ↓</option>
          <option value="confidence-asc">Уверенность ↑</option>
        </select>
      </div>

      <div className="text-dim" style={{ marginBottom: 8 }}>Найдено: {total}</div>

      {/* Список */}
      {loading ? (
        <div className="loading-text">Загрузка...</div>
      ) : pairs.length === 0 ? (
        <div className="card empty-state"><p>Нет Q&A-пар</p></div>
      ) : (
        <>
          <div className="pairs-list">
            {pairs.map(pair => (
              <div
                key={pair.id}
                className={`pair-card ${pair.expert_status ? `pair-${pair.expert_status}` : ''} ${expandedId === pair.id ? 'pair-expanded' : ''}`}
                onClick={() => { void toggleExpanded(pair.id) }}
              >
                <div className="pair-card-header">
                  <span className="pair-id">#{pair.id}</span>
                  <span className={`badge badge-${pair.extraction_type === 'thread_reply' ? 'info' : 'warning'}`}>
                    {pair.extraction_type === 'thread_reply' ? 'Thread' : 'LLM'}
                  </span>
                  <span className="pair-confidence">{(pair.confidence * 100).toFixed(0)}%</span>
                  {pair.expert_status && (
                    <span className={`badge badge-${pair.expert_status === 'approved' ? 'success' : 'danger'}`}>
                      {pair.expert_status === 'approved' ? '✓' : '✗'} {pair.expert_status}
                    </span>
                  )}
                  {pair.group_title && <span className="badge badge-dim">{pair.group_title}</span>}
                </div>
                <div className="pair-question">
                  <strong>Q:</strong> {expandedId === pair.id ? pair.question_text : pair.question_text.slice(0, 200) + (pair.question_text.length > 200 ? '...' : '')}
                </div>
                <div className="pair-answer">
                  <strong>A:</strong> {expandedId === pair.id ? pair.answer_text : pair.answer_text.slice(0, 200) + (pair.answer_text.length > 200 ? '...' : '')}
                </div>
                {expandedId === pair.id && (
                  <div className="pair-details text-dim" style={{ marginTop: 8, fontSize: 12 }}>
                    Создано: {pair.created_at} · Модель: {pair.llm_model_used || '–'} · Approved: {pair.approved}
                    <div style={{ marginTop: 10 }}>
                      <strong>LLM request:</strong>
                      {detailLoadingId === pair.id && !pairDetails[pair.id] ? (
                        <div style={{ marginTop: 6 }}>Загрузка отладочного запроса...</div>
                      ) : pairDetails[pair.id]?.llm_request_payload ? (
                        <pre className="chain-msg-text" style={{ marginTop: 6, whiteSpace: 'pre-wrap' }}>
                          {formatDebugPayload(pairDetails[pair.id]?.llm_request_payload)}
                        </pre>
                      ) : (
                        <div style={{ marginTop: 6 }}>Для этой пары отладочный запрос не сохранён.</div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>

          {totalPages > 1 && (
            <div className="pagination">
              <button className="btn btn-sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>← Назад</button>
              <span className="text-dim">Страница {page} из {totalPages} · {total} пар</span>
              <button className="btn btn-sm" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>Далее →</button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
