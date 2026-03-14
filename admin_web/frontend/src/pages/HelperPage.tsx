import { useCallback, useEffect, useState } from 'react'
import { groupsApi, type HelperGroupsConfig } from '../api'

const HELPER_TABS = [
  { key: 'group-settings', label: 'Настройки групп', icon: '👥' },
] as const

type HelperTabKey = (typeof HELPER_TABS)[number]['key']

function HelperGroupsSettingsTab() {
  const [helperConfig, setHelperConfig] = useState<HelperGroupsConfig | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [addGroupId, setAddGroupId] = useState('')
  const [addGroupTitle, setAddGroupTitle] = useState('')
  const [actionLoading, setActionLoading] = useState(false)

  const fetchAll = useCallback(() => {
    setLoading(true)
    groupsApi.getHelperGroups()
      .then((helper) => {
        setHelperConfig(helper)
        setError('')
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { fetchAll() }, [fetchAll])

  const handleAddHelperGroup = async () => {
    if (!addGroupId.trim()) return
    setActionLoading(true)
    try {
      await groupsApi.addHelperGroup({ id: Number(addGroupId), title: addGroupTitle.trim() })
      setAddGroupId('')
      setAddGroupTitle('')
      fetchAll()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setActionLoading(false)
    }
  }

  const handleRemoveHelperGroup = async (groupId: number) => {
    setActionLoading(true)
    try {
      await groupsApi.removeHelperGroup(groupId)
      fetchAll()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setActionLoading(false)
    }
  }

  const handleToggleHelperGroup = async (groupId: number, disabled: boolean) => {
    setActionLoading(true)
    try {
      await groupsApi.toggleHelperGroup(groupId, disabled)
      fetchAll()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setActionLoading(false)
    }
  }

  if (loading) return <div className="loading-text">Загрузка...</div>

  return (
    <div>
      {error && <div className="alert alert-danger" style={{ marginBottom: 12 }}>{error}</div>}

      {helperConfig && (
        <div className="card">
          <h3>🆘 The Helper — отслеживаемые группы</h3>
          <p className="text-dim">Группы, в которых The Helper слушает /helpme (config/helper_groups.json)</p>

          {helperConfig.groups.length === 0 ? (
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
                {helperConfig.groups.map(g => (
                  <tr key={g.id} className={g.disabled ? 'pm-row-disabled' : ''}>
                    <td><code>{g.id}</code></td>
                    <td>{g.title || '—'}</td>
                    <td>
                      <button
                        className={`btn btn-sm ${g.disabled ? 'btn-warning' : 'btn-success'}`}
                        disabled={actionLoading}
                        onClick={() => handleToggleHelperGroup(g.id, !g.disabled)}
                        title={g.disabled ? 'Включить группу' : 'Отключить группу'}
                      >
                        {g.disabled ? '⏸ Отключена' : '✓ Активна'}
                      </button>
                    </td>
                    <td>
                      <button
                        className="btn btn-sm btn-danger"
                        disabled={actionLoading}
                        onClick={() => handleRemoveHelperGroup(g.id)}
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
              style={{ width: 220 }}
            />
            <button
              className="btn btn-sm btn-success"
              disabled={actionLoading || !addGroupId.trim()}
              onClick={handleAddHelperGroup}
            >
              + Добавить
            </button>
            <button className="btn btn-sm" onClick={fetchAll} title="Обновить">🔄</button>
          </div>
        </div>
      )}
    </div>
  )
}

export default function HelperPage() {
  const [activeTab, setActiveTab] = useState<HelperTabKey>('group-settings')

  return (
    <div className="pm-page">
      <div className="page-header">
        <h1>🆘 The Helper</h1>
        <p className="text-dim">Управление настройками The Helper</p>
      </div>

      <div className="gk-tab-bar">
        {HELPER_TABS.map(tab => (
          <button
            key={tab.key}
            className={`gk-tab ${activeTab === tab.key ? 'gk-tab-active' : ''}`}
            onClick={() => setActiveTab(tab.key)}
          >
            <span className="gk-tab-icon">{tab.icon}</span>
            <span className="gk-tab-label">{tab.label}</span>
          </button>
        ))}
      </div>

      <div className="gk-tab-content">
        {activeTab === 'group-settings' && <HelperGroupsSettingsTab />}
      </div>
    </div>
  )
}
