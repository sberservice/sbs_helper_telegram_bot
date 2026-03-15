import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  api,
  type GKGroup,
  type GKMessageChainItem,
  type GKMessageBrowserItem,
  type GKMessageBrowserSender,
} from '../../api'

const PAGE_SIZE_STORAGE_KEY = 'gk_message_browser_page_size'

const formatDateTime = (unixTs?: number | null): string => {
  if (!unixTs) return '—'
  const date = new Date(unixTs * 1000)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleString('ru-RU')
}

const trimText = (value: string | null | undefined, maxLen: number = 220): string => {
  const text = String(value || '').trim()
  if (!text) return '—'
  if (text.length <= maxLen) return text
  return `${text.slice(0, maxLen)}…`
}

const formatResponderState = (item: GKMessageBrowserItem): string => {
  if (!item.responder_mode) return '—'
  const modeLabel = item.responder_mode === 'live' ? 'LIVE' : 'DRY'
  const confidencePart = item.responder_confidence == null
    ? ''
    : ` · ${Math.round(item.responder_confidence * 100)}%`
  return `${modeLabel}${confidencePart}`
}

export default function MessageBrowserTab() {
  const [items, setItems] = useState<GKMessageBrowserItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState<number>(() => {
    try {
      const raw = window.localStorage.getItem(PAGE_SIZE_STORAGE_KEY)
      const parsed = Number(raw)
      if ([20, 50, 100, 200].includes(parsed)) {
        return parsed
      }
    } catch {}
    return 50
  })

  const [groups, setGroups] = useState<GKGroup[]>([])
  const [senders, setSenders] = useState<GKMessageBrowserSender[]>([])

  const [groupId, setGroupId] = useState<number | ''>('')
  const [senderId, setSenderId] = useState<number | ''>('')
  const [processed, setProcessed] = useState<'all' | 'yes' | 'no'>('all')
  const [isQuestion, setIsQuestion] = useState<'all' | 'yes' | 'no'>('all')
  const [analyzed, setAnalyzed] = useState<'all' | 'yes' | 'no'>('all')
  const [inChain, setInChain] = useState<'all' | 'yes' | 'no'>('all')
  const [search, setSearch] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [chainLoading, setChainLoading] = useState(false)
  const [chainItems, setChainItems] = useState<GKMessageChainItem[]>([])
  const [chainTitle, setChainTitle] = useState('')

  useEffect(() => {
    try {
      window.localStorage.setItem(PAGE_SIZE_STORAGE_KEY, String(pageSize))
    } catch {}
  }, [pageSize])

  useEffect(() => {
    api.gkGroups().then(setGroups).catch(() => {})
  }, [])

  const loadSenders = useCallback(async () => {
    try {
      const data = await api.gkMessageSenders({
        group_id: groupId === '' ? null : Number(groupId),
        limit: 300,
      })
      setSenders(data)
    } catch {
      setSenders([])
    }
  }, [groupId])

  useEffect(() => {
    loadSenders().catch(() => {})
  }, [loadSenders])

  const loadMessages = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const response = await api.gkMessagesBrowser({
        page,
        page_size: pageSize,
        group_id: groupId === '' ? null : Number(groupId),
        sender_id: senderId === '' ? null : Number(senderId),
        processed: processed === 'all' ? null : processed === 'yes',
        is_question: isQuestion === 'all' ? null : isQuestion === 'yes',
        analyzed: analyzed === 'all' ? null : analyzed === 'yes',
        in_chain: inChain === 'all' ? null : inChain === 'yes',
        search: search.trim() || null,
        date_from: dateFrom || null,
        date_to: dateTo || null,
      })
      setItems(response.items || [])
      setTotal(response.total || 0)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка загрузки сообщений')
      setItems([])
      setTotal(0)
    } finally {
      setLoading(false)
    }
  }, [page, pageSize, groupId, senderId, processed, isQuestion, analyzed, inChain, search, dateFrom, dateTo])

  useEffect(() => {
    loadMessages().catch(() => {})
  }, [loadMessages])

  const totalPages = useMemo(() => Math.max(1, Math.ceil(total / pageSize)), [total, pageSize])

  const resetPageAnd = (fn: () => void) => {
    setPage(1)
    fn()
  }

  const showChainPanel = chainLoading || chainItems.length > 0

  const openChain = async (item: GKMessageBrowserItem) => {
    setChainLoading(true)
    setError('')
    try {
      const response = await api.gkMessageChain({
        group_id: item.group_id,
        telegram_message_id: item.telegram_message_id,
      })
      setChainItems(response.items || [])
      setChainTitle(`${item.group_title || item.group_id} · msg ${item.telegram_message_id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка загрузки цепочки')
      setChainItems([])
      setChainTitle('')
    } finally {
      setChainLoading(false)
    }
  }

  const closeChain = () => {
    setChainItems([])
    setChainTitle('')
    setChainLoading(false)
  }

  return (
    <div className="gk-message-browser-tab">
      <div className="card" style={{ marginBottom: 12, padding: 12 }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 8 }}>
          <select className="input input-sm" value={groupId} onChange={e => resetPageAnd(() => setGroupId(e.target.value ? Number(e.target.value) : ''))}>
            <option value="">Все группы</option>
            {groups.map(g => (
              <option key={g.group_id} value={g.group_id}>{g.group_title || `Группа ${g.group_id}`}</option>
            ))}
          </select>

          <select className="input input-sm" value={senderId} onChange={e => resetPageAnd(() => setSenderId(e.target.value ? Number(e.target.value) : ''))}>
            <option value="">Все пользователи</option>
            {senders.map(s => (
              <option key={s.sender_id} value={s.sender_id}>{s.sender_name || s.sender_id} ({s.message_count})</option>
            ))}
          </select>

          <select className="input input-sm" value={processed} onChange={e => resetPageAnd(() => setProcessed(e.target.value as 'all' | 'yes' | 'no'))}>
            <option value="all">Processed: все</option>
            <option value="yes">Processed: да</option>
            <option value="no">Processed: нет</option>
          </select>

          <select className="input input-sm" value={isQuestion} onChange={e => resetPageAnd(() => setIsQuestion(e.target.value as 'all' | 'yes' | 'no'))}>
            <option value="all">Question: все</option>
            <option value="yes">Question: да</option>
            <option value="no">Question: нет</option>
          </select>

          <select className="input input-sm" value={analyzed} onChange={e => resetPageAnd(() => setAnalyzed(e.target.value as 'all' | 'yes' | 'no'))}>
            <option value="all">Analyzer: все</option>
            <option value="yes">Analyzer: да</option>
            <option value="no">Analyzer: нет</option>
          </select>

          <select className="input input-sm" value={inChain} onChange={e => resetPageAnd(() => setInChain(e.target.value as 'all' | 'yes' | 'no'))}>
            <option value="all">Chain: все</option>
            <option value="yes">Chain: в цепочке</option>
            <option value="no">Chain: вне цепочки</option>
          </select>

          <input className="input input-sm" type="date" value={dateFrom} onChange={e => resetPageAnd(() => setDateFrom(e.target.value))} />
          <input className="input input-sm" type="date" value={dateTo} onChange={e => resetPageAnd(() => setDateTo(e.target.value))} />
          <input className="input input-sm" placeholder="Поиск по тексту/подписи/имени" value={search} onChange={e => resetPageAnd(() => setSearch(e.target.value))} />

          <select className="input input-sm" value={String(pageSize)} onChange={e => resetPageAnd(() => setPageSize(Number(e.target.value)))}>
            <option value="20">20 / page</option>
            <option value="50">50 / page</option>
            <option value="100">100 / page</option>
            <option value="200">200 / page</option>
          </select>
        </div>
      </div>

      {error && <div className="alert alert-danger">{error}</div>}

      <div style={{ display: 'grid', gridTemplateColumns: showChainPanel ? 'minmax(0, 2fr) minmax(340px, 1fr)' : '1fr', gap: 12, alignItems: 'start' }}>
        <div>
          {loading ? (
            <div className="loading-text">Загрузка...</div>
          ) : items.length === 0 ? (
            <div className="card empty-state"><p>Сообщения не найдены</p></div>
          ) : (
            <div className="results-table">
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr>
                    <th style={thStyle}>Дата</th>
                    <th style={thStyle}>Группа</th>
                    <th style={thStyle}>Пользователь</th>
                    <th style={thStyle}>Текст</th>
                    <th style={thStyle}>Chain</th>
                    <th style={thStyle}>Responder</th>
                    <th style={thStyle}>Analyzer</th>
                    <th style={thStyle}>Question</th>
                    <th style={thStyle}>Processed</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((item) => (
                    <tr key={item.id}>
                      <td style={tdStyle}>{formatDateTime(item.message_date)}</td>
                      <td style={tdStyle}>{item.group_title || item.group_id}</td>
                      <td style={tdStyle}>{item.sender_name || item.sender_id}</td>
                      <td style={tdStyle} title={item.message_text || item.caption || ''}>
                        {trimText(item.message_text || item.caption)}
                      </td>
                      <td style={tdStyle}>
                        {item.is_in_chain ? (
                          <button className="btn btn-sm" onClick={() => openChain(item)} title="Показать цепочку">✅</button>
                        ) : '—'}
                      </td>
                      <td style={tdStyle} title={item.responder_responded_at ? `Отработал: ${formatDateTime(item.responder_responded_at)}` : ''}>
                        {formatResponderState(item)}
                      </td>
                      <td style={tdStyle}>{item.is_analyzed ? '✅' : '—'}</td>
                      <td style={tdStyle}>{item.is_question === null ? '—' : (item.is_question ? '✅' : '❌')}</td>
                      <td style={tdStyle}>{item.processed ? '✅' : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 12 }}>
            <div className="text-dim">Всего: {total}</div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <button className="btn btn-sm" disabled={page <= 1} onClick={() => setPage(p => Math.max(1, p - 1))}>← Назад</button>
              <span className="text-dim">Стр. {page} / {totalPages}</span>
              <button className="btn btn-sm" disabled={page >= totalPages} onClick={() => setPage(p => Math.min(totalPages, p + 1))}>Вперёд →</button>
            </div>
          </div>
        </div>

        {showChainPanel && (
          <div className="card" style={{ padding: 12, position: 'sticky', top: 12, maxHeight: '78vh', overflow: 'auto' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
              <strong>Цепочка сообщений {chainTitle ? `· ${chainTitle}` : ''}</strong>
              <button className="btn btn-sm" onClick={closeChain}>✕</button>
            </div>
            {chainLoading ? (
              <div className="loading-text">Загрузка цепочки...</div>
            ) : chainItems.length === 0 ? (
              <div className="text-dim">Цепочка не найдена</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {chainItems.map((msg) => (
                  <div key={msg.telegram_message_id} className="card" style={{ padding: 8 }}>
                    <div className="text-dim" style={{ fontSize: 12, marginBottom: 4 }}>
                      {formatDateTime(msg.message_date)} · {msg.sender_name || msg.sender_id}
                      {msg.reply_to_message_id ? ` · ↩ ${msg.reply_to_message_id}` : ''}
                      {msg.is_question === null ? '' : (msg.is_question ? ' · question✅' : ' · question❌')}
                    </div>
                    <div style={{ whiteSpace: 'pre-wrap' }}>{trimText(msg.message_text || msg.caption, 1200)}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

const thStyle: React.CSSProperties = {
  textAlign: 'left',
  padding: '8px 12px',
  borderBottom: '1px solid var(--border)',
  color: 'var(--text-dim)',
  fontSize: 12,
  fontWeight: 600,
}

const tdStyle: React.CSSProperties = {
  padding: '8px 12px',
  borderBottom: '1px solid var(--border)',
  verticalAlign: 'top',
}
