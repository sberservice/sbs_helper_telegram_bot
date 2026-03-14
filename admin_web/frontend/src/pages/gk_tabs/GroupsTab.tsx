/**
 * Вкладка «Группы» — список GK-групп с подробной статистикой.
 */

import { useCallback, useEffect, useState } from 'react'
import { api, groupsApi, type GKGroup, type GKGroupDetailStats } from '../../api'
import { useAuth } from '../../auth'

export default function GroupsTab() {
  const { hasPermission } = useAuth()
  const canEdit = hasPermission('gk_knowledge', 'edit')

  const [groups, setGroups] = useState<GKGroup[]>([])
  const [disabledGroupIds, setDisabledGroupIds] = useState<Set<number>>(new Set())
  const [gkConfig, setGkConfig] = useState<Awaited<ReturnType<typeof groupsApi.getGKGroups>> | null>(null)
  const [collectedGroups, setCollectedGroups] = useState<Awaited<ReturnType<typeof groupsApi.getCollectedGroups>>>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [detailStats, setDetailStats] = useState<GKGroupDetailStats | null>(null)
  const [selectedGroupId, setSelectedGroupId] = useState<number | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [actionLoading, setActionLoading] = useState(false)
  const [addGroupId, setAddGroupId] = useState('')
  const [addGroupTitle, setAddGroupTitle] = useState('')
  const [selectedCandidateTargetId, setSelectedCandidateTargetId] = useState('')
  const [selectedConfiguredTargetId, setSelectedConfiguredTargetId] = useState('')

  const fetchGroups = useCallback(() => {
    setLoading(true)
    Promise.all([
      api.gkGroups(),
      groupsApi.getGKGroups().catch(() => ({ groups: [], test_target_group: null, test_target_groups: [] })),
      groupsApi.getCollectedGroups().catch(() => []),
    ])
      .then(([dbGroups, config, collected]) => {
        setGroups(dbGroups)
        setGkConfig(config)
        setCollectedGroups(collected)
        setSelectedCandidateTargetId('')
        setSelectedConfiguredTargetId(String(config.test_target_group?.id ?? config.test_target_groups?.[0]?.id ?? ''))
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

  const handleAddGKGroup = useCallback(async () => {
    if (!addGroupId.trim()) return
    setActionLoading(true)
    setError('')
    try {
      await groupsApi.addGKGroup({ id: Number(addGroupId), title: addGroupTitle.trim() })
      setAddGroupId('')
      setAddGroupTitle('')
      fetchGroups()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка добавления группы')
    } finally {
      setActionLoading(false)
    }
  }, [addGroupId, addGroupTitle, fetchGroups])

  const handleRemoveGKGroup = useCallback(async (groupId: number) => {
    setActionLoading(true)
    setError('')
    try {
      await groupsApi.removeGKGroup(groupId)
      fetchGroups()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка удаления группы')
    } finally {
      setActionLoading(false)
    }
  }, [fetchGroups])

  const handleToggleGKGroup = useCallback(async (groupId: number, disabled: boolean) => {
    setActionLoading(true)
    setError('')
    try {
      await groupsApi.toggleGKGroup(groupId, disabled)
      fetchGroups()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка переключения статуса группы')
    } finally {
      setActionLoading(false)
    }
  }, [fetchGroups])

  const handleAddTestTargetOption = useCallback(async () => {
    if (!selectedCandidateTargetId.trim()) return
    const groupId = Number(selectedCandidateTargetId)
    if (!Number.isInteger(groupId) || groupId === 0) return

    const candidate = collectedGroups.find(g => g.group_id === groupId)
    setActionLoading(true)
    setError('')
    try {
      await groupsApi.addGKTestTargetOption({
        id: groupId,
        title: candidate?.group_title || 'Без названия',
        participants: null,
      })
      fetchGroups()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка добавления в список test target')
    } finally {
      setActionLoading(false)
    }
  }, [collectedGroups, selectedCandidateTargetId, fetchGroups])

  const handleSetActiveTestTarget = useCallback(async () => {
    if (!selectedConfiguredTargetId.trim()) return
    const groupId = Number(selectedConfiguredTargetId)
    if (!Number.isInteger(groupId) || groupId === 0) return

    const target = gkConfig?.test_target_groups?.find(g => g.id === groupId)
    if (!target) return

    setActionLoading(true)
    setError('')
    try {
      await groupsApi.setGKTestTarget(target)
      fetchGroups()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка установки активной test target группы')
    } finally {
      setActionLoading(false)
    }
  }, [gkConfig, selectedConfiguredTargetId, fetchGroups])

  const handleRemoveTestTargetOption = useCallback(async () => {
    if (!selectedConfiguredTargetId.trim()) return
    const groupId = Number(selectedConfiguredTargetId)
    if (!Number.isInteger(groupId) || groupId === 0) return

    setActionLoading(true)
    setError('')
    try {
      await groupsApi.removeGKTestTargetOption(groupId)
      fetchGroups()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка удаления test target группы из списка')
    } finally {
      setActionLoading(false)
    }
  }, [selectedConfiguredTargetId, fetchGroups])

  const handleClearTestTarget = useCallback(async () => {
    setActionLoading(true)
    setError('')
    try {
      await groupsApi.clearGKTestTarget()
      fetchGroups()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка очистки активной test target группы')
    } finally {
      setActionLoading(false)
    }
  }, [fetchGroups])

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

      {canEdit && gkConfig && (
        <div className="card" style={{ marginBottom: 16 }}>
          <h3>⚙️ Управление отслеживаемыми GK-группами</h3>
          <p className="text-dim" style={{ marginBottom: 12 }}>
            CRUD конфигурации config/gk_groups.json для GK Collector и GK Responder.
          </p>

          {gkConfig.groups.length === 0 ? (
            <p className="text-dim" style={{ marginBottom: 12 }}>Нет настроенных групп</p>
          ) : (
            <table className="pm-table" style={{ marginBottom: 16 }}>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Название</th>
                  <th>Статус</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {gkConfig.groups.map(g => (
                  <tr key={g.id} className={g.disabled ? 'pm-row-disabled' : ''}>
                    <td><code>{g.id}</code></td>
                    <td>{g.title || '—'}</td>
                    <td>
                      <button
                        className={`btn btn-sm ${g.disabled ? 'btn-warning' : 'btn-success'}`}
                        disabled={actionLoading}
                        onClick={() => handleToggleGKGroup(g.id, !g.disabled)}
                        title={g.disabled ? 'Включить группу' : 'Отключить группу'}
                      >
                        {g.disabled ? '⏸ Отключена' : '✓ Активна'}
                      </button>
                    </td>
                    <td>
                      <button
                        className="btn btn-sm btn-danger"
                        disabled={actionLoading}
                        onClick={() => handleRemoveGKGroup(g.id)}
                        title="Удалить"
                      >
                        ✕
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          <div className="pm-add-group-form">
            <input
              type="number"
              className="input input-sm"
              placeholder="ID группы"
              value={addGroupId}
              onChange={e => setAddGroupId(e.target.value)}
              style={{ width: 180 }}
            />
            <input
              type="text"
              className="input input-sm"
              placeholder="Название (опционально)"
              value={addGroupTitle}
              onChange={e => setAddGroupTitle(e.target.value)}
              style={{ width: 240 }}
            />
            <button
              className="btn btn-sm btn-success"
              disabled={actionLoading || !addGroupId.trim()}
              onClick={handleAddGKGroup}
            >
              + Добавить
            </button>
          </div>

          <div style={{ marginTop: 24 }}>
            <h4>↪️ Test target group (redirect test mode)</h4>

            {gkConfig.test_target_group ? (
              <div className="pm-test-target-info">
                <span>
                  <strong>{gkConfig.test_target_group.title}</strong> (ID: {gkConfig.test_target_group.id})
                  {gkConfig.test_target_group.participants != null && (
                    <span className="text-dim">, участников: {gkConfig.test_target_group.participants}</span>
                  )}
                </span>
                <button
                  className="btn btn-sm btn-danger"
                  disabled={actionLoading}
                  onClick={handleClearTestTarget}
                >
                  Очистить
                </button>
              </div>
            ) : (
              <p className="text-dim">Не установлена</p>
            )}

            <div style={{ marginTop: 12 }}>
              <label className="text-dim" style={{ display: 'block', marginBottom: 6 }}>
                Добавить в список test target из собранных групп:
              </label>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                <select
                  className="input input-sm"
                  value={selectedCandidateTargetId}
                  onChange={e => setSelectedCandidateTargetId(e.target.value)}
                  style={{ minWidth: 320 }}
                >
                  <option value="">— Выберите группу —</option>
                  {collectedGroups
                    .filter(g => !gkConfig.test_target_groups.some(tt => tt.id === g.group_id))
                    .map(g => (
                      <option key={g.group_id} value={g.group_id}>
                        {g.group_title || 'Без названия'} (ID: {g.group_id}, msg: {g.message_count})
                      </option>
                    ))}
                </select>
                <button
                  className="btn btn-sm btn-success"
                  disabled={actionLoading || !selectedCandidateTargetId}
                  onClick={handleAddTestTargetOption}
                >
                  + В список
                </button>
              </div>
            </div>

            <div style={{ marginTop: 12 }}>
              <label className="text-dim" style={{ display: 'block', marginBottom: 6 }}>
                Список test target групп:
              </label>
              {gkConfig.test_target_groups.length === 0 ? (
                <p className="text-dim">Список пуст</p>
              ) : (
                <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                  <select
                    className="input input-sm"
                    value={selectedConfiguredTargetId}
                    onChange={e => setSelectedConfiguredTargetId(e.target.value)}
                    style={{ minWidth: 320 }}
                  >
                    {gkConfig.test_target_groups.map(g => (
                      <option key={g.id} value={g.id}>
                        {g.title || 'Без названия'} (ID: {g.id})
                      </option>
                    ))}
                  </select>
                  <button
                    className="btn btn-sm btn-success"
                    disabled={actionLoading || !selectedConfiguredTargetId}
                    onClick={handleSetActiveTestTarget}
                  >
                    Сделать активной
                  </button>
                  <button
                    className="btn btn-sm btn-danger"
                    disabled={actionLoading || !selectedConfiguredTargetId}
                    onClick={handleRemoveTestTargetOption}
                  >
                    Удалить из списка
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

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
