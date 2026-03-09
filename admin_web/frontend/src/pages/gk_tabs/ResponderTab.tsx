/**
 * Вкладка «Лог автоответчика» — просмотр истории автоматических ответов.
 */

import { useCallback, useEffect, useState } from 'react'
import { api, type GKResponderEntry, type GKResponderSummary, type GKGroup } from '../../api'

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
  const [expandedId, setExpandedId] = useState<number | null>(null)

  useEffect(() => {
    api.gkGroups().then(setGroups).catch(() => {})
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [logRes, sumRes] = await Promise.all([
        api.gkResponderLog({ page, page_size: pageSize, group_id: groupId, dry_run: dryRun, min_confidence: minConfidence }),
        api.gkResponderSummary(groupId ?? undefined),
      ])
      setEntries(logRes.entries)
      setTotal(logRes.total)
      setSummary(sumRes)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка загрузки')
    } finally {
      setLoading(false)
    }
  }, [page, pageSize, groupId, dryRun, minConfidence])

  useEffect(() => { load() }, [load])

  const totalPages = Math.ceil(total / pageSize)

  return (
    <div className="gk-responder-tab">
      {error && <div className="alert alert-danger">{error}</div>}

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
      </div>

      {/* Записи */}
      {loading ? (
        <div className="loading-text">Загрузка...</div>
      ) : entries.length === 0 ? (
        <div className="card empty-state"><p>Нет записей</p></div>
      ) : (
        <>
          <div className="responder-list">
            {entries.map(entry => (
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
                  <span className="pair-confidence">{(entry.confidence * 100).toFixed(0)}%</span>
                  {entry.group_title && <span className="badge badge-dim">{entry.group_title}</span>}
                  {entry.responded_at && <span className="text-dim">{entry.responded_at}</span>}
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
              </div>
            ))}
          </div>

          {totalPages > 1 && (
            <div className="pagination">
              <button className="btn btn-sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>← Назад</button>
              <span className="text-dim">Страница {page} из {totalPages}</span>
              <button className="btn btn-sm" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>Далее →</button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
