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
  type TermRecountStatus,
  type TermUsageMessage,
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
  const [usageMessages, setUsageMessages] = useState<TermUsageMessage[]>([])
  const [usageLoading, setUsageLoading] = useState(false)
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
  const [pageSize, setPageSize] = useState<number>(() => {
    try {
      const raw = window.localStorage.getItem('gk_terms_page_size')
      const parsed = raw ? Number(raw) : 50
      return [10, 50, 100, 500].includes(parsed) ? parsed : 50
    } catch {
      return 50
    }
  })
  const [groupId, setGroupId] = useState<number | null>(null)
  const [termType, setTermType] = useState<string | null>(null)
  const [status, setStatus] = useState<string | null>('pending')
  const [minConfidence, setMinConfidence] = useState<number | null>(null)
  const [searchInput, setSearchInput] = useState('')
  const [searchText, setSearchText] = useState<string | null>(null)
  const [sortBy, setSortBy] = useState<'created_at' | 'term' | 'confidence' | 'id' | 'group_id' | 'status' | 'message_count'>('created_at')
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
  const [recountRunning, setRecountRunning] = useState(false)
  const [recountTaskId, setRecountTaskId] = useState<string | null>(null)
  const [recountStatus, setRecountStatus] = useState<TermRecountStatus | null>(null)
  const [progressNowTs, setProgressNowTs] = useState<number>(Date.now())

  // Ручное добавление
  const [showAdd, setShowAdd] = useState(false)
  const [addGroupId, setAddGroupId] = useState<number | ''>(0)
  const [addTerm, setAddTerm] = useState('')
  const [addDefinition, setAddDefinition] = useState('')
  const [addSubmitting, setAddSubmitting] = useState(false)
  const [resetSubmitting, setResetSubmitting] = useState(false)

  // Загрузка списка
  const loadTerms = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const result: TermListResponse = await api.listTerms({
        page,
        page_size: pageSize,
        group_id: groupId,
        has_definition: termType === 'with_definition' ? true : termType === 'without_definition' ? false : undefined,
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

  useEffect(() => {
    try {
      window.localStorage.setItem('gk_terms_page_size', String(pageSize))
    } catch {
      // noop
    }
  }, [pageSize])

  useEffect(() => { loadTerms() }, [loadTerms])

  // Загрузка деталей термина
  const loadTermDetail = useCallback(async (termId: number) => {
    try {
      const [detail, usage] = await Promise.all([
        api.getTermDetail(termId),
        api.getTermUsageMessages(termId, 10),
      ])
      setCurrentTerm(detail)
      setUsageMessages(usage)
      setComment('')
      setEditedTerm(detail.term)
      setEditedDefinition(detail.definition || '')
      setIsEditing(false)
      setPendingVerdict(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка загрузки термина')
      setUsageMessages([])
    } finally {
      setUsageLoading(false)
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
    setUsageLoading(true)
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
  }, [canEdit, addSubmitting, addTerm, addDefinition, addGroupId, loadTerms])

  const handleResetTerms = useCallback(async () => {
    if (!canEdit || resetSubmitting) return
    const sure = window.confirm(
      'Это действие удалит ВСЕ термины и ВСЮ историю валидации терминов. Продолжить?',
    )
    if (!sure) return

    const confirmation = window.prompt('Введите фразу подтверждения: NUKE_TERMS')
    if (!confirmation) return

    setResetSubmitting(true)
    try {
      const result = await api.resetTermsData({ confirmation_text: confirmation })
      setShowAdd(false)
      setShowScan(false)
      setMode('list')
      setCurrentTerm(null)
      setUsageMessages([])
      setPage(1)
      await loadTerms()
      window.alert(`Готово. Удалено терминов: ${result.terms_deleted}, валидаций: ${result.validations_deleted}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка очистки таблиц терминов')
    } finally {
      setResetSubmitting(false)
    }
  }, [canEdit, resetSubmitting, loadTerms])

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

  const handleRecount = useCallback(async () => {
    if (!canEdit || recountRunning || !scanGroupId) return
    setRecountRunning(true)
    setRecountStatus(null)
    try {
      const res = await api.triggerTermRecount({
        group_id: Number(scanGroupId),
      })
      setRecountTaskId(res.task_id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка запуска пересчёта')
      setRecountRunning(false)
    }
  }, [canEdit, recountRunning, scanGroupId])

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

  // Полл статуса пересчёта message_count
  useEffect(() => {
    if (!recountTaskId) return
    let cancelled = false
    const poll = async () => {
      try {
        const st = await api.getTermRecountStatus(recountTaskId)
        if (cancelled) return
        setRecountStatus(st)
        if (st.status === 'completed' || st.status === 'failed') {
          setRecountRunning(false)
          if (st.status === 'completed') loadTerms()
          return
        }
        setTimeout(poll, 2000)
      } catch {
        if (!cancelled) setRecountRunning(false)
      }
    }
    poll()
    return () => { cancelled = true }
  }, [recountTaskId, loadTerms])

  // Локальный таймер для актуализации ETA между поллами.
  useEffect(() => {
    if (!scanRunning && !recountRunning) return
    const id = window.setInterval(() => setProgressNowTs(Date.now()), 1000)
    return () => window.clearInterval(id)
  }, [scanRunning, recountRunning])

  const formatDuration = useCallback((seconds: number): string => {
    const safe = Math.max(0, Math.round(seconds))
    const hours = Math.floor(safe / 3600)
    const minutes = Math.floor((safe % 3600) / 60)
    const secs = safe % 60
    if (hours > 0) return `${hours}ч ${minutes}м`
    if (minutes > 0) return `${minutes}м ${secs}с`
    return `${secs}с`
  }, [])

  const buildEtaText = useCallback((startedAt?: string, percent?: number): string | null => {
    if (!startedAt || percent == null || percent <= 0 || percent >= 100) return null
    const startedTs = new Date(startedAt).getTime()
    if (!Number.isFinite(startedTs) || startedTs <= 0) return null
    const elapsedSec = (progressNowTs - startedTs) / 1000
    if (elapsedSec <= 0) return null

    const totalSec = elapsedSec / (percent / 100)
    const remainingSec = Math.max(0, totalSec - elapsedSec)
    const etaDate = new Date(progressNowTs + remainingSec * 1000)
    return `Осталось ~${formatDuration(remainingSec)} · ETA ${etaDate.toLocaleTimeString()}`
  }, [formatDuration, progressNowTs])

  const getScanPercent = useCallback((status: TermScanStatus | null): number => {
    if (!status) return 0
    if (typeof status.progress?.percent === 'number') {
      return Math.max(0, Math.min(100, status.progress.percent))
    }
    const latestProgress = status.progress_log && status.progress_log.length > 0
      ? status.progress_log[status.progress_log.length - 1]
      : null
    if (latestProgress && typeof latestProgress.percent === 'number') {
      return Math.max(0, Math.min(100, latestProgress.percent))
    }
    if (status.status === 'completed') return 100
    return 0
  }, [])

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
            <div className="stat"><span className="stat-value">{stats.with_definition}</span><span className="stat-label">С определением</span></div>
            <div className="stat stat-accent"><span className="stat-value">{stats.without_definition}</span><span className="stat-label">Без определения</span></div>
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
            <option value="">Все</option>
            <option value="with_definition">С определением</option>
            <option value="without_definition">Без определения</option>
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
            <option value="message_count">Сортировка: частота</option>
            <option value="status">Сортировка: статус</option>
            <option value="group_id">Сортировка: группа</option>
            <option value="id">Сортировка: ID</option>
          </select>
          <select className="input input-sm" value={sortOrder} onChange={e => { setSortOrder(e.target.value as typeof sortOrder); setPage(1) }}>
            <option value="desc">По убыванию</option>
            <option value="asc">По возрастанию</option>
          </select>
          <select
            className="input input-sm"
            value={String(pageSize)}
            onChange={e => {
              setPageSize(Number(e.target.value))
              setPage(1)
            }}
            title="Терминов на странице"
          >
            <option value="10">10 / стр</option>
            <option value="50">50 / стр</option>
            <option value="100">100 / стр</option>
            <option value="500">500 / стр</option>
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
            <button className="btn btn-sm" onClick={handleResetTerms} disabled={resetSubmitting}>
              {resetSubmitting ? '⏳ Очистка...' : '☢ Очистить термины и валидации'}
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
                <label className="text-dim" style={{ fontSize: 12 }}>Термин</label>
                <input type="text" className="input input-sm" value={addTerm} onChange={e => setAddTerm(e.target.value)} placeholder="напр. ккт" maxLength={100} />
              </div>
              <div>
                <label className="text-dim" style={{ fontSize: 12 }}>Определение</label>
                <input type="text" className="input input-sm" value={addDefinition} onChange={e => setAddDefinition(e.target.value)} placeholder="расшифровка (необязательно)" maxLength={500} />
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
              <button
                className="btn btn-sm"
                onClick={handleRecount}
                disabled={recountRunning || !scanGroupId}
                title="Пересчитать частоту встречаемости терминов по сообщениям группы"
              >
                {recountRunning ? '⏳ Пересчёт...' : '♻ Пересчитать message_count'}
              </button>
            </div>
            {scanStatus && (
              <>
                {(() => {
                  const etaText = buildEtaText(scanStatus.started_at, scanStatus.progress?.percent)
                  return etaText ? (
                    <div className="text-dim" style={{ marginTop: 8, fontSize: 12 }}>{etaText}</div>
                  ) : null
                })()}
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
                      , новых: {scanStatus.result?.terms_new ?? scanStatus.progress?.terms_new ?? 0}
                      {(scanStatus.result?.terms_updated ?? scanStatus.progress?.terms_updated ?? 0) > 0 && (
                        <>, обновлено: {scanStatus.result?.terms_updated ?? scanStatus.progress?.terms_updated ?? 0}</>
                      )}
                      {(scanStatus.result?.terms_skipped ?? scanStatus.progress?.terms_skipped ?? 0) > 0 && (
                        <>, пропущено (рассмотрено): {scanStatus.result?.terms_skipped ?? scanStatus.progress?.terms_skipped ?? 0}</>
                      )}
                    </>
                  )}
                  {scanStatus.status === 'failed' && `Ошибка: ${scanStatus.error || 'Неизвестная ошибка'}`}
                </div>

                {
                  (() => {
                    const scanPercent = getScanPercent(scanStatus)
                    return (
                  <div className="card" style={{ marginTop: 8, padding: 10 }}>
                    <div style={{ fontSize: 12, marginBottom: 6, color: 'var(--text-dim)' }}>
                      Прогресс: {`${Math.round(scanPercent)}%`}
                    </div>
                    <div style={{ width: '100%', height: 6, background: 'var(--surface-2)', borderRadius: 4, overflow: 'hidden', marginBottom: 8 }}>
                      <div
                        style={{
                          width: `${scanPercent}%`,
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
                    )
                  })()
                }
              </>
            )}
            {recountStatus && (
              <>
                {(() => {
                  const etaText = buildEtaText(recountStatus.started_at, recountStatus.progress?.percent)
                  return etaText ? (
                    <div className="text-dim" style={{ marginTop: 8, fontSize: 12 }}>{etaText}</div>
                  ) : null
                })()}
                <div
                  className={`alert alert-${recountStatus.status === 'completed' ? 'success' : recountStatus.status === 'failed' ? 'danger' : 'info'}`}
                  style={{ marginTop: 12 }}
                >
                  {(recountStatus.status === 'running' || recountStatus.status === 'queued') && (
                    <>
                      ⏳ {recountStatus.progress?.message || 'Пересчёт выполняется...'}
                      {typeof recountStatus.progress?.percent === 'number' ? ` (${Math.round(recountStatus.progress.percent)}%)` : ''}
                    </>
                  )}
                  {recountStatus.status === 'completed' && (
                    <>
                      ✓ Пересчёт завершён: обновлено терминов {recountStatus.result?.updated ?? 0},
                      проанализировано сообщений {recountStatus.result?.messages_scanned ?? 0}
                    </>
                  )}
                  {recountStatus.status === 'failed' && `Ошибка пересчёта: ${recountStatus.error || 'Неизвестная ошибка'}`}
                </div>
                {(recountStatus.progress || recountStatus.status === 'running' || recountStatus.status === 'queued') && (
                  <div className="card" style={{ marginTop: 8, padding: 10 }}>
                    <div style={{ fontSize: 12, marginBottom: 6, color: 'var(--text-dim)' }}>
                      Прогресс: {typeof recountStatus.progress?.percent === 'number' ? `${Math.max(0, Math.min(100, Math.round(recountStatus.progress.percent)))}%` : '—'}
                    </div>
                    <div style={{ width: '100%', height: 6, background: 'var(--surface-2)', borderRadius: 4, overflow: 'hidden' }}>
                      <div
                        style={{
                          width: `${Math.max(0, Math.min(100, recountStatus.progress?.percent ?? 0))}%`,
                          height: '100%',
                          background: 'var(--accent)',
                          transition: 'width 0.2s ease',
                        }}
                      />
                    </div>
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
                    <span className={`badge badge-${term.has_definition ? 'warning' : 'info'}`}>
                      {term.has_definition ? 'С определением' : 'Термин'}
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
                    <span className="text-dim" style={{ marginLeft: 8 }} title="Количество сообщений группы, где найден термин">
                      · msg: {term.message_count ?? 0}
                    </span>
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
            <span className={`badge badge-${currentTerm.has_definition ? 'warning' : 'info'}`}>
              {currentTerm.has_definition ? 'С определением' : 'Термин'}
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

          {(currentTerm.has_definition || currentTerm.definition || isEditing) && (
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

          <div className="qa-block">
            <div className="qa-label">📚 Примеры сообщений с термином</div>
            {usageLoading ? (
              <div className="text-dim">Загрузка примеров...</div>
            ) : usageMessages.length === 0 ? (
              <div className="text-dim">Совпадения не найдены</div>
            ) : (
              <div style={{ display: 'grid', gap: 8 }}>
                {usageMessages.map((message) => {
                  const sourceText = message.matched_text || message.message_text || message.caption || message.image_description || ''
                  const matchedFieldLabel = message.matched_field || 'message_text'
                  const dateText = message.message_date
                    ? new Date(message.message_date * 1000).toLocaleString()
                    : '—'
                  return (
                    <div key={message.id} className="card" style={{ padding: 10 }}>
                      <div className="text-dim" style={{ fontSize: 12, marginBottom: 6 }}>
                        {dateText} · {message.sender_name || `user:${message.sender_id ?? 'unknown'}`} · msg #{message.telegram_message_id} · поле: {matchedFieldLabel}
                      </div>
                      <div style={{ whiteSpace: 'pre-wrap' }}>{sourceText || <span className="text-dim">(пустое сообщение)</span>}</div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>

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
