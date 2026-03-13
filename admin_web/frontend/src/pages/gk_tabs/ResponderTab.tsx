/**
 * Вкладка «Лог автоответчика» — просмотр истории автоматических ответов.
 */

import { useCallback, useEffect, useState } from 'react'
import { api, type GKResponderEntry, type GKResponderSummary, type GKGroup } from '../../api'

function formatTs(value: string | number | null | undefined): string {
  if (value == null) return '—'
  if (typeof value === 'number' && Number.isFinite(value)) {
    const date = new Date(value * 1000)
    return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString()
  }
  const asNumber = Number(value)
  if (!Number.isNaN(asNumber) && Number.isFinite(asNumber)) {
    const date = new Date(asNumber * 1000)
    if (!Number.isNaN(date.getTime())) return date.toLocaleString()
  }
  const parsed = new Date(String(value))
  return Number.isNaN(parsed.getTime()) ? String(value) : parsed.toLocaleString()
}

function extractLLMMeta(payload: string | null | undefined): { model: string; temperature: string } {
  if (!payload) return { model: '—', temperature: '—' }
  try {
    const parsed = JSON.parse(payload) as { model_override?: unknown; temperature?: unknown }
    const model = typeof parsed.model_override === 'string' && parsed.model_override.trim()
      ? parsed.model_override.trim()
      : '—'
    const rawTemp = parsed.temperature
    const tempNumber =
      typeof rawTemp === 'number' ? rawTemp :
      typeof rawTemp === 'string' ? Number(rawTemp) :
      Number.NaN
    const temperature = Number.isFinite(tempNumber) ? String(tempNumber) : '—'
    return { model, temperature }
  } catch {
    return { model: '—', temperature: '—' }
  }
}

export default function ResponderTab() {
  const [entries, setEntries] = useState<GKResponderEntry[]>([])
  const [total, setTotal] = useState(0)
  const [summary, setSummary] = useState<GKResponderSummary | null>(null)
  const [groups, setGroups] = useState<GKGroup[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const [page, setPage] = useState(1)
  const [pageSize] = useState(20)
  const [groupId, setGroupId] = useState<number | null>(null)
  const [dryRun, setDryRun] = useState<boolean | null>(null)
  const [minConfidence, setMinConfidence] = useState<number | null>(null)
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [subpage, setSubpage] = useState<'log' | 'overview'>('log')

  useEffect(() => {
    api.gkGroups().then(setGroups).catch(() => {})
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const summaryPromise = api.gkResponderSummary({
        group_id: groupId,
        date_from: dateFrom || null,
        date_to: dateTo || null,
      })

      if (subpage === 'overview') {
        const sumRes = await summaryPromise
        setSummary(sumRes)
        setEntries([])
        setTotal(0)
        return
      }

      const [logRes, sumRes] = await Promise.all([
        api.gkResponderLog({ page, page_size: pageSize, group_id: groupId, dry_run: dryRun, min_confidence: minConfidence }),
        summaryPromise,
      ])
      setEntries(logRes.entries)
      setTotal(logRes.total)
      setSummary(sumRes)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка загрузки')
    } finally {
      setLoading(false)
    }
  }, [page, pageSize, groupId, dryRun, minConfidence, dateFrom, dateTo, subpage])

  useEffect(() => { load() }, [load])

  const totalPages = Math.ceil(total / pageSize)

  return (
    <div className="gk-responder-tab">
      {error && <div className="alert alert-danger">{error}</div>}

      <div className="filters-bar" style={{ marginBottom: 12 }}>
        <button
          className={`btn btn-sm ${subpage === 'log' ? 'btn-primary' : ''}`}
          onClick={() => { setSubpage('log'); setPage(1) }}
        >
          Лог
        </button>
        <button
          className={`btn btn-sm ${subpage === 'overview' ? 'btn-primary' : ''}`}
          onClick={() => { setSubpage('overview'); setPage(1) }}
        >
          Обзор
        </button>
      </div>

      {/* Сводка */}
      {summary && (
        <div className="stats-bar">
          <div className="stat">
            <span className="stat-value">{summary.total_entries}</span>
            <span className="stat-label">Всего</span>
          </div>
          <div className="stat stat-success">
            <span className="stat-value">{summary.live_count}</span>
            <span className="stat-label">Live</span>
          </div>
          <div className="stat">
            <span className="stat-value">{summary.dry_run_count}</span>
            <span className="stat-label">Dry-run</span>
          </div>
          <div className="stat stat-accent">
            <span className="stat-value">{(summary.avg_confidence * 100).toFixed(0)}%</span>
            <span className="stat-label">Ср. уверенность</span>
          </div>
        </div>
      )}

      {/* Фильтры */}
      <div className="filters-bar">
        <select className="input input-sm" value={groupId ?? ''} onChange={e => { setGroupId(e.target.value ? Number(e.target.value) : null); setPage(1) }}>
          <option value="">Все группы</option>
          {groups.map(g => (
            <option key={g.group_id} value={g.group_id}>{g.group_title || `Группа ${g.group_id}`}</option>
          ))}
        </select>
        <input className="input input-sm" type="date" value={dateFrom} onChange={e => { setDateFrom(e.target.value); setPage(1) }} />
        <input className="input input-sm" type="date" value={dateTo} onChange={e => { setDateTo(e.target.value); setPage(1) }} />
        {subpage === 'log' && (
          <>
            <select className="input input-sm" value={dryRun === null ? '' : String(dryRun)} onChange={e => { setDryRun(e.target.value === '' ? null : e.target.value === 'true'); setPage(1) }}>
              <option value="">Все режимы</option>
              <option value="true">Dry-run</option>
              <option value="false">Live</option>
            </select>
            <select className="input input-sm" value={minConfidence ?? ''} onChange={e => { setMinConfidence(e.target.value ? Number(e.target.value) : null); setPage(1) }}>
              <option value="">Любая уверенность</option>
              <option value="0.9">≥ 0.9</option>
              <option value="0.8">≥ 0.8</option>
              <option value="0.7">≥ 0.7</option>
            </select>
          </>
        )}
      </div>

      {/* Записи */}
      {subpage === 'overview' ? (
        <div className="card" style={{ marginTop: 12 }}>
          <p>Обзор статистики учитывает выбранные группу и диапазон дат.</p>
        </div>
      ) : (
        loading ? (
          <div className="loading-text">Загрузка...</div>
        ) : entries.length === 0 ? (
          <div className="card empty-state"><p>Нет записей</p></div>
        ) : (
          <>
            <div className="responder-list">
              {entries.map(entry => {
                const llmMeta = extractLLMMeta(entry.llm_request_payload)
                return (
                  <div
                    key={entry.id}
                    className={`card responder-entry ${entry.dry_run ? 'responder-dry' : 'responder-live'}`}
                    onClick={() => setExpandedId(expandedId === entry.id ? null : entry.id)}
                  >
                    <div className="responder-entry-header">
                      <span className="pair-id">#{entry.id}</span>
                      <span className={`badge ${entry.dry_run ? 'badge-dim' : 'badge-success'}`}>
                        {entry.dry_run ? 'Dry-run' : 'Live'}
                      </span>
                      {entry.llm_request_payload && (
                        <span className="badge badge-success">LLM saved</span>
                      )}
                      <span className="pair-confidence">{(entry.confidence * 100).toFixed(0)}%</span>
                      {entry.group_title && <span className="badge badge-dim">{entry.group_title}</span>}
                    </div>
                    <div className="text-dim" style={{ marginBottom: 6 }}>
                      Вопрос: {formatTs(entry.question_message_date)} · Ответ: {formatTs(entry.responded_at)}
                    </div>
                    <div className="text-dim" style={{ marginBottom: 6 }}>
                      Модель: {llmMeta.model} · Temp: {llmMeta.temperature}
                    </div>
                    {entry.question_text && (
                      <div className="pair-question">
                        <strong>Q:</strong> {expandedId === entry.id ? entry.question_text : entry.question_text.slice(0, 200) + (entry.question_text.length > 200 ? '...' : '')}
                      </div>
                    )}
                    {expandedId === entry.id && entry.answer_text && (
                      <div className="pair-answer">
                        <strong>A:</strong> {entry.answer_text}
                      </div>
                    )}
                    {expandedId === entry.id && entry.llm_request_payload && (
                      <div className="pair-answer" style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                        <strong>LLM request:</strong> {entry.llm_request_payload}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>

            {totalPages > 1 && (
              <div className="pagination">
                <button className="btn btn-sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>← Назад</button>
                <span className="text-dim">Страница {page} из {totalPages}</span>
                <button className="btn btn-sm" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>Далее →</button>
              </div>
            )}
          </>
        )
      )}
    </div>
  )
}
