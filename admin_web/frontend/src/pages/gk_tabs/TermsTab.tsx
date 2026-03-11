/**
 * Вкладка «Термины» — управление защищёнными терминами и аббревиатурами.
 * Поддержка: список, экспертная валидация, добавление вручную, запуск LLM-сканирования.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import {
  api,
  type TermDetail,
  type TermValidationStats,
  type TermGroupInfo,
  type TermListResponse,
  type TermScanStatus,
  type GroupInfo,
} from '../../api'
import { useAuth } from '../../auth'

export default function TermsTab() {
  const { hasPermission } = useAuth()
  const canEdit = hasPermission('gk_knowledge', 'edit')

  // Данные
  const [terms, setTerms] = useState<TermDetail[]>([])
  const [total, setTotal] = useState(0)
  const [stats, setStats] = useState<TermValidationStats | null>(null)
  const [groups, setGroups] = useState<TermGroupInfo[]>([])
  const [evGroups, setEvGroups] = useState<GroupInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  // Текущий термин
  const [currentTerm, setCurrentTerm] = useState<TermDetail | null>(null)
  const [currentIndex, setCurrentIndex] = useState(0)
  const [comment, setComment] = useState('')
  const [editedTerm, setEditedTerm] = useState('')
  const [editedDefinition, setEditedDefinition] = useState('')
  const [isEditing, setIsEditing] = useState(false)
  const [validating, setValidating] = useState(false)
  const [lastAction, setLastAction] = useState<{ verdict: string; termId: number } | null>(null)
  const [pendingVerdict, setPendingVerdict] = useState<{ verdict: 'approved' | 'rejected'; expiresAt: number } | null>(null)

  // Фильтры
  const [page, setPage] = useState(1)
  const [pageSize] = useState(30)
  const [groupId, setGroupId] = useState<number | null>(null)
  const [termType, setTermType] = useState<string | null>(null)
  const [status, setStatus] = useState<string | null>('pending')
  const [minConfidence, setMinConfidence] = useState<number | null>(null)
  const [searchInput, setSearchInput] = useState('')
  const [searchText, setSearchText] = useState<string | null>(null)
  const [sortBy, setSortBy] = useState<'created_at' | 'term' | 'confidence' | 'id' | 'group_id' | 'term_type' | 'status'>('created_at')
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc')
  const [expertStatus] = useState<string | null>(null)

  const [mode, setMode] = useState<'list' | 'review'>('list')
  const reviewRef = useRef<HTMLDivElement>(null)

  // Сканирование
  const [scanGroupId, setScanGroupId] = useState<number | ''>('')
  const [scanDateFrom, setScanDateFrom] = useState('')
  const [scanDateTo, setScanDateTo] = useState('')
  const [scanRunning, setScanRunning] = useState(false)
  const [scanBatchId, setScanBatchId] = useState<string | null>(null)
  const [scanStatus, setScanStatus] = useState<TermScanStatus | null>(null)
  const [showScan, setShowScan] = useState(false)

  // Ручное добавление
  const [showAdd, setShowAdd] = useState(false)
  const [addGroupId, setAddGroupId] = useState<number | ''>(0)
  const [addTerm, setAddTerm] = useState('')
  const [addTermType, setAddTermType] = useState<'fixed_term' | 'acronym'>('fixed_term')
  const [addDefinition, setAddDefinition] = useState('')
  const [addSubmitting, setAddSubmitting] = useState(false)

  // Загрузка списка
  const loadTerms = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const result: TermListResponse = await api.listTerms({
        page,
        page_size: pageSize,
        group_id: groupId,
        term_type: termType,
        status,
        min_confidence: minConfidence,
        search_text: searchText,
        expert_status: expertStatus,
        sort_by: sortBy,
        sort_order: sortOrder,
      })
      setTerms(result.terms)
      setTotal(result.total)
      setStats(result.stats)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка загрузки')
    } finally {
      setLoading(false)
    }
  }, [page, pageSize, groupId, termType, status, minConfidence, searchText, expertStatus, sortBy, sortOrder])

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      setSearchText(searchInput.trim() || null)
      setPage(1)
    }, 300)
    return () => window.clearTimeout(timeout)
  }, [searchInput])

  useEffect(() => {
    api.getTermGroups().then(setGroups).catch(() => {})
    api.getEVGroups().then(setEvGroups).catch(() => {})
  }, [])

  useEffect(() => { loadTerms() }, [loadTerms])

  // Загрузка деталей термина
  const loadTermDetail = useCallback(async (termId: number) => {
    try {
      const detail = await api.getTermDetail(termId)
      setCurrentTerm(detail)
      setComment('')
      setEditedTerm(detail.term)
      setEditedDefinition(detail.definition || '')
      setIsEditing(false)
      setPendingVerdict(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка загрузки термина')
    }
  }, [])

  // Навигация review
  const startReview = useCallback((index: number) => {
    setCurrentIndex(index)
    setCurrentTerm(null)
    setMode('review')
  }, [])

  const exitReview = useCallback(() => {
    setMode('list')
  }, [])

  const goToNext = useCallback(() => {
    if (currentIndex < terms.length - 1) {
      setCurrentIndex(i => i + 1)
    } else if (page * pageSize < total) {
      setPage(p => p + 1)
      setCurrentIndex(0)
    } else {
      exitReview()
    }
  }, [currentIndex, terms.length, page, pageSize, total, exitReview])

  const goToPrev = useCallback(() => {
    if (currentIndex > 0) setCurrentIndex(i => i - 1)
  }, [currentIndex])

  // Verdict
  const submitVerdict = useCallback(async (verdict: 'approved' | 'rejected' | 'edited') => {
    if (!currentTerm || !canEdit || validating) return
    setValidating(true)
    setPendingVerdict(null)
    try {
      await api.validateTerm({
        term_id: currentTerm.id,
        verdict,
        comment: comment.trim() || undefined,
        edited_term: verdict === 'edited' ? editedTerm.trim() : undefined,
        edited_definition: verdict === 'edited' ? editedDefinition.trim() : undefined,
      })
      setLastAction({ verdict, termId: currentTerm.id })
      setTerms(prev => prev.map(t =>
        t.id === currentTerm.id
          ? { ...t, existing_verdict: verdict, expert_status: verdict, status: verdict === 'rejected' ? 'rejected' : 'approved' }
          : t
      ))
      setTimeout(() => { setLastAction(null); goToNext() }, 300)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка валидации')
    } finally {
      setValidating(false)
    }
  }, [currentTerm, canEdit, validating, comment, editedTerm, editedDefinition, goToNext])

  const armOrSubmitVerdict = useCallback((verdict: 'approved' | 'rejected') => {
    if (!currentTerm || !canEdit || validating) return
    const now = Date.now()
    if (pendingVerdict && pendingVerdict.verdict === verdict && pendingVerdict.expiresAt >= now) {
      submitVerdict(verdict)
      return
    }
    setPendingVerdict({ verdict, expiresAt: now + 2000 })
  }, [currentTerm, canEdit, validating, pendingVerdict, submitVerdict])

  useEffect(() => {
    if (!pendingVerdict) return
    const ms = pendingVerdict.expiresAt - Date.now()
    if (ms <= 0) { setPendingVerdict(null); return }
    const id = window.setTimeout(() => {
      setPendingVerdict(c => c && c.expiresAt <= Date.now() ? null : c)
    }, ms + 10)
    return () => window.clearTimeout(id)
  }, [pendingVerdict])

  useEffect(() => { if (mode !== 'review') setPendingVerdict(null) }, [mode])

  useEffect(() => {
    if (mode !== 'review' || loading) return
    const t = terms[currentIndex]
    if (!t) { setCurrentTerm(null); return }
    if (currentTerm?.id === t.id) return
    loadTermDetail(t.id)
  }, [mode, loading, terms, currentIndex, currentTerm?.id, loadTermDetail])

  // Hotkeys
  useEffect(() => {
    if (mode !== 'review' || !canEdit) return
    const handler = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return
      switch (e.key.toLowerCase()) {
        case 'y': e.preventDefault(); armOrSubmitVerdict('approved'); break
        case 'n': e.preventDefault(); armOrSubmitVerdict('rejected'); break
        case 'e': e.preventDefault(); setIsEditing(v => !v); break
        case 'arrowleft': e.preventDefault(); goToPrev(); break
        case 'arrowright': e.preventDefault(); goToNext(); break
        case 'escape': e.preventDefault(); exitReview(); break
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [mode, canEdit, armOrSubmitVerdict, goToPrev, goToNext, exitReview])

  useEffect(() => {
    if (mode === 'review' && reviewRef.current) reviewRef.current.focus()
  }, [mode, currentTerm])

  // Удаление термина
  const handleDelete = useCallback(async (termId: number) => {
    if (!canEdit) return
    try {
      await api.deleteTerm(termId)
      setTerms(prev => prev.filter(t => t.id !== termId))
      setTotal(prev => prev - 1)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка удаления')
    }
  }, [canEdit])

  // Ручное добавление
  const handleAdd = useCallback(async () => {
    if (!canEdit || addSubmitting || !addTerm.trim()) return
    setAddSubmitting(true)
    try {
      await api.addTermManually({
        group_id: typeof addGroupId === 'number' ? addGroupId : 0,
        term: addTerm.trim(),
        term_type: addTermType,
        definition: addDefinition.trim() || undefined,
      })
      setAddTerm('')
      setAddDefinition('')
      setShowAdd(false)
      loadTerms()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка добавления')
    } finally {
      setAddSubmitting(false)
    }
  }, [canEdit, addSubmitting, addTerm, addTermType, addDefinition, addGroupId, loadTerms])

  // Сканирование
  const handleScan = useCallback(async () => {
    if (!canEdit || scanRunning || !scanGroupId || !scanDateFrom || !scanDateTo) return
    setScanRunning(true)
    setScanStatus(null)
    try {
      const res = await api.triggerTermScan({
        group_id: Number(scanGroupId),
        date_from: scanDateFrom,
        date_to: scanDateTo,
      })
      setScanBatchId(res.batch_id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка запуска сканирования')
      setScanRunning(false)
    }
  }, [canEdit, scanRunning, scanGroupId, scanDateFrom, scanDateTo])

  // Полл статуса сканирования
  useEffect(() => {
    if (!scanBatchId) return
    let cancelled = false
    const poll = async () => {
      try {
        const st = await api.getTermScanStatus(scanBatchId)
        if (cancelled) return
        setScanStatus(st)
        if (st.status === 'completed' || st.status === 'failed') {
          setScanRunning(false)
          if (st.status === 'completed') loadTerms()
          return
        }
        setTimeout(poll, 2000)
      } catch {
        if (!cancelled) setScanRunning(false)
      }
    }
    poll()
    return () => { cancelled = true }
  }, [scanBatchId, loadTerms])

  const totalPages = Math.ceil(total / pageSize)

  // ---- List mode ----
  if (mode === 'list') {
    return (
      <div className="expert-page">
        {stats && (
          <div className="stats-bar">
            <div className="stat"><span className="stat-value">{stats.total}</span><span className="stat-label">Всего</span></div>
            <div className="stat stat-warning"><span className="stat-value">{stats.pending}</span><span className="stat-label">На проверке</span></div>
            <div className="stat stat-success"><span className="stat-value">{stats.approved}</span><span className="stat-label">Одобрено</span></div>
            <div className="stat stat-danger"><span className="stat-value">{stats.rejected}</span><span className="stat-label">Отклонено</span></div>
            <div className="stat"><span className="stat-value">{stats.fixed_terms}</span><span className="stat-label">Термины</span></div>
            <div className="stat stat-accent"><span className="stat-value">{stats.acronyms}</span><span className="stat-label">Аббревиатуры</span></div>
          </div>
        )}

        <div className="filters-bar">
          <select className="input input-sm" value={groupId ?? ''} onChange={e => { setGroupId(e.target.value ? Number(e.target.value) : null); setPage(1) }}>
            <option value="">Все группы</option>
            <option value="0">Глобальные</option>
            {groups.map(g => (
              <option key={g.group_id} value={g.group_id}>
                {g.group_title || `Группа ${g.group_id}`} ({g.term_count}, ожидает: {g.pending_count})
              </option>
            ))}
          </select>
          <select className="input input-sm" value={termType ?? ''} onChange={e => { setTermType(e.target.value || null); setPage(1) }}>
            <option value="">Все типы</option>
            <option value="fixed_term">Термин</option>
            <option value="acronym">Аббревиатура</option>
          </select>
          <select className="input input-sm" value={status ?? ''} onChange={e => { setStatus(e.target.value || null); setPage(1) }}>
            <option value="">Все статусы</option>
            <option value="pending">На проверке</option>
            <option value="approved">Одобрено</option>
            <option value="rejected">Отклонено</option>
          </select>
          <select
            className="input input-sm"
            value={minConfidence == null ? '' : String(minConfidence)}
            onChange={e => {
              const value = e.target.value
              setMinConfidence(value === '' ? null : Number(value))
              setPage(1)
            }}
          >
            <option value="">Мин. confidence (любой)</option>
            {Array.from({ length: 11 }, (_, index) => {
              const value = (index / 10).toFixed(1)
              return (
                <option key={value} value={value}>
                  ≥ {value}
                </option>
              )
            })}
          </select>
          <select className="input input-sm" value={sortBy} onChange={e => { setSortBy(e.target.value as typeof sortBy); setPage(1) }}>
            <option value="created_at">Сортировка: дата</option>
            <option value="term">Сортировка: термин</option>
            <option value="confidence">Сортировка: confidence</option>
            <option value="status">Сортировка: статус</option>
            <option value="term_type">Сортировка: тип</option>
            <option value="group_id">Сортировка: группа</option>
            <option value="id">Сортировка: ID</option>
          </select>
          <select className="input input-sm" value={sortOrder} onChange={e => { setSortOrder(e.target.value as typeof sortOrder); setPage(1) }}>
            <option value="desc">По убыванию</option>
            <option value="asc">По возрастанию</option>
          </select>
          <input
            type="text" className="input input-sm" value={searchInput}
            onChange={e => setSearchInput(e.target.value)}
            placeholder="Поиск по термину/определению" maxLength={200}
          />
          {canEdit && terms.length > 0 && (
            <button className="btn btn-primary" onClick={() => startReview(0)}>▶ Начать проверку</button>
          )}
        </div>

        {canEdit && (
          <div className="filters-bar" style={{ gap: 8 }}>
            <button className="btn btn-sm" onClick={() => setShowAdd(!showAdd)}>
              {showAdd ? '✕ Закрыть' : '＋ Добавить термин'}
            </button>
            <button className="btn btn-sm" onClick={() => setShowScan(!showScan)}>
              {showScan ? '✕ Закрыть' : '🔬 Сканирование LLM'}
            </button>
          </div>
        )}

        {/* Форма добавления */}
        {showAdd && canEdit && (
          <div className="card" style={{ marginBottom: 16, padding: 16 }}>
            <h4 style={{ margin: '0 0 12px' }}>Добавить термин вручную</h4>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'flex-end' }}>
              <div>
                <label className="text-dim" style={{ fontSize: 12 }}>Группа</label>
                <select className="input input-sm" value={addGroupId} onChange={e => setAddGroupId(e.target.value === '' ? '' : Number(e.target.value))}>
                  <option value={0}>Глобальный</option>
                  {evGroups.map(g => (
                    <option key={g.group_id} value={g.group_id}>
                      {g.group_title || `Группа ${g.group_id}`}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-dim" style={{ fontSize: 12 }}>Тип</label>
                <select className="input input-sm" value={addTermType} onChange={e => setAddTermType(e.target.value as 'fixed_term' | 'acronym')}>
                  <option value="fixed_term">Термин</option>
                  <option value="acronym">Аббревиатура</option>
                </select>
              </div>
              <div>
                <label className="text-dim" style={{ fontSize: 12 }}>Термин</label>
                <input type="text" className="input input-sm" value={addTerm} onChange={e => setAddTerm(e.target.value)} placeholder="напр. ккт" maxLength={100} />
              </div>
              <div>
                <label className="text-dim" style={{ fontSize: 12 }}>Определение</label>
                <input type="text" className="input input-sm" value={addDefinition} onChange={e => setAddDefinition(e.target.value)} placeholder="для аббревиатур" maxLength={500} />
              </div>
              <button className="btn btn-primary btn-sm" onClick={handleAdd} disabled={addSubmitting || !addTerm.trim()}>
                {addSubmitting ? 'Добавление...' : 'Добавить'}
              </button>
            </div>
          </div>
        )}

        {/* Форма сканирования */}
        {showScan && canEdit && (
          <div className="card" style={{ marginBottom: 16, padding: 16 }}>
            <h4 style={{ margin: '0 0 12px' }}>LLM-сканирование сообщений</h4>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'flex-end' }}>
              <div>
                <label className="text-dim" style={{ fontSize: 12 }}>Группа</label>
                <select className="input input-sm" value={scanGroupId} onChange={e => setScanGroupId(e.target.value ? Number(e.target.value) : '')}>
                  <option value="">Выберите группу</option>
                  {evGroups.map(g => (
                    <option key={g.group_id} value={g.group_id}>
                      {g.group_title || `Группа ${g.group_id}`}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-dim" style={{ fontSize: 12 }}>Дата от</label>
                <input type="date" className="input input-sm" value={scanDateFrom} onChange={e => setScanDateFrom(e.target.value)} />
              </div>
              <div>
                <label className="text-dim" style={{ fontSize: 12 }}>Дата до</label>
                <input type="date" className="input input-sm" value={scanDateTo} onChange={e => setScanDateTo(e.target.value)} />
              </div>
              <button
                className="btn btn-primary btn-sm"
                onClick={handleScan}
                disabled={scanRunning || !scanGroupId || !scanDateFrom || !scanDateTo}
              >
                {scanRunning ? '⏳ Сканирование...' : '🔬 Запустить'}
              </button>
            </div>
            {scanStatus && (
              <>
                <div
                  className={`alert alert-${scanStatus.status === 'completed' ? 'success' : scanStatus.status === 'failed' ? 'danger' : 'info'}`}
                  style={{ marginTop: 12 }}
                >
                  {(scanStatus.status === 'queued' || scanStatus.status === 'running') && (
                    <>
                      ⏳ {scanStatus.progress?.message || (scanStatus.status === 'queued' ? 'Сканирование в очереди...' : 'Сканирование выполняется...')}
                      {typeof scanStatus.progress?.percent === 'number' ? ` (${Math.round(scanStatus.progress.percent)}%)` : ''}
                      {typeof scanStatus.progress?.batches_processed === 'number' && typeof scanStatus.progress?.total_batches === 'number'
                        ? ` · Батчи: ${scanStatus.progress.batches_processed}/${scanStatus.progress.total_batches}`
                        : ''}
                    </>
                  )}
                  {scanStatus.status === 'completed' && (
                    <>
                      ✓ Найдено терминов: {scanStatus.result?.terms_found ?? scanStatus.progress?.terms_found ?? 0}
                      , новых: {scanStatus.result?.terms_new ?? scanStatus.progress?.terms_new ?? scanStatus.result?.terms_stored ?? 0}
                    </>
                  )}
                  {scanStatus.status === 'failed' && `Ошибка: ${scanStatus.error || 'Неизвестная ошибка'}`}
                </div>

                {(scanStatus.progress || (scanStatus.progress_log && scanStatus.progress_log.length > 0)) && (
                  <div className="card" style={{ marginTop: 8, padding: 10 }}>
                    <div style={{ fontSize: 12, marginBottom: 6, color: 'var(--text-dim)' }}>
                      Прогресс: {typeof scanStatus.progress?.percent === 'number' ? `${Math.max(0, Math.min(100, Math.round(scanStatus.progress.percent)))}%` : '—'}
                    </div>
                    <div style={{ width: '100%', height: 6, background: 'var(--surface-2)', borderRadius: 4, overflow: 'hidden', marginBottom: 8 }}>
                      <div
                        style={{
                          width: `${Math.max(0, Math.min(100, scanStatus.progress?.percent ?? 0))}%`,
                          height: '100%',
                          background: 'var(--accent)',
                          transition: 'width 0.2s ease',
                        }}
                      />
                    </div>
                    {scanStatus.progress_log && scanStatus.progress_log.length > 0 && (
                      <div style={{ fontSize: 12, lineHeight: 1.4 }}>
                        {scanStatus.progress_log.slice(-5).map((line, idx) => {
                          const time = line.updated_at ? new Date(line.updated_at).toLocaleTimeString() : '—'
                          const text = line.message || line.stage || 'Событие'
                          return (
                            <div key={`${line.updated_at || 'no-time'}-${idx}`} style={{ color: 'var(--text-dim)' }}>
                              {time} — {text}
                            </div>
                          )
                        })}
                      </div>
                    )}
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {error && <div className="alert alert-danger">{error}</div>}

        {loading ? (
          <div className="loading-text">Загрузка терминов...</div>
        ) : terms.length === 0 ? (
          <div className="card empty-state"><p>Нет терминов, соответствующих фильтрам</p></div>
        ) : (
          <>
            <div className="pairs-list">
              {terms.map((term, index) => (
                <div
                  key={term.id}
                  className={`pair-card ${term.status === 'approved' ? 'pair-approved' : term.status === 'rejected' ? 'pair-rejected' : ''}`}
                  onClick={() => startReview(index)}
                >
                  <div className="pair-card-header">
                    <span className="pair-id">#{term.id}</span>
                    <span className={`badge badge-${term.term_type === 'fixed_term' ? 'info' : 'warning'}`}>
                      {term.term_type === 'fixed_term' ? 'Термин' : 'Аббревиатура'}
                    </span>
                    <span className={`badge badge-dim`}>{term.source}</span>
                    {term.confidence != null && (
                      <span className="pair-confidence" title="Уверенность">{(term.confidence * 100).toFixed(0)}%</span>
                    )}
                    {term.status === 'approved' && <span className="badge badge-success">✓ Одобрено</span>}
                    {term.status === 'rejected' && <span className="badge badge-danger">✗ Отклонено</span>}
                    {term.status === 'pending' && <span className="badge badge-warning">⏳ На проверке</span>}
                    {term.group_id === 0 && <span className="badge badge-dim">глобальный</span>}
                  </div>
                  <div className="pair-question">
                    <strong>{term.term}</strong>
                    {term.definition && <span className="text-dim" style={{ marginLeft: 8 }}>— {term.definition}</span>}
                  </div>
                </div>
              ))}
            </div>
            {totalPages > 1 && (
              <div className="pagination">
                <button className="btn btn-sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>← Назад</button>
                <span className="text-dim">Страница {page} из {totalPages} · {total} терминов</span>
                <button className="btn btn-sm" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>Далее →</button>
              </div>
            )}
          </>
        )}
      </div>
    )
  }

  // ---- Review mode ----
  return (
    <div className="expert-page review-mode" ref={reviewRef} tabIndex={-1}>
      <div className="review-header">
        <button className="btn btn-sm" onClick={exitReview}>← К списку <kbd>Esc</kbd></button>
        <div className="review-progress">
          <span>{currentIndex + 1}</span> / <span>{terms.length}</span>
          {total > terms.length && <span className="text-dim"> (из {total})</span>}
        </div>
        <div className="review-nav">
          <button className="btn btn-sm" onClick={goToPrev} disabled={currentIndex <= 0}>← <kbd>←</kbd></button>
          <button className="btn btn-sm" onClick={goToNext} disabled={currentIndex >= terms.length - 1 && page * pageSize >= total}>→ <kbd>→</kbd></button>
        </div>
      </div>

      {error && <div className="alert alert-danger">{error}</div>}

      {lastAction && (
        <div className={`alert alert-${lastAction.verdict === 'approved' ? 'success' : lastAction.verdict === 'rejected' ? 'danger' : 'info'} flash`}>
          {lastAction.verdict === 'approved' ? '✓ Одобрено' : lastAction.verdict === 'rejected' ? '✗ Отклонено' : '✎ Отредактировано'} · термин #{lastAction.termId}
        </div>
      )}

      {currentTerm ? (
        <div className="review-content">
          <div className="pair-meta">
            <span className="pair-id">Термин #{currentTerm.id}</span>
            <span className={`badge badge-${currentTerm.term_type === 'fixed_term' ? 'info' : 'warning'}`}>
              {currentTerm.term_type === 'fixed_term' ? 'Термин' : 'Аббревиатура'}
            </span>
            <span className="badge badge-dim">{currentTerm.source}</span>
            {currentTerm.confidence != null && (
              <span className="pair-confidence-large">Уверенность: <strong>{(currentTerm.confidence * 100).toFixed(1)}%</strong></span>
            )}
            {currentTerm.group_title && <span className="badge badge-dim">{currentTerm.group_title}</span>}
            {currentTerm.group_id === 0 && <span className="badge badge-dim">глобальный</span>}
            {currentTerm.status === 'approved' && <span className="badge badge-success">✓ Одобрено</span>}
            {currentTerm.status === 'rejected' && <span className="badge badge-danger">✗ Отклонено</span>}
            {currentTerm.status === 'pending' && <span className="badge badge-warning">⏳ На проверке</span>}
          </div>

          <div className="qa-block qa-question">
            <div className="qa-label">📝 Термин</div>
            {isEditing ? (
              <input type="text" className="input" value={editedTerm} onChange={e => setEditedTerm(e.target.value)} />
            ) : (
              <div className="qa-text" style={{ fontSize: '1.2em', fontWeight: 600 }}>{currentTerm.term}</div>
            )}
          </div>

          {(currentTerm.term_type === 'acronym' || currentTerm.definition || isEditing) && (
            <div className="qa-block qa-answer">
              <div className="qa-label">💡 Определение</div>
              {isEditing ? (
                <textarea
                  className="input" rows={3}
                  value={editedDefinition}
                  onChange={e => setEditedDefinition(e.target.value)}
                  placeholder="Расшифровка аббревиатуры"
                />
              ) : (
                <div className="qa-text">{currentTerm.definition || <span className="text-dim">(нет определения)</span>}</div>
              )}
            </div>
          )}

          {canEdit && (
            <div className="comment-section">
              <input type="text" className="input" value={comment} onChange={e => setComment(e.target.value)} placeholder="Комментарий (необязательно)..." maxLength={2000} />
            </div>
          )}

          {canEdit && (
            <div className="verdict-buttons">
              <button
                className={`btn btn-verdict btn-approve ${pendingVerdict?.verdict === 'approved' ? 'btn-armed' : ''}`}
                onClick={() => armOrSubmitVerdict('approved')} disabled={validating}
              >
                {pendingVerdict?.verdict === 'approved' ? '✓ Подтвердить' : '✓ Одобрить'} <kbd>Y</kbd>
              </button>
              <button
                className={`btn btn-verdict btn-reject ${pendingVerdict?.verdict === 'rejected' ? 'btn-armed' : ''}`}
                onClick={() => armOrSubmitVerdict('rejected')} disabled={validating}
              >
                {pendingVerdict?.verdict === 'rejected' ? '✗ Подтвердить' : '✗ Отклонить'} <kbd>N</kbd>
              </button>
              <button className="btn btn-verdict" onClick={() => setIsEditing(!isEditing)} disabled={validating}>
                ✎ {isEditing ? 'Отмена' : 'Редактировать'} <kbd>E</kbd>
              </button>
              {isEditing && (
                <button className="btn btn-verdict btn-primary" onClick={() => submitVerdict('edited')} disabled={validating || !editedTerm.trim()}>
                  💾 Сохранить с правками
                </button>
              )}
              {canEdit && (
                <button className="btn btn-verdict btn-sm" style={{ marginLeft: 'auto', opacity: 0.6 }} onClick={() => handleDelete(currentTerm.id)} disabled={validating}>
                  🗑 Удалить
                </button>
              )}
            </div>
          )}

          {canEdit && pendingVerdict && (
            <div className="verdict-confirm-hint" role="status" aria-live="polite">
              Нажмите {pendingVerdict.verdict === 'approved' ? '«Одобрить» (Y)' : '«Отклонить» (N)'} ещё раз в течение 2 с для подтверждения
            </div>
          )}

          {!canEdit && (
            <div className="card" style={{ textAlign: 'center', marginTop: 16 }}>
              <p className="text-dim">У вас нет прав на валидацию. Режим просмотра.</p>
            </div>
          )}
        </div>
      ) : (
        <div className="loading-text">Загрузка термина...</div>
      )}
    </div>
  )
}
