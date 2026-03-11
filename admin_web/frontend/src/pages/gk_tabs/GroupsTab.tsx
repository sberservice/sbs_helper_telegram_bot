/**
 * Вкладка «Группы» — список GK-групп с подробной статистикой.
 */

import { useCallback, useEffect, useState } from 'react'
import { api, groupsApi, type GKGroup, type GKGroupDetailStats } from '../../api'

export default function GroupsTab() {
  const [groups, setGroups] = useState<GKGroup[]>([])
  const [disabledGroupIds, setDisabledGroupIds] = useState<Set<number>>(new Set())
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [detailStats, setDetailStats] = useState<GKGroupDetailStats | null>(null)
  const [selectedGroupId, setSelectedGroupId] = useState<number | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  const fetchGroups = useCallback(() => {
    setLoading(true)
    Promise.all([
      api.gkGroups(),
      groupsApi.getGKGroups().catch(() => ({ groups: [], test_target_group: null })),
    ])
      .then(([dbGroups, config]) => {
        setGroups(dbGroups)
        const disabled = new Set<number>()
        for (const g of config.groups) {
          if (g.disabled) disabled.add(g.id)
        }
        setDisabledGroupIds(disabled)
      })
      .catch(err => setError(err instanceof Error ? err.message : 'Ошибка'))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { fetchGroups() }, [fetchGroups])

  const loadDetail = useCallback(async (groupId: number) => {
    if (selectedGroupId === groupId) {
      setSelectedGroupId(null)
      setDetailStats(null)
      return
    }
    setSelectedGroupId(groupId)
    setDetailLoading(true)
    try {
      const stats = await api.gkGroupStats(groupId)
      setDetailStats(stats)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка загрузки')
    } finally {
      setDetailLoading(false)
    }
  }, [selectedGroupId])

  if (loading) return <div className="loading-text">Загрузка групп...</div>

  return (
    <div className="gk-groups-tab">
      {error && <div className="alert alert-danger">{error}</div>}

      {groups.length === 0 ? (
        <div className="card empty-state"><p>Нет мониторируемых групп</p></div>
      ) : (
        <div className="groups-grid">
          {groups.map(g => (
            <div
              key={g.group_id}
              className={`card group-card ${selectedGroupId === g.group_id ? 'group-selected' : ''} ${disabledGroupIds.has(g.group_id) ? 'group-card-disabled' : ''}`}
              onClick={() => loadDetail(g.group_id)}
            >
              <div className="group-card-header">
                <h3>
                  {g.group_title || `Группа ${g.group_id}`}
                  {disabledGroupIds.has(g.group_id) && (
                    <span className="badge badge-warning" style={{ marginLeft: 8, fontSize: 11 }}>⏸ Отключена</span>
                  )}
                </h3>
                <span className="text-dim">ID: {g.group_id}</span>
              </div>
              <div className="group-card-stats">
                <span><strong>{g.message_count}</strong> сообщ.</span>
                <span><strong>{g.sender_count}</strong> отправит.</span>
                <span><strong>{g.pair_count}</strong> Q&A-пар</span>
                <span><strong>{g.validated_count}</strong> провалидир.</span>
                <span>{g.question_pct}% вопросов</span>
              </div>
              {g.first_message_date && (
                <div className="text-dim" style={{ marginTop: 6, fontSize: 12 }}>
                  {g.first_message_date} — {g.last_message_date}
                </div>
              )}

              {selectedGroupId === g.group_id && (
                <div className="group-detail" style={{ marginTop: 12 }}>
                  {detailLoading ? (
                    <div className="loading-text">Загрузка...</div>
                  ) : detailStats ? (
                    <div className="stats-bar" style={{ flexWrap: 'wrap' }}>
                      <div className="stat">
                        <span className="stat-value">{detailStats.qa_thread_reply}</span>
                        <span className="stat-label">Thread</span>
                      </div>
                      <div className="stat">
                        <span className="stat-value">{detailStats.qa_llm_inferred}</span>
                        <span className="stat-label">LLM</span>
                      </div>
                      <div className="stat">
                        <span className="stat-value">{detailStats.responder_count}</span>
                        <span className="stat-label">Ответов</span>
                      </div>
                      <div className="stat">
                        <span className="stat-value">{detailStats.image_count}</span>
                        <span className="stat-label">Изображ.</span>
                      </div>
                    </div>
                  ) : null}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
