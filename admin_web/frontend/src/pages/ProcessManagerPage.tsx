/**
 * Главная страница модуля «Менеджер процессов».
 *
 * Три вкладки:
 * - Обзор — карточки процессов по категориям
 * - Процесс — детали выбранного процесса (запуск/остановка, логи, флаги)
 * - История — агрегированная история запусков
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  api,
  connectProcessLogs,
  groupsApi,
  type CollectedGroupInfo,
  type GKGroupsConfig,
  type GroupEntry,
  type HelperGroupsConfig,
  type LaunchConfigProcessEntry,
  type LaunchConfigResponse,
  type PresetDef,
  type ProcessHistoryResponse,
  type ProcessRegistryInfo,
  type ProcessRunRecord,
  type ProcessStatusInfo,
  type TestTargetGroup,
} from '../api'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatUptime(seconds: number | null): string {
  if (seconds == null) return '—'
  if (seconds < 60) return `${Math.floor(seconds)}с`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}м ${Math.floor(seconds % 60)}с`
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  return `${h}ч ${m}м`
}

function statusBadgeClass(status: string): string {
  switch (status) {
    case 'running': return 'badge badge-success'
    case 'stopped': return 'badge badge-dim'
    case 'crashed': return 'badge badge-danger'
    case 'starting': return 'badge badge-warning'
    case 'stopping': return 'badge badge-warning'
    default: return 'badge'
  }
}

function statusLabel(status: string): string {
  switch (status) {
    case 'running': return 'Работает'
    case 'stopped': return 'Остановлен'
    case 'crashed': return 'Упал'
    case 'starting': return 'Запускается'
    case 'stopping': return 'Останавливается'
    default: return status
  }
}

function formatDateShort(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
}

// ---------------------------------------------------------------------------
// Tab definitions
// ---------------------------------------------------------------------------

const TABS = [
  { key: 'overview', label: 'Обзор', icon: '📊' },
  { key: 'detail', label: 'Процесс', icon: '🔎' },
  { key: 'groups', label: 'Группы', icon: '👥' },
  { key: 'history', label: 'История', icon: '📜' },
  { key: 'launch', label: 'Запуск', icon: '🚀' },
] as const

// ===================================================================
// Overview Tab
// ===================================================================

function OverviewTab({ onSelectProcess }: { onSelectProcess: (key: string) => void }) {
  const [categories, setCategories] = useState<Record<string, ProcessStatusInfo[]>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const fetchData = useCallback(() => {
    api.pmListProcesses()
      .then(data => { setCategories(data.categories); setError('') })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 5000)
    return () => clearInterval(interval)
  }, [fetchData])

  if (loading) return <div className="loading-text">Загрузка...</div>
  if (error) return <div className="alert alert-danger">{error}</div>

  const categoryOrder = Object.keys(categories)

  return (
    <div className="pm-overview">
      {categoryOrder.map(cat => (
        <div key={cat} className="pm-category-group">
          <h3 className="pm-category-title">{cat}</h3>
          <div className="pm-cards-grid">
            {categories[cat].map(proc => (
              <div
                key={proc.key}
                className={`pm-process-card pm-status-${proc.status}`}
                onClick={() => onSelectProcess(proc.key)}
              >
                <div className="pm-card-header">
                  <span className="pm-card-icon">{proc.icon}</span>
                  <div className="pm-card-title-area">
                    <h4 className="pm-card-name">{proc.name}</h4>
                    <span className={`${statusBadgeClass(proc.status)} pm-status-badge-compact`}>
                      {proc.status === 'running' && <span className="pm-status-dot pm-dot-running" />}
                      {proc.status === 'crashed' && <span className="pm-status-dot pm-dot-crashed" />}
                      {statusLabel(proc.status)}
                    </span>
                  </div>
                  <div className="pm-card-meta pm-card-meta-compact">
                    {proc.status === 'running' && <span className="text-dim">PID: {proc.pid}</span>}
                    {proc.status === 'running' && <span className="text-dim">{formatUptime(proc.uptime_seconds)}</span>}
                    {proc.process_type === 'daemon' && (
                      <span className="badge badge-dim">daemon</span>
                    )}
                  </div>
                </div>
                <div className="pm-card-meta pm-card-meta-secondary">
                  {proc.status === 'running' && proc.current_preset && (
                    <span className="badge badge-accent">{proc.current_preset}</span>
                  )}
                  {proc.status === 'running' && !proc.current_preset && proc.current_flags?.length
                    ? <span className="text-dim">{proc.current_flags.join(' ')}</span>
                    : <span className="text-dim">{proc.description}</span>}
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

// ===================================================================
// Process Detail Tab
// ===================================================================

function ProcessDetailTab({ processKey }: { processKey: string | null }) {
  const [status, setStatus] = useState<ProcessStatusInfo | null>(null)
  const [registry, setRegistry] = useState<ProcessRegistryInfo | null>(null)
  const [history, setHistory] = useState<ProcessRunRecord[]>([])
  const [historyTotal, setHistoryTotal] = useState(0)
  const [output, setOutput] = useState<Array<{ timestamp: string; line: string }>>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [actionLoading, setActionLoading] = useState(false)
  const [selectedPreset, setSelectedPreset] = useState<string>('')
  const [customFlags, setCustomFlags] = useState<string>('')
  const [useCustomFlags, setUseCustomFlags] = useState(false)
  const [liveMode, setLiveMode] = useState(false)
  const [persistOnRestart, setPersistOnRestart] = useState(true)
  const [showLaunchForm, setShowLaunchForm] = useState(false)
  const [launchFormPreset, setLaunchFormPreset] = useState<PresetDef | null>(null)
  const logEndRef = useRef<HTMLDivElement>(null)
  const logViewerRef = useRef<HTMLDivElement>(null)
  const wsRef = useRef<ReturnType<typeof connectProcessLogs> | null>(null)
  const liveModeRef = useRef(false)

  // Синхронизировать ref с state, чтобы fetchAll не зависел от liveMode
  useEffect(() => { liveModeRef.current = liveMode }, [liveMode])

  const isRunning = status?.status === 'running' || status?.status === 'starting'

  // Fetch status + registry + history
  const fetchAll = useCallback(() => {
    if (!processKey) return
    Promise.all([
      api.pmGetProcess(processKey),
      api.pmGetRegistry(processKey),
      api.pmGetHistory(processKey, 1, 10),
      api.pmGetOutput(processKey, 300),
    ])
      .then(([st, reg, hist, out]) => {
        setStatus(st)
        setRegistry(reg)
        setHistory(hist.runs)
        setHistoryTotal(hist.total)
        if (!liveModeRef.current) setOutput(out.lines)
        setError('')
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [processKey])

  useEffect(() => {
    setLoading(true)
    setOutput([])
    setLiveMode(false)
    fetchAll()
    const interval = setInterval(() => {
      if (!processKey) return
      api.pmGetProcess(processKey).then(setStatus).catch(() => {})
    }, 3000)
    return () => clearInterval(interval)
  }, [processKey, fetchAll])

  // WebSocket live logs
  useEffect(() => {
    if (!liveMode || !processKey) {
      wsRef.current?.close()
      wsRef.current = null
      return
    }
    const ws = connectProcessLogs(
      processKey,
      (entry) => setOutput(prev => [...prev.slice(-998), entry]),
      () => setLiveMode(false),
    )
    wsRef.current = ws
    return () => ws.close()
  }, [liveMode, processKey])

  // Auto-scroll logs (only the log container, not the whole page)
  useEffect(() => {
    const viewer = logViewerRef.current
    if (viewer) {
      viewer.scrollTop = viewer.scrollHeight
    }
  }, [output])

  // Actions
  const handleStart = async (formData?: Record<string, unknown>) => {
    if (!processKey) return
    setActionLoading(true)
    try {
      const body: { preset?: string; flags?: string[]; form_data?: Record<string, unknown>; persist?: boolean } = {}
      if (useCustomFlags && customFlags.trim()) {
        body.flags = customFlags.trim().split(/\s+/)
      } else if (selectedPreset) {
        body.preset = selectedPreset
        if (formData) {
          body.form_data = formData
        }
      }
      // Передать persist только для daemon-процессов
      if (registry?.process_type === 'daemon') {
        body.persist = persistOnRestart
      }
      const st = await api.pmStartProcess(processKey, body)
      setStatus(st)
      setLiveMode(true)
      setShowLaunchForm(false)
      setLaunchFormPreset(null)
      fetchAll()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setActionLoading(false)
    }
  }

  const handlePresetClick = (preset: PresetDef) => {
    setSelectedPreset(preset.name)
    if (preset.requires_form && preset.form_type) {
      setLaunchFormPreset(preset)
      setShowLaunchForm(true)
    } else {
      setShowLaunchForm(false)
      setLaunchFormPreset(null)
    }
  }

  const handleStop = async () => {
    if (!processKey) return
    setActionLoading(true)
    try {
      const st = await api.pmStopProcess(processKey)
      setStatus(st)
      fetchAll()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setActionLoading(false)
    }
  }

  const handleRestart = async () => {
    if (!processKey) return
    setActionLoading(true)
    try {
      const body: { preset?: string; flags?: string[] } = {}
      if (useCustomFlags && customFlags.trim()) {
        body.flags = customFlags.trim().split(/\s+/)
      } else if (selectedPreset) {
        body.preset = selectedPreset
      }
      const st = await api.pmRestartProcess(processKey, body)
      setStatus(st)
      setLiveMode(true)
      fetchAll()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setActionLoading(false)
    }
  }

  if (!processKey) {
    return (
      <div className="card empty-state">
        <p>Выберите процесс из вкладки «Обзор»</p>
      </div>
    )
  }

  if (loading) return <div className="loading-text">Загрузка...</div>
  if (error && !status) return <div className="alert alert-danger">{error}</div>

  return (
    <div className="pm-detail">
      {/* Header */}
      <div className="pm-detail-header">
        <div className="pm-detail-title">
          <span className="pm-detail-icon">{status?.icon}</span>
          <h2>{status?.name}</h2>
          <span className={statusBadgeClass(status?.status || 'unknown')}>
            {status?.status === 'running' && <span className="pm-status-dot pm-dot-running" />}
            {statusLabel(status?.status || 'unknown')}
          </span>
        </div>
        <p className="text-dim">{status?.description}</p>
        {status?.status === 'running' && (
          <div className="pm-detail-meta">
            <span>PID: <strong>{status.pid}</strong></span>
            <span>Uptime: <strong>{formatUptime(status.uptime_seconds)}</strong></span>
            {status.current_preset && <span>Пресет: <strong>{status.current_preset}</strong></span>}
            {status.current_flags?.length ? (
              <span>Флаги: <code>{status.current_flags.join(' ')}</code></span>
            ) : null}
          </div>
        )}
      </div>

      {error && <div className="alert alert-danger" style={{ marginBottom: 16 }}>{error}</div>}

      {/* Controls */}
      <div className="pm-controls card">
        <h3>Управление</h3>

        {/* Preset selector */}
        {registry && registry.presets.filter(p => !p.hidden).length > 0 && !useCustomFlags && (
          <div className="pm-preset-selector">
            <label className="text-dim">Пресет:</label>
            <div className="pm-preset-list">
              {registry.presets.filter(p => !p.hidden).map(p => (
                <button
                  key={p.name}
                  className={`pm-preset-btn ${selectedPreset === p.name ? 'pm-preset-active' : ''}`}
                  onClick={() => handlePresetClick(p)}
                  title={p.description}
                >
                  <span>{p.icon}</span> {p.name}
                  {p.requires_form && <span className="pm-preset-form-badge">📋</span>}
                </button>
              ))}
            </div>
            {selectedPreset && (
              <p className="text-dim pm-preset-desc">
                {registry.presets.find(p => p.name === selectedPreset)?.description}
                {' — '}
                <code>{registry.presets.find(p => p.name === selectedPreset)?.flags.join(' ') || '(без флагов)'}</code>
              </p>
            )}
          </div>
        )}

        {/* Custom flags */}
        {registry && registry.flags.length > 0 && (
          <div className="pm-custom-flags">
            <label>
              <input
                type="checkbox"
                checked={useCustomFlags}
                onChange={e => setUseCustomFlags(e.target.checked)}
              />
              <span style={{ marginLeft: 6 }}>Ручной ввод флагов</span>
            </label>
            {useCustomFlags && (
              <div style={{ marginTop: 8 }}>
                <input
                  type="text"
                  className="input"
                  placeholder="--flag1 --flag2 value"
                  value={customFlags}
                  onChange={e => setCustomFlags(e.target.value)}
                  style={{ width: '100%' }}
                />
                <div className="pm-available-flags text-dim" style={{ marginTop: 4, fontSize: 12 }}>
                  Доступные флаги: {registry.flags.map(f => f.name).join(', ')}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Action buttons */}
        <div className="pm-action-buttons">
          {!isRunning && registry?.process_type === 'daemon' && (
            <label className="pm-persist-checkbox">
              <input
                type="checkbox"
                checked={persistOnRestart}
                onChange={e => setPersistOnRestart(e.target.checked)}
              />
              <span style={{ marginLeft: 4 }}>Авто-восстановление при перезагрузке</span>
            </label>
          )}
          {!isRunning && (
            <button
              className="btn btn-success"
              disabled={actionLoading || (showLaunchForm && launchFormPreset != null)}
              onClick={() => handleStart()}
            >
              {actionLoading ? '...' : '▶ Запустить'}
            </button>
          )}
          {isRunning && (
            <>
              <button
                className="btn btn-danger"
                disabled={actionLoading}
                onClick={handleStop}
              >
                {actionLoading ? '...' : '⏹ Остановить'}
              </button>
              <button
                className="btn btn-warning"
                disabled={actionLoading}
                onClick={handleRestart}
              >
                {actionLoading ? '...' : '🔄 Перезапустить'}
              </button>
            </>
          )}
        </div>
      </div>

      {/* Launch form for presets that require additional input */}
      {showLaunchForm && launchFormPreset && (
        <LaunchFormDialog
          preset={launchFormPreset}
          onSubmit={(formData) => handleStart(formData)}
          onCancel={() => { setShowLaunchForm(false); setLaunchFormPreset(null); setSelectedPreset('') }}
          loading={actionLoading}
        />
      )}

      {/* Output / Logs */}
      <div className="pm-logs card">
        <div className="pm-logs-header">
          <h3>Вывод</h3>
          <div className="pm-logs-controls">
            <label>
              <input
                type="checkbox"
                checked={liveMode}
                onChange={e => setLiveMode(e.target.checked)}
              />
              <span style={{ marginLeft: 4 }}>Live</span>
            </label>
            <button
              className="btn btn-sm"
              onClick={() => fetchAll()}
              title="Обновить"
            >
              🔄
            </button>
            <button
              className="btn btn-sm"
              onClick={() => setOutput([])}
              title="Очистить"
            >
              🗑
            </button>
          </div>
        </div>
        <div className="pm-log-viewer" ref={logViewerRef}>
          {output.length === 0 ? (
            <div className="pm-log-empty text-dim">Нет вывода</div>
          ) : (
            output.map((entry, i) => (
              <div key={i} className="pm-log-line">
                <span className="pm-log-ts">{entry.timestamp?.slice(11, 19) || ''}</span>
                <span className="pm-log-text">{entry.line}</span>
              </div>
            ))
          )}
          <div ref={logEndRef} />
        </div>
      </div>

      {/* History */}
      <div className="pm-history card">
        <h3>Последние запуски ({historyTotal})</h3>
        {history.length === 0 ? (
          <p className="text-dim">Нет записей</p>
        ) : (
          <table className="pm-table">
            <thead>
              <tr>
                <th>Статус</th>
                <th>Пресет / Флаги</th>
                <th>PID</th>
                <th>Запущен</th>
                <th>Остановлен</th>
                <th>Код</th>
                <th>Причина</th>
              </tr>
            </thead>
            <tbody>
              {history.map(run => (
                <tr key={run.id}>
                  <td><span className={statusBadgeClass(run.status)}>{statusLabel(run.status)}</span></td>
                  <td>{run.preset_name || run.flags?.join(' ') || '—'}</td>
                  <td>{run.pid ?? '—'}</td>
                  <td>{formatDateShort(run.started_at)}</td>
                  <td>{formatDateShort(run.stopped_at)}</td>
                  <td>{run.exit_code ?? '—'}</td>
                  <td>{run.stop_reason || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

// ===================================================================
// Launch Form Dialog
// ===================================================================

function LaunchFormDialog({
  preset,
  onSubmit,
  onCancel,
  loading,
}: {
  preset: PresetDef
  onSubmit: (formData: Record<string, unknown>) => void
  onCancel: () => void
  loading: boolean
}) {
  const [formValues, setFormValues] = useState<Record<string, string | number>>({})
  const [collectedGroups, setCollectedGroups] = useState<CollectedGroupInfo[]>([])
  const [gkGroups, setGkGroups] = useState<GroupEntry[]>([])
  const [gkTestTarget, setGkTestTarget] = useState<TestTargetGroup | null>(null)
  const [gkTestTargets, setGkTestTargets] = useState<TestTargetGroup[]>([])
  const [loadingGroups, setLoadingGroups] = useState(true)

  useEffect(() => {
    const promises: Promise<void>[] = []
    if (preset.form_type === 'gk_test_mode' || preset.form_type === 'gk_redirect_test') {
      promises.push(
        groupsApi.getCollectedGroups()
          .then(setCollectedGroups)
          .catch(() => {}),
        groupsApi.getGKGroups()
          .then(cfg => {
            setGkGroups(cfg.groups)
            setGkTestTarget(cfg.test_target_group ?? null)
            setGkTestTargets(cfg.test_target_groups ?? [])
            if (cfg.test_target_group?.id) {
              setFormValues(prev => ({
                ...prev,
                'redirect-group-id': prev['redirect-group-id'] ?? cfg.test_target_group?.id,
              }))
            }
          })
          .catch(() => {}),
      )
    }
    if (preset.form_type === 'gk_delete_group') {
      promises.push(
        groupsApi.getCollectedGroups()
          .then(setCollectedGroups)
          .catch(() => {}),
      )
    }
    Promise.all(promises).finally(() => setLoadingGroups(false))
  }, [preset.form_type])

  const updateField = (key: string, value: string | number) => {
    setFormValues(prev => ({ ...prev, [key]: value }))
  }

  const handleSubmit = () => {
    onSubmit(formValues)
  }

  const renderFormFields = () => {
    switch (preset.form_type) {
      case 'gk_test_mode':
        return (
          <>
            <div className="pm-form-field">
              <label className="pm-form-label">Реальная группа (база знаний):</label>
              <select
                className="input"
                value={formValues['test-real-group-id'] ?? ''}
                onChange={e => updateField('test-real-group-id', Number(e.target.value))}
              >
                <option value="">— Выберите —</option>
                {gkGroups.map(g => (
                  <option key={g.id} value={g.id}>
                    {g.title || 'Без названия'} (ID: {g.id})
                  </option>
                ))}
              </select>
            </div>
            <div className="pm-form-field">
              <label className="pm-form-label">Тестовая группа (для мониторинга):</label>
              <select
                className="input"
                value={formValues['test-group-id'] ?? ''}
                onChange={e => updateField('test-group-id', Number(e.target.value))}
              >
                <option value="">— Выберите —</option>
                {collectedGroups
                  .filter(g => g.group_id !== formValues['test-real-group-id'])
                  .map(g => (
                    <option key={g.group_id} value={g.group_id}>
                      {g.group_title || 'Без названия'} (ID: {g.group_id}, msg: {g.message_count})
                    </option>
                  ))}
              </select>
              <div className="pm-form-hint text-dim">
                Или введите ID вручную:
                <input
                  type="number"
                  className="input input-sm"
                  style={{ width: 160, marginLeft: 8 }}
                  placeholder="ID группы"
                  value={formValues['test-group-id'] ?? ''}
                  onChange={e => updateField('test-group-id', Number(e.target.value))}
                />
              </div>
            </div>
          </>
        )

      case 'gk_redirect_test': {
        // Если настроен список test-target групп — используем его в приоритете.
        const allGroupsMap = new Map<number, { id: number; title: string }>()
        for (const g of gkTestTargets) allGroupsMap.set(g.id, { id: g.id, title: g.title })
        if (gkTestTarget) allGroupsMap.set(gkTestTarget.id, { id: gkTestTarget.id, title: gkTestTarget.title })
        for (const g of gkGroups) allGroupsMap.set(g.id, { id: g.id, title: g.title })
        for (const g of collectedGroups) {
          if (!allGroupsMap.has(g.group_id)) {
            allGroupsMap.set(g.group_id, { id: g.group_id, title: g.group_title || '' })
          }
        }
        const allGroups = Array.from(allGroupsMap.values())
        return (
          <div className="pm-form-field">
            <label className="pm-form-label">Тестовая группа для перенаправления ответов:</label>
            <select
              className="input"
              value={formValues['redirect-group-id'] ?? ''}
              onChange={e => updateField('redirect-group-id', Number(e.target.value))}
            >
              <option value="">— Выберите —</option>
              {allGroups.map(g => (
                <option key={g.id} value={g.id}>
                  {g.title || 'Без названия'} (ID: {g.id})
                </option>
              ))}
            </select>
            <div className="pm-form-hint text-dim">
              Или введите ID вручную:
              <input
                type="number"
                className="input input-sm"
                style={{ width: 160, marginLeft: 8 }}
                placeholder="ID группы"
                value={formValues['redirect-group-id'] ?? ''}
                onChange={e => updateField('redirect-group-id', Number(e.target.value))}
              />
            </div>
          </div>
        )
      }

      case 'gk_delete_group':
        return (
          <div className="pm-form-field">
            <label className="pm-form-label">Группа для удаления данных:</label>
            <select
              className="input"
              value={formValues['group-id'] ?? ''}
              onChange={e => updateField('group-id', Number(e.target.value))}
            >
              <option value="">— Выберите —</option>
              {collectedGroups.map(g => (
                <option key={g.group_id} value={g.group_id}>
                  {g.group_title || 'Без названия'} (ID: {g.group_id}, сообщений: {g.message_count})
                </option>
              ))}
            </select>
          </div>
        )

      default:
        return <p className="text-dim">Неизвестный тип формы: {preset.form_type}</p>
    }
  }

  const isValid = (): boolean => {
    switch (preset.form_type) {
      case 'gk_test_mode':
        return !!(formValues['test-real-group-id'] && formValues['test-group-id'])
      case 'gk_redirect_test':
        return !!formValues['redirect-group-id']
      case 'gk_delete_group':
        return !!formValues['group-id']
      default:
        return true
    }
  }

  return (
    <div className="pm-launch-form card">
      <h3>{preset.icon} {preset.name}</h3>
      <p className="text-dim">{preset.description}</p>

      {loadingGroups ? (
        <div className="loading-text">Загрузка данных...</div>
      ) : (
        <>
          {renderFormFields()}
          <div className="pm-action-buttons" style={{ marginTop: 16 }}>
            <button
              className="btn btn-success"
              disabled={loading || !isValid()}
              onClick={handleSubmit}
            >
              {loading ? '...' : '▶ Запустить'}
            </button>
            <button
              className="btn"
              onClick={onCancel}
              disabled={loading}
            >
              Отмена
            </button>
          </div>
        </>
      )}
    </div>
  )
}

// ===================================================================
// Groups Tab
// ===================================================================

function GroupsTab() {
  const [gkConfig, setGkConfig] = useState<GKGroupsConfig | null>(null)
  const [helperConfig, setHelperConfig] = useState<HelperGroupsConfig | null>(null)
  const [collected, setCollected] = useState<CollectedGroupInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [activeSection, setActiveSection] = useState<'gk' | 'helper' | 'collected'>('gk')
  const [addGroupId, setAddGroupId] = useState('')
  const [addGroupTitle, setAddGroupTitle] = useState('')
  const [selectedCandidateTargetId, setSelectedCandidateTargetId] = useState('')
  const [selectedConfiguredTargetId, setSelectedConfiguredTargetId] = useState('')
  const [actionLoading, setActionLoading] = useState(false)

  const fetchAll = useCallback(() => {
    setLoading(true)
    Promise.all([
      groupsApi.getGKGroups().catch(() => ({ groups: [], test_target_group: null, test_target_groups: [] })),
      groupsApi.getHelperGroups().catch(() => ({ groups: [] })),
      groupsApi.getCollectedGroups().catch(() => []),
    ])
      .then(([gk, helper, coll]) => {
        setGkConfig(gk)
        setHelperConfig(helper)
        setCollected(coll)
        setSelectedCandidateTargetId('')
        setSelectedConfiguredTargetId(String(gk.test_target_group?.id ?? gk.test_target_groups?.[0]?.id ?? ''))
        setError('')
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { fetchAll() }, [fetchAll])

  const handleAddGKGroup = async () => {
    if (!addGroupId.trim()) return
    setActionLoading(true)
    try {
      await groupsApi.addGKGroup({ id: Number(addGroupId), title: addGroupTitle.trim() })
      setAddGroupId('')
      setAddGroupTitle('')
      fetchAll()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setActionLoading(false)
    }
  }

  const handleRemoveGKGroup = async (groupId: number) => {
    setActionLoading(true)
    try {
      await groupsApi.removeGKGroup(groupId)
      fetchAll()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setActionLoading(false)
    }
  }

  const handleToggleGKGroup = async (groupId: number, disabled: boolean) => {
    setActionLoading(true)
    try {
      await groupsApi.toggleGKGroup(groupId, disabled)
      fetchAll()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setActionLoading(false)
    }
  }

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

  const handleAddTestTargetOption = async () => {
    if (!selectedCandidateTargetId.trim()) return
    const groupId = Number(selectedCandidateTargetId)
    if (!Number.isInteger(groupId) || groupId === 0) return

    const candidate = collected.find(g => g.group_id === groupId)
    setActionLoading(true)
    try {
      await groupsApi.addGKTestTargetOption({
        id: groupId,
        title: candidate?.group_title || 'Без названия',
        participants: null,
      })
      fetchAll()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setActionLoading(false)
    }
  }

  const handleSetActiveTestTarget = async () => {
    if (!selectedConfiguredTargetId.trim()) return
    const groupId = Number(selectedConfiguredTargetId)
    if (!Number.isInteger(groupId) || groupId === 0) return

    const target = gkConfig?.test_target_groups?.find(g => g.id === groupId)
    if (!target) return

    setActionLoading(true)
    try {
      await groupsApi.setGKTestTarget(target)
      fetchAll()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setActionLoading(false)
    }
  }

  const handleRemoveTestTargetOption = async () => {
    if (!selectedConfiguredTargetId.trim()) return
    const groupId = Number(selectedConfiguredTargetId)
    if (!Number.isInteger(groupId) || groupId === 0) return

    setActionLoading(true)
    try {
      await groupsApi.removeGKTestTargetOption(groupId)
      fetchAll()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setActionLoading(false)
    }
  }

  if (loading) return <div className="loading-text">Загрузка...</div>

  const sections = [
    { key: 'gk' as const, label: 'GK Groups', icon: '📡' },
    { key: 'helper' as const, label: 'Helper Groups', icon: '🆘' },
    { key: 'collected' as const, label: 'Собранные (БД)', icon: '💾' },
  ]

  return (
    <div className="pm-groups-tab">
      {error && <div className="alert alert-danger" style={{ marginBottom: 12 }}>{error}</div>}

      <div className="pm-groups-sections">
        {sections.map(s => (
          <button
            key={s.key}
            className={`pm-preset-btn ${activeSection === s.key ? 'pm-preset-active' : ''}`}
            onClick={() => { setActiveSection(s.key); setAddGroupId(''); setAddGroupTitle('') }}
          >
            <span>{s.icon}</span> {s.label}
          </button>
        ))}
        <button className="btn btn-sm" onClick={fetchAll} title="Обновить">🔄</button>
      </div>

      {/* GK Groups */}
      {activeSection === 'gk' && gkConfig && (
        <div className="pm-groups-section card">
          <h3>📡 Group Knowledge — отслеживаемые группы</h3>
          <p className="text-dim">Группы, из которых GK Collector собирает сообщения (config/gk_groups.json)</p>

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
              style={{ width: 220 }}
            />
            <button
              className="btn btn-sm btn-success"
              disabled={actionLoading || !addGroupId.trim()}
              onClick={handleAddGKGroup}
            >
              + Добавить
            </button>
          </div>

          {/* Test target group */}
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
                  onClick={async () => {
                    setActionLoading(true)
                    try {
                      await groupsApi.clearGKTestTarget()
                      fetchAll()
                    } catch (e: any) {
                      setError(e.message)
                    } finally {
                      setActionLoading(false)
                    }
                  }}
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
                  {collected
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

      {/* Helper Groups */}
      {activeSection === 'helper' && helperConfig && (
        <div className="pm-groups-section card">
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
          </div>
        </div>
      )}

      {/* Collected from DB */}
      {activeSection === 'collected' && (
        <div className="pm-groups-section card">
          <h3>💾 Собранные группы (из БД)</h3>
          <p className="text-dim">Группы, из которых уже есть сообщения в таблице gk_messages</p>

          {collected.length === 0 ? (
            <p className="text-dim">Нет собранных данных</p>
          ) : (
            <table className="pm-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Название</th>
                  <th>Сообщений</th>
                  <th>Первое</th>
                  <th>Последнее</th>
                </tr>
              </thead>
              <tbody>
                {collected.map(g => (
                  <tr key={g.group_id}>
                    <td><code>{g.group_id}</code></td>
                    <td>{g.group_title || '—'}</td>
                    <td>{g.message_count.toLocaleString()}</td>
                    <td>{formatDateShort(g.first_message)}</td>
                    <td>{formatDateShort(g.last_message)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  )
}

// ===================================================================
// History Tab
// ===================================================================

function HistoryTab() {
  const [data, setData] = useState<ProcessHistoryResponse | null>(null)
  const [page, setPage] = useState(1)
  const [filterKey, setFilterKey] = useState('')
  const [filterStatus, setFilterStatus] = useState('')
  const [loading, setLoading] = useState(true)

  const fetchHistory = useCallback(() => {
    setLoading(true)
    api.pmGetAllHistory(page, 25, filterKey || undefined, filterStatus || undefined)
      .then(setData)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [page, filterKey, filterStatus])

  useEffect(() => { fetchHistory() }, [fetchHistory])

  return (
    <div className="pm-history-tab">
      <div className="filters-bar">
        <input
          className="input input-sm"
          placeholder="Ключ процесса"
          value={filterKey}
          onChange={e => { setFilterKey(e.target.value); setPage(1) }}
        />
        <select
          className="input input-sm"
          value={filterStatus}
          onChange={e => { setFilterStatus(e.target.value); setPage(1) }}
        >
          <option value="">Все статусы</option>
          <option value="running">running</option>
          <option value="stopped">stopped</option>
          <option value="crashed">crashed</option>
          <option value="killed">killed</option>
        </select>
        <button className="btn btn-sm" onClick={fetchHistory}>🔄</button>
      </div>

      {loading ? (
        <div className="loading-text">Загрузка...</div>
      ) : !data || data.runs.length === 0 ? (
        <div className="card empty-state"><p>Нет записей</p></div>
      ) : (
        <>
          <table className="pm-table">
            <thead>
              <tr>
                <th>Процесс</th>
                <th>Статус</th>
                <th>Пресет / Флаги</th>
                <th>PID</th>
                <th>Запущен</th>
                <th>Остановлен</th>
                <th>Код</th>
                <th>Причина</th>
              </tr>
            </thead>
            <tbody>
              {data.runs.map(run => (
                <tr key={run.id}>
                  <td><strong>{run.process_key}</strong></td>
                  <td><span className={statusBadgeClass(run.status)}>{statusLabel(run.status)}</span></td>
                  <td>{run.preset_name || run.flags?.join(' ') || '—'}</td>
                  <td>{run.pid ?? '—'}</td>
                  <td>{formatDateShort(run.started_at)}</td>
                  <td>{formatDateShort(run.stopped_at)}</td>
                  <td>{run.exit_code ?? '—'}</td>
                  <td>{run.stop_reason || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="pm-pagination">
            <button
              className="btn btn-sm"
              disabled={page <= 1}
              onClick={() => setPage(p => p - 1)}
            >
              ← Назад
            </button>
            <span className="text-dim">
              Страница {data.page} из {Math.ceil(data.total / data.page_size) || 1}
            </span>
            <button
              className="btn btn-sm"
              disabled={page * (data?.page_size ?? 25) >= (data?.total ?? 0)}
              onClick={() => setPage(p => p + 1)}
            >
              Вперёд →
            </button>
          </div>
        </>
      )}
    </div>
  )
}

// ===================================================================
// Launch Config Tab
// ===================================================================

function LaunchConfigTab() {
  const [config, setConfig] = useState<LaunchConfigResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [applying, setApplying] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [applyResults, setApplyResults] = useState<Record<string, string> | null>(null)
  const [dirty, setDirty] = useState(false)

  const fetchConfig = useCallback(() => {
    setLoading(true)
    api.pmGetLaunchConfig()
      .then(data => { setConfig(data); setError(''); setDirty(false) })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { fetchConfig() }, [fetchConfig])

  const toggleProcess = (key: string) => {
    if (!config) return
    const proc = config.processes[key]
    if (!proc) return
    setConfig({
      ...config,
      processes: {
        ...config.processes,
        [key]: { ...proc, enabled: !proc.enabled },
      },
    })
    setDirty(true)
    setSuccess('')
    setApplyResults(null)
  }

  const setPreset = (key: string, presetName: string | null) => {
    if (!config) return
    const proc = config.processes[key]
    if (!proc) return
    const preset = proc.available_presets.find(p => p.name === presetName)
    setConfig({
      ...config,
      processes: {
        ...config.processes,
        [key]: {
          ...proc,
          preset: presetName,
          flags: preset ? [...preset.flags] : [],
        },
      },
    })
    setDirty(true)
    setSuccess('')
    setApplyResults(null)
  }

  const handleSave = async () => {
    if (!config) return
    setSaving(true)
    setError('')
    setSuccess('')
    try {
      const payload: Record<string, { enabled: boolean; flags: string[]; preset: string | null }> = {}
      for (const [key, proc] of Object.entries(config.processes)) {
        payload[key] = {
          enabled: proc.enabled,
          flags: proc.flags,
          preset: proc.preset,
        }
      }
      await api.pmUpdateLaunchConfig({ processes: payload })
      setSuccess('Конфигурация сохранена')
      setDirty(false)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }

  const handleApply = async () => {
    if (!config) return
    // Сначала сохраним, если есть изменения.
    if (dirty) {
      await handleSave()
    }
    setApplying(true)
    setError('')
    setApplyResults(null)
    try {
      const result = await api.pmApplyLaunchConfig()
      setApplyResults(result.actions)
      setSuccess('Конфигурация применена')
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setApplying(false)
    }
  }

  if (loading) return <div className="loading-text">Загрузка...</div>
  if (error && !config) return <div className="alert alert-danger">{error}</div>
  if (!config) return null

  // Группировка процессов по категории для display.
  const categories: Record<string, Array<[string, LaunchConfigProcessEntry]>> = {}
  for (const [key, proc] of Object.entries(config.processes)) {
    const cat = proc.category || 'Прочие'
    if (!categories[cat]) categories[cat] = []
    categories[cat].push([key, proc])
  }

  const actionLabel = (action: string) => {
    if (action === 'started') return '✅ Запущен'
    if (action === 'stopped') return '⏹️ Остановлен'
    if (action === 'unchanged') return '— Без изменений'
    if (action.startsWith('error:')) return `❌ ${action}`
    return action
  }

  return (
    <div className="pm-launch-config">
      <div className="pm-launch-header">
        <div>
          <h3 style={{ margin: 0 }}>Конфигурация автозапуска</h3>
          <p className="text-dim" style={{ marginTop: 4 }}>
            Процессы, которые запускаются автоматически при старте системы.
            Изменения сохраняются в <code>deploy/launch_config.json</code>.
          </p>
        </div>
        <div className="pm-launch-actions">
          <button
            className="btn btn-primary"
            onClick={handleSave}
            disabled={saving || !dirty}
          >
            {saving ? 'Сохранение...' : 'Сохранить'}
          </button>
          <button
            className="btn btn-accent"
            onClick={handleApply}
            disabled={applying}
            title="Сохранить и запустить/остановить процессы по конфигурации"
          >
            {applying ? 'Применение...' : 'Применить сейчас'}
          </button>
        </div>
      </div>

      {error && <div className="alert alert-danger" style={{ marginTop: 12 }}>{error}</div>}
      {success && <div className="alert alert-success" style={{ marginTop: 12 }}>{success}</div>}

      {applyResults && (
        <div className="pm-apply-results" style={{ marginTop: 12 }}>
          <h4 style={{ marginBottom: 8 }}>Результаты применения:</h4>
          <div className="pm-apply-results-grid">
            {Object.entries(applyResults).map(([key, action]) => {
              const proc = config.processes[key]
              return (
                <div key={key} className="pm-apply-result-row">
                  <span>{proc?.icon || '📦'} {proc?.name || key}</span>
                  <span className="text-dim">{actionLabel(action)}</span>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {Object.entries(categories).map(([cat, procs]) => (
        <div key={cat} className="pm-category-group" style={{ marginTop: 20 }}>
          <h3 className="pm-category-title">{cat}</h3>
          <div className="pm-launch-grid">
            {procs.map(([key, proc]) => (
              <div
                key={key}
                className={`pm-launch-card ${proc.enabled ? 'pm-launch-enabled' : 'pm-launch-disabled'}`}
              >
                <div className="pm-launch-card-header">
                  <span className="pm-card-icon">{proc.icon}</span>
                  <div className="pm-launch-card-info">
                    <h4 className="pm-card-name">{proc.name}</h4>
                    <span className="text-dim" style={{ fontSize: '0.85em' }}>{proc.description}</span>
                  </div>
                  <label className="pm-toggle">
                    <input
                      type="checkbox"
                      checked={proc.enabled}
                      onChange={() => toggleProcess(key)}
                    />
                    <span className="pm-toggle-slider" />
                  </label>
                </div>

                {proc.enabled && proc.available_presets.length > 0 && (
                  <div className="pm-launch-preset-row">
                    <span className="text-dim" style={{ fontSize: '0.85em' }}>Режим:</span>
                    <select
                      value={proc.preset || ''}
                      onChange={e => setPreset(key, e.target.value || null)}
                      className="pm-launch-select"
                    >
                      <option value="">Без пресета</option>
                      {proc.available_presets.map(p => (
                        <option key={p.name} value={p.name}>
                          {p.icon} {p.name}
                        </option>
                      ))}
                    </select>
                  </div>
                )}

                {proc.enabled && proc.preset && (
                  <div className="pm-launch-flags-info">
                    {(() => {
                      const preset = proc.available_presets.find(p => p.name === proc.preset)
                      if (!preset) return null
                      return (
                        <span className="text-dim" style={{ fontSize: '0.8em' }}>
                          {preset.description}
                          {preset.flags.length > 0 && ` (${preset.flags.join(' ')})`}
                        </span>
                      )
                    })()}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

// ===================================================================
// Main Page
// ===================================================================

export default function ProcessManagerPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const tabFromUrl = searchParams.get('tab')
  const processFromUrl = searchParams.get('process')

  const [activeTab, setActiveTab] = useState(
    TABS.some(t => t.key === tabFromUrl) ? tabFromUrl! : 'overview',
  )
  const [selectedProcess, setSelectedProcess] = useState<string | null>(processFromUrl)

  const handleTabChange = (key: string) => {
    setActiveTab(key)
    const params: Record<string, string> = { tab: key }
    if (selectedProcess && key === 'detail') params.process = selectedProcess
    setSearchParams(params, { replace: true })
  }

  const handleSelectProcess = (key: string) => {
    setSelectedProcess(key)
    setActiveTab('detail')
    setSearchParams({ tab: 'detail', process: key }, { replace: true })
  }

  return (
    <div className="pm-page">
      <div className="page-header">
        <h1>⚙️ Менеджер процессов</h1>
        <p className="text-dim">Управление скриптами и демонами SBS Archie</p>
      </div>

      {/* Tab bar */}
      <div className="gk-tab-bar">
        {TABS.map(tab => (
          <button
            key={tab.key}
            className={`gk-tab ${activeTab === tab.key ? 'gk-tab-active' : ''}`}
            onClick={() => handleTabChange(tab.key)}
          >
            <span className="gk-tab-icon">{tab.icon}</span>
            <span className="gk-tab-label">{tab.label}</span>
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="gk-tab-content">
        {activeTab === 'overview' && (
          <OverviewTab onSelectProcess={handleSelectProcess} />
        )}
        {activeTab === 'detail' && (
          <ProcessDetailTab processKey={selectedProcess} />
        )}
        {activeTab === 'groups' && (
          <GroupsTab />
        )}
        {activeTab === 'history' && (
          <HistoryTab />
        )}
        {activeTab === 'launch' && (
          <LaunchConfigTab />
        )}
      </div>
    </div>
  )
}
