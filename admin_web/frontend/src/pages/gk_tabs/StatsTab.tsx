/**
 * Вкладка «Статистика» — обзорные метрики GK.
 * Отображает общую статистику, тайм-лайн по дням и распределение уверенности.
 */

import { useCallback, useEffect, useState } from 'react'
import { api, type GKOverviewStats, type GKTimelineEntry, type GKConfidenceBucket, type GKGroup } from '../../api'

export default function StatsTab() {
  const [overview, setOverview] = useState<GKOverviewStats | null>(null)
  const [timeline, setTimeline] = useState<GKTimelineEntry[]>([])
  const [distribution, setDistribution] = useState<GKConfidenceBucket[]>([])
  const [groups, setGroups] = useState<GKGroup[]>([])
  const [groupId, setGroupId] = useState<number | undefined>(undefined)
  const [days, setDays] = useState(30)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [ov, tl, dist] = await Promise.all([
        api.gkStatsOverview(groupId),
        api.gkStatsTimeline(groupId, days),
        api.gkStatsDistribution(groupId),
      ])
      setOverview(ov)
      setTimeline(tl.dates || [])
      setDistribution(dist)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка загрузки статистики')
    } finally {
      setLoading(false)
    }
  }, [groupId, days])

  useEffect(() => {
    api.gkGroups().then(setGroups).catch(() => {})
  }, [])

  useEffect(() => { load() }, [load])

  if (loading && !overview) {
    return <div className="loading-text">Загрузка статистики...</div>
  }

  return (
    <div className="gk-stats-tab">
      {error && <div className="alert alert-danger">{error}</div>}

      {/* Фильтры */}
      <div className="filters-bar">
        <select
          className="input input-sm"
          value={groupId ?? ''}
          onChange={e => setGroupId(e.target.value ? Number(e.target.value) : undefined)}
        >
          <option value="">Все группы</option>
          {groups.map(g => (
            <option key={g.group_id} value={g.group_id}>
              {g.group_title || `Группа ${g.group_id}`}
            </option>
          ))}
        </select>
        <select
          className="input input-sm"
          value={days}
          onChange={e => setDays(Number(e.target.value))}
        >
          <option value={7}>7 дней</option>
          <option value={14}>14 дней</option>
          <option value={30}>30 дней</option>
          <option value={90}>90 дней</option>
          <option value={180}>180 дней</option>
          <option value={365}>365 дней</option>
        </select>
      </div>

      {/* Обзор */}
      {overview && (
        <div className="stats-bar" style={{ flexWrap: 'wrap' }}>
          <div className="stat">
            <span className="stat-value">{overview.total_messages}</span>
            <span className="stat-label">Сообщений</span>
          </div>
          <div className="stat">
            <span className="stat-value">{overview.total_qa_pairs}</span>
            <span className="stat-label">Q&A-пар</span>
          </div>
          <div className="stat stat-success">
            <span className="stat-value">{overview.qa_pairs_approved}</span>
            <span className="stat-label">Одобрено</span>
          </div>
          <div className="stat stat-danger">
            <span className="stat-value">{overview.qa_pairs_rejected}</span>
            <span className="stat-label">Отклонено</span>
          </div>
          <div className="stat">
            <span className="stat-value">{overview.qa_pairs_unvalidated}</span>
            <span className="stat-label">Не проверено</span>
          </div>
          <div className="stat stat-accent">
            <span className="stat-value">{overview.qa_pairs_vector_indexed}</span>
            <span className="stat-label">В индексе</span>
          </div>
          <div className="stat">
            <span className="stat-value">{overview.total_responder_entries}</span>
            <span className="stat-label">Ответов</span>
          </div>
          <div className="stat">
            <span className="stat-value">{overview.total_images}</span>
            <span className="stat-label">Изображений</span>
          </div>
        </div>
      )}

      {/* Тайм-лайн */}
      {timeline.length > 0 && (
        <div className="card" style={{ marginTop: 16 }}>
          <h3 style={{ marginBottom: 12 }}>Динамика за {days} дней</h3>
          <div className="timeline-simple">
            {timeline.map(entry => (
              <div key={entry.date} className="timeline-row">
                <span className="timeline-date">{entry.date}</span>
                <span className="timeline-bar">
                  <span
                    className="timeline-bar-fill timeline-bar-messages"
                    style={{ width: `${Math.min(entry.messages, 200) / 2}%` }}
                    title={`${entry.messages} сообщений`}
                  />
                </span>
                <span className="timeline-val">{entry.messages} / {entry.qa_pairs}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Распределение уверенности */}
      {distribution.length > 0 && (
        <div className="card" style={{ marginTop: 16 }}>
          <h3 style={{ marginBottom: 12 }}>Распределение уверенности Q&A</h3>
          <div className="distribution-bars">
            {distribution.map(b => (
              <div key={b.range_label} className="distrib-row">
                <span className="distrib-label">{b.range_label}</span>
                <span className="distrib-bar">
                  <span
                    className="distrib-bar-fill"
                    style={{ width: `${Math.min(b.count / (Math.max(...distribution.map(d => d.count)) || 1) * 100, 100)}%` }}
                  />
                </span>
                <span className="distrib-count">{b.count}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
