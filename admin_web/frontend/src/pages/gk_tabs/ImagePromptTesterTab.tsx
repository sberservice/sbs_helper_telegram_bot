/**
 * Вкладка «Image Prompt Tester» — отдельный blind A/B тестер описаний изображений.
 */

import { type CSSProperties, useCallback, useEffect, useMemo, useState } from 'react'
import {
  api,
  type GKGroup,
  type GKImageComparison,
  type GKImagePrompt,
  type GKImageSessionEstimate,
  type GKImagePromptSession,
  type GKImagePromptTesterStats,
  type GKSessionResults,
} from '../../api'
import { useAuth } from '../../auth'

type SubView = 'sessions' | 'prompts' | 'stats' | 'compare' | 'results'

const thStyle: CSSProperties = {
  textAlign: 'left',
  padding: '8px 10px',
  borderBottom: '1px solid var(--border)',
}

const tdStyle: CSSProperties = {
  padding: '8px 10px',
  borderBottom: '1px solid var(--border)',
  verticalAlign: 'top',
}

export default function ImagePromptTesterTab() {
  const { hasPermission } = useAuth()
  const canEdit = hasPermission('gk_knowledge', 'edit')

  const [subView, setSubView] = useState<SubView>('sessions')
  const [error, setError] = useState('')

  const [prompts, setPrompts] = useState<GKImagePrompt[]>([])
  const [promptsLoading, setPromptsLoading] = useState(false)
  const [showPromptForm, setShowPromptForm] = useState(false)
  const [editPrompt, setEditPrompt] = useState<GKImagePrompt | null>(null)
  const [promptForm, setPromptForm] = useState({ label: '', prompt_text: '', model_name: '', temperature: '0.3' })
  const [supportedModels, setSupportedModels] = useState<string[]>([])
  const [defaultModelName, setDefaultModelName] = useState<string | null>(null)

  const [sessions, setSessions] = useState<GKImagePromptSession[]>([])
  const [sessionsLoading, setSessionsLoading] = useState(false)
  const [showSessionForm, setShowSessionForm] = useState(false)
  const [sessionForm, setSessionForm] = useState({
    name: '',
    prompt_ids: [] as number[],
    image_count: '20',
    source_group_id: '',
    source_date_from: '',
    source_date_to: '',
  })
  const [sessionEstimate, setSessionEstimate] = useState<GKImageSessionEstimate | null>(null)
  const [estimateLoading, setEstimateLoading] = useState(false)
  const [groups, setGroups] = useState<GKGroup[]>([])

  const [activeSessionId, setActiveSessionId] = useState<number | null>(null)
  const [comparison, setComparison] = useState<GKImageComparison | null>(null)
  const [compareLoading, setCompareLoading] = useState(false)
  const [voteLoading, setVoteLoading] = useState(false)
  const [votedCount, setVotedCount] = useState(0)

  const [results, setResults] = useState<GKSessionResults | null>(null)
  const [aggregateStats, setAggregateStats] = useState<GKImagePromptTesterStats | null>(null)

  const loadPrompts = useCallback(async () => {
    setPromptsLoading(true)
    try {
      const data = await api.gkImagePrompts(false)
      setPrompts(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка загрузки промптов')
    } finally {
      setPromptsLoading(false)
    }
  }, [])

  const loadSessions = useCallback(async () => {
    setSessionsLoading(true)
    try {
      const data = await api.gkImageSessions()
      setSessions(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка загрузки сессий')
    } finally {
      setSessionsLoading(false)
    }
  }, [])

  const loadAggregateStats = useCallback(async () => {
    try {
      const data = await api.gkImagePromptTesterStats()
      setAggregateStats(data)
    } catch {
      setAggregateStats(null)
    }
  }, [])

  useEffect(() => {
    loadSessions()
    loadPrompts()
    loadAggregateStats()
    api.gkGroups().then(setGroups).catch(() => {})
    api.gkImagePromptTesterSupportedModels()
      .then(data => {
        setSupportedModels(data.models || [])
        setDefaultModelName(data.default_model || null)
      })
      .catch(() => {})
  }, [loadSessions, loadPrompts, loadAggregateStats])

  const modelOptions = useMemo(() => {
    const currentModel = promptForm.model_name.trim()
    if (!currentModel || supportedModels.includes(currentModel)) {
      return supportedModels
    }
    return [...supportedModels, currentModel]
  }, [supportedModels, promptForm.model_name])

  useEffect(() => {
    const hasGenerating = sessions.some(s => s.status === 'generating')
    if (!hasGenerating) {
      return
    }

    const timer = window.setInterval(() => {
      loadSessions().catch(() => {})
    }, 2500)

    return () => window.clearInterval(timer)
  }, [sessions, loadSessions])

  useEffect(() => {
    if (!showSessionForm) {
      setSessionEstimate(null)
      setEstimateLoading(false)
      return
    }

    const imageCount = Number(sessionForm.image_count) || 0
    if (sessionForm.prompt_ids.length < 2 || imageCount < 2 || imageCount > 1000) {
      setSessionEstimate(null)
      setEstimateLoading(false)
      return
    }

    let cancelled = false
    setEstimateLoading(true)

    const timer = window.setTimeout(() => {
      api.gkEstimateImageSession({
        prompt_ids: sessionForm.prompt_ids,
        image_count: imageCount,
        source_group_id: sessionForm.source_group_id ? Number(sessionForm.source_group_id) : undefined,
        source_date_from: sessionForm.source_date_from || undefined,
        source_date_to: sessionForm.source_date_to || undefined,
      })
        .then((estimate) => {
          if (!cancelled) {
            setSessionEstimate(estimate)
          }
        })
        .catch(() => {
          if (!cancelled) {
            setSessionEstimate(null)
          }
        })
        .finally(() => {
          if (!cancelled) {
            setEstimateLoading(false)
          }
        })
    }, 250)

    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [showSessionForm, sessionForm.prompt_ids, sessionForm.image_count, sessionForm.source_group_id, sessionForm.source_date_from, sessionForm.source_date_to])

  const handlePromptSubmit = async () => {
    setError('')
    try {
      const data = {
        label: promptForm.label,
        prompt_text: promptForm.prompt_text,
        model_name: promptForm.model_name || undefined,
        temperature: parseFloat(promptForm.temperature) || 0.3,
      }
      if (editPrompt) {
        await api.gkUpdateImagePrompt(editPrompt.id, data)
      } else {
        await api.gkCreateImagePrompt(data)
      }
      setShowPromptForm(false)
      setEditPrompt(null)
      setPromptForm({ label: '', prompt_text: '', model_name: '', temperature: '0.3' })
      loadPrompts()
      loadAggregateStats()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка')
    }
  }

  const startEditPrompt = (p: GKImagePrompt) => {
    setEditPrompt(p)
    setPromptForm({
      label: p.label,
      prompt_text: p.prompt_text,
      model_name: p.model_name || '',
      temperature: String(p.temperature),
    })
    setShowPromptForm(true)
  }

  const handleCreateSession = async () => {
    setError('')
    if (sessionForm.prompt_ids.length < 2) {
      setError('Выберите минимум 2 промпта')
      return
    }
    try {
      await api.gkCreateImageSession({
        name: sessionForm.name,
        prompt_ids: sessionForm.prompt_ids,
        image_count: Number(sessionForm.image_count) || 20,
        source_group_id: sessionForm.source_group_id ? Number(sessionForm.source_group_id) : undefined,
        source_date_from: sessionForm.source_date_from || undefined,
        source_date_to: sessionForm.source_date_to || undefined,
      })
      setShowSessionForm(false)
      setSessionForm({ name: '', prompt_ids: [], image_count: '20', source_group_id: '', source_date_from: '', source_date_to: '' })
      setSessionEstimate(null)
      loadSessions()
      loadAggregateStats()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка создания сессии')
    }
  }

  const startComparing = async (sessionId: number) => {
    setActiveSessionId(sessionId)
    setSubView('compare')
    setVotedCount(0)
    await loadNextComparison(sessionId)
  }

  const loadNextComparison = async (sessionId: number) => {
    setCompareLoading(true)
    try {
      const comp = await api.gkGetNextImageComparison(sessionId)
      setComparison(comp)
      if (typeof comp.progress_voted === 'number') {
        setVotedCount(comp.progress_voted)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка')
    } finally {
      setCompareLoading(false)
    }
  }

  const vote = async (winner: string) => {
    if (!comparison?.comparison_id || !activeSessionId) return
    setVoteLoading(true)
    try {
      await api.gkImageVote(activeSessionId, { comparison_id: comparison.comparison_id, winner })
      setVotedCount(c => c + 1)
      await loadNextComparison(activeSessionId)
      loadAggregateStats()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка голосования')
    } finally {
      setVoteLoading(false)
    }
  }

  const showResults = async (sessionId: number) => {
    setActiveSessionId(sessionId)
    setSubView('results')
    try {
      const res = await api.gkImageSessionResults(sessionId)
      setResults(res)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка')
    }
  }

  const abandonSession = async (sessionId: number) => {
    try {
      await api.gkAbandonImageSession(sessionId)
      loadSessions()
      loadAggregateStats()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка')
    }
  }

  const renderSubNav = () => (
    <div className="pt-sub-nav" style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
      <button className={`btn btn-sm ${subView === 'sessions' ? 'btn-primary' : ''}`} onClick={() => setSubView('sessions')}>Сессии</button>
      <button className={`btn btn-sm ${subView === 'prompts' ? 'btn-primary' : ''}`} onClick={() => setSubView('prompts')}>Промпты</button>
      <button className={`btn btn-sm ${subView === 'stats' ? 'btn-primary' : ''}`} onClick={() => setSubView('stats')}>Статистика</button>
    </div>
  )

  if (subView === 'stats') {
    const summary = aggregateStats?.summary
    const promptsStats = aggregateStats?.prompts || []

    return (
      <div className="gk-prompt-tester-tab">
        {renderSubNav()}
        {error && <div className="alert alert-danger">{error}</div>}

        {summary && (
          <div className="stats-bar" style={{ marginBottom: 12 }}>
            <div className="stat"><span className="stat-value">{summary.sessions_total}</span><span className="stat-label">Сессии</span></div>
            <div className="stat stat-success"><span className="stat-value">{summary.sessions_completed}</span><span className="stat-label">Завершены</span></div>
            <div className="stat stat-accent"><span className="stat-value">{summary.voted_matches}</span><span className="stat-label">Голоса</span></div>
            <div className="stat stat-danger"><span className="stat-value">{summary.skipped_matches}</span><span className="stat-label">Skip</span></div>
          </div>
        )}

        {promptsStats.length === 0 ? (
          <div className="card empty-state"><p>Пока нет данных для рейтинга</p></div>
        ) : (
          <div className="results-table">
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr>
                  <th style={thStyle}>#</th>
                  <th style={thStyle}>Промпт</th>
                  <th style={thStyle}>Elo</th>
                  <th style={thStyle}>ΔElo</th>
                  <th style={thStyle}>Win Rate</th>
                  <th style={thStyle}>Матчи</th>
                  <th style={thStyle}>W/L/T</th>
                  <th style={thStyle}>Сессии</th>
                </tr>
              </thead>
              <tbody>
                {promptsStats.map((p, index) => (
                  <tr key={p.prompt_id} style={{ background: index === 0 ? 'var(--success-dim)' : 'transparent' }}>
                    <td style={tdStyle}>{index + 1}</td>
                    <td style={tdStyle}><strong>{p.label}</strong>{!p.is_active && <span className="badge badge-dim" style={{ marginLeft: 8 }}>неактивен</span>}</td>
                    <td style={tdStyle}>{p.elo.toFixed(1)}</td>
                    <td style={{ ...tdStyle, color: p.elo_delta >= 0 ? 'var(--success)' : 'var(--danger)' }}>{p.elo_delta >= 0 ? '+' : ''}{p.elo_delta.toFixed(1)}</td>
                    <td style={tdStyle}>{(p.win_rate * 100).toFixed(1)}%</td>
                    <td style={tdStyle}>{p.matches}</td>
                    <td style={tdStyle}>{p.wins}/{p.losses}/{p.ties}</td>
                    <td style={tdStyle}>{p.sessions_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    )
  }

  if (subView === 'prompts') {
    return (
      <div className="gk-prompt-tester-tab">
        {renderSubNav()}
        {error && <div className="alert alert-danger">{error}</div>}

        {canEdit && (
          <button className="btn btn-primary" style={{ marginBottom: 12 }} onClick={() => { setEditPrompt(null); setPromptForm({ label: '', prompt_text: '', model_name: '', temperature: '0.3' }); setShowPromptForm(true) }}>
            + Новый промпт
          </button>
        )}

        {showPromptForm && (
          <div className="card" style={{ marginBottom: 16, padding: 16 }}>
            <h3 style={{ marginBottom: 12 }}>{editPrompt ? 'Редактирование промпта' : 'Новый промпт'}</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <input className="input" placeholder="Название" value={promptForm.label} onChange={e => setPromptForm({ ...promptForm, label: e.target.value })} />
              <textarea className="input" placeholder="Промпт для описания изображения" rows={6} value={promptForm.prompt_text} onChange={e => setPromptForm({ ...promptForm, prompt_text: e.target.value })} style={{ resize: 'vertical', fontFamily: 'var(--font-mono)', fontSize: 13 }} />
              <div style={{ display: 'flex', gap: 8 }}>
                <select className="input input-sm" value={promptForm.model_name} onChange={e => setPromptForm({ ...promptForm, model_name: e.target.value })}>
                  <option value="">{defaultModelName ? `По умолчанию (${defaultModelName})` : 'По умолчанию'}</option>
                  {modelOptions.map(modelName => (<option key={modelName} value={modelName}>{modelName}</option>))}
                </select>
                <input className="input input-sm" type="number" step="0.1" min="0" max="2" placeholder="Температура" value={promptForm.temperature} onChange={e => setPromptForm({ ...promptForm, temperature: e.target.value })} style={{ width: 120 }} />
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <button className="btn btn-primary" onClick={handlePromptSubmit}>Сохранить</button>
                <button className="btn" onClick={() => { setShowPromptForm(false); setEditPrompt(null) }}>Отмена</button>
              </div>
            </div>
          </div>
        )}

        {promptsLoading ? (
          <div className="loading-text">Загрузка...</div>
        ) : prompts.length === 0 ? (
          <div className="card empty-state"><p>Нет промптов</p></div>
        ) : (
          <div className="prompts-list">
            {prompts.map(p => (
              <div key={p.id} className={`card ${!p.is_active ? 'card-inactive' : ''}`} style={{ marginBottom: 8, padding: 12 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <strong>{p.label}</strong>
                    <span className={`badge ${p.is_active ? 'badge-success' : 'badge-dim'}`} style={{ marginLeft: 8 }}>{p.is_active ? 'активен' : 'неактивен'}</span>
                    {p.model_name && <span className="text-dim" style={{ marginLeft: 8 }}>{p.model_name}</span>}
                    <span className="text-dim" style={{ marginLeft: 8 }}>t={p.temperature}</span>
                  </div>
                  {canEdit && (
                    <div style={{ display: 'flex', gap: 4 }}>
                      <button className="btn btn-sm" onClick={() => startEditPrompt(p)}>✏️</button>
                      {p.is_active && <button className="btn btn-sm" onClick={() => { api.gkDeleteImagePrompt(p.id).then(loadPrompts) }}>🗑</button>}
                    </div>
                  )}
                </div>
                <div className="text-dim" style={{ marginTop: 6, fontSize: 12, whiteSpace: 'pre-wrap', maxHeight: 100, overflow: 'hidden' }}>
                  {p.prompt_text.slice(0, 350)}{p.prompt_text.length > 350 ? '...' : ''}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    )
  }

  if (subView === 'compare' && activeSessionId) {
    return (
      <div className="gk-prompt-tester-tab">
        <button className="btn btn-sm" onClick={() => setSubView('sessions')} style={{ marginBottom: 12 }}>← К сессиям</button>
        {error && <div className="alert alert-danger">{error}</div>}

        <div className="text-dim" style={{ marginBottom: 8 }}>
          Голосов отдано: {votedCount}{typeof comparison?.progress_total === 'number' ? ` / ${comparison.progress_total}` : ''}
        </div>

        {compareLoading ? (
          <div className="loading-text">Загрузка сравнения...</div>
        ) : !comparison?.has_more ? (
          <div className="card" style={{ padding: 16 }}>
            <p style={{ marginBottom: 10 }}>Сравнения завершены.</p>
            <button className="btn btn-primary" onClick={() => showResults(activeSessionId)}>Показать результаты</button>
          </div>
        ) : (
          <>
            {comparison.image_preview_url && (
              <div className="card" style={{ marginBottom: 12, padding: 12 }}>
                <img
                  src={comparison.image_preview_url}
                  alt={`cmp-${comparison.image_queue_id || ''}`}
                  style={{ maxWidth: '100%', maxHeight: 240, borderRadius: 6, border: '1px solid var(--border)' }}
                />
              </div>
            )}
            <div className="compare-grid">
              <div className="card compare-option" style={{ padding: 12 }}>
                <h4 style={{ marginBottom: 6 }}>Вариант A</h4>
                <div style={{ whiteSpace: 'pre-wrap' }}>{comparison.generation_a_text}</div>
              </div>
              <div className="card compare-option" style={{ padding: 12 }}>
                <h4 style={{ marginBottom: 6 }}>Вариант B</h4>
                <div style={{ whiteSpace: 'pre-wrap' }}>{comparison.generation_b_text}</div>
              </div>
            </div>
            <div className="compare-buttons" style={{ display: 'flex', gap: 8, marginTop: 10 }}>
              <button className="btn btn-primary" disabled={voteLoading} onClick={() => vote('a')}>A лучше</button>
              <button className="btn" disabled={voteLoading} onClick={() => vote('tie')}>Равны</button>
              <button className="btn btn-primary" disabled={voteLoading} onClick={() => vote('b')}>B лучше</button>
              <button className="btn btn-sm" disabled={voteLoading} onClick={() => vote('skip')}>Пропустить</button>
            </div>
          </>
        )}
      </div>
    )
  }

  if (subView === 'results' && results) {
    return (
      <div className="gk-prompt-tester-tab">
        <button className="btn btn-sm" onClick={() => setSubView('sessions')} style={{ marginBottom: 12 }}>← К сессиям</button>
        {error && <div className="alert alert-danger">{error}</div>}

        <div className="stats-bar" style={{ marginBottom: 12 }}>
          <div className="stat"><span className="stat-value">{results.total_comparisons}</span><span className="stat-label">Сравнений</span></div>
          <div className="stat stat-accent"><span className="stat-value">{results.voted_comparisons}</span><span className="stat-label">С голосом</span></div>
          <div className="stat stat-success"><span className="stat-value">{Math.round((results.voted_comparisons / Math.max(results.total_comparisons, 1)) * 100)}%</span><span className="stat-label">Прогресс</span></div>
        </div>

        <div className="results-table">
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                <th style={thStyle}>#</th>
                <th style={thStyle}>Промпт</th>
                <th style={thStyle}>Elo</th>
                <th style={thStyle}>ΔElo</th>
                <th style={thStyle}>Win Rate</th>
                <th style={thStyle}>Матчи</th>
                <th style={thStyle}>W/L/T</th>
              </tr>
            </thead>
            <tbody>
              {results.prompts.map((p, idx) => (
                <tr key={p.prompt_id} style={{ background: idx === 0 ? 'var(--success-dim)' : 'transparent' }}>
                  <td style={tdStyle}>{idx + 1}</td>
                  <td style={tdStyle}><strong>{p.label}</strong></td>
                  <td style={tdStyle}>{p.elo.toFixed(1)}</td>
                  <td style={{ ...tdStyle, color: (p.elo_delta || 0) >= 0 ? 'var(--success)' : 'var(--danger)' }}>
                    {(p.elo_delta || 0) >= 0 ? '+' : ''}{(p.elo_delta || 0).toFixed(1)}
                  </td>
                  <td style={tdStyle}>{(p.win_rate * 100).toFixed(1)}%</td>
                  <td style={tdStyle}>{p.matches || 0}</td>
                  <td style={tdStyle}>{p.wins}/{p.losses}/{p.ties}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    )
  }

  return (
    <div className="gk-prompt-tester-tab">
      {renderSubNav()}
      {error && <div className="alert alert-danger">{error}</div>}

      {canEdit && (
        <button className="btn btn-primary" style={{ marginBottom: 12 }} onClick={() => setShowSessionForm(v => !v)}>
          {showSessionForm ? 'Скрыть форму' : '+ Новая сессия'}
        </button>
      )}

      {showSessionForm && (
        <div className="card" style={{ marginBottom: 16, padding: 16 }}>
          <h3 style={{ marginBottom: 12 }}>Новая image-сессия</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <input className="input" placeholder="Название сессии" value={sessionForm.name} onChange={e => setSessionForm({ ...sessionForm, name: e.target.value })} />
            <div className="text-dim" style={{ fontSize: 12 }}>Выберите минимум 2 промпта</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {prompts.filter(p => p.is_active).map(p => {
                const checked = sessionForm.prompt_ids.includes(p.id)
                return (
                  <label key={p.id} className="badge badge-dim" style={{ cursor: 'pointer', userSelect: 'none' }}>
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={(event) => {
                        const isChecked = event.target.checked
                        setSessionForm(prev => ({
                          ...prev,
                          prompt_ids: isChecked ? [...prev.prompt_ids, p.id] : prev.prompt_ids.filter(id => id !== p.id),
                        }))
                      }}
                      style={{ marginRight: 6 }}
                    />
                    {p.label}
                  </label>
                )
              })}
            </div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <input className="input input-sm" type="number" min="2" max="1000" value={sessionForm.image_count} onChange={e => setSessionForm({ ...sessionForm, image_count: e.target.value })} placeholder="Изображений" style={{ width: 160 }} />
              <select className="input input-sm" value={sessionForm.source_group_id} onChange={e => setSessionForm({ ...sessionForm, source_group_id: e.target.value })} style={{ minWidth: 220 }}>
                <option value="">Все группы</option>
                {groups.map(group => (
                  <option key={group.group_id} value={String(group.group_id)}>
                    {group.group_title || `Группа ${group.group_id}`}
                  </option>
                ))}
              </select>
              <input className="input input-sm" type="date" value={sessionForm.source_date_from} onChange={e => setSessionForm({ ...sessionForm, source_date_from: e.target.value })} />
              <input className="input input-sm" type="date" value={sessionForm.source_date_to} onChange={e => setSessionForm({ ...sessionForm, source_date_to: e.target.value })} />
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="btn btn-primary" onClick={handleCreateSession}>Создать сессию</button>
              <button className="btn" onClick={() => setShowSessionForm(false)}>Отмена</button>
            </div>

            {(estimateLoading || sessionEstimate) && (
              <div className="text-dim" style={{ fontSize: 12 }}>
                {estimateLoading ? (
                  'Расчёт ожидаемого числа сравнений...'
                ) : sessionEstimate ? (
                  `Ожидается ${sessionEstimate.expected_comparisons} сравнений (${sessionEstimate.prompt_count} промптов × ${sessionEstimate.effective_image_count} изображений).`
                ) : null}
              </div>
            )}
          </div>
        </div>
      )}

      {sessionsLoading ? (
        <div className="loading-text">Загрузка...</div>
      ) : sessions.length === 0 ? (
        <div className="card empty-state"><p>Нет сессий</p></div>
      ) : (
        <div className="prompts-list">
          {sessions.map(session => (
            <div key={session.id} className="card" style={{ marginBottom: 8, padding: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                <div>
                  <strong>{session.name || `Session #${session.id}`}</strong>
                  <span className={`badge ${session.status === 'completed' ? 'badge-success' : session.status === 'abandoned' ? 'badge-danger' : 'badge-dim'}`} style={{ marginLeft: 8 }}>
                    {session.status}
                  </span>
                  <span className="text-dim" style={{ marginLeft: 8 }}>
                    prompts: {session.prompt_count || session.prompt_ids?.length || 0} · images: {session.image_count || 0}
                  </span>
                </div>
                <div style={{ display: 'flex', gap: 6 }}>
                  <button className="btn btn-sm" onClick={() => startComparing(session.id)}>Сравнивать</button>
                  <button className="btn btn-sm" onClick={() => showResults(session.id)}>Результаты</button>
                  {canEdit && session.status !== 'abandoned' && session.status !== 'completed' && (
                    <button className="btn btn-sm" onClick={() => abandonSession(session.id)}>Отменить</button>
                  )}
                </div>
              </div>
              <div className="text-dim" style={{ marginTop: 6, fontSize: 12 }}>
                Генерации: {session.generation_count || 0} / {session.expected_generations || 0} ({session.generation_progress_pct || 0}%) ·
                Сравнения: {session.voted_count || 0} / {session.total_comparisons || 0}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
