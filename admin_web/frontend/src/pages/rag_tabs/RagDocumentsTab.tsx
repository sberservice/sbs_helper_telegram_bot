import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, type RAGDocumentsResponse } from '../../api'

function formatDate(value: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('ru-RU')
}

function truncateMiddle(value: string, maxLen: number = 64): string {
  if (value.length <= maxLen) return value
  const keep = Math.max(8, Math.floor((maxLen - 1) / 2))
  return `${value.slice(0, keep)}…${value.slice(value.length - keep)}`
}

function formatEmbeddingState(ready: number, failed: number, stale: number): string {
  if (ready === 0 && failed === 0 && stale === 0) return 'нет данных'
  return `${ready}/${failed}/${stale}`
}

const PAGE_SIZE_OPTIONS = [10, 20, 50, 100]

export default function RagDocumentsTab() {
  const [data, setData] = useState<RAGDocumentsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [searchInput, setSearchInput] = useState('')
  const [searchText, setSearchText] = useState<string | null>(null)
  const [status, setStatus] = useState<'active' | 'archived' | 'deleted' | null>(null)
  const [sourceType, setSourceType] = useState<string | null>(null)
  const [hasSummary, setHasSummary] = useState<boolean | null>(null)
  const [sortBy, setSortBy] = useState<'updated_at' | 'created_at' | 'filename' | 'status' | 'source_type' | 'chunks' | 'chunk_embeddings_ready' | 'summary_embeddings_ready'>('updated_at')
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc')

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const value = searchInput.trim()
      setSearchText(value || null)
      setPage(1)
    }, 350)
    return () => window.clearTimeout(timer)
  }, [searchInput])

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const response = await api.gkRAGDocuments({
        page,
        page_size: pageSize,
        q: searchText,
        status,
        source_type: sourceType,
        has_summary: hasSummary,
        sort_by: sortBy,
        sort_order: sortOrder,
      })
      setData(response)
    } catch (e: any) {
      setError(e?.message || 'Не удалось загрузить список RAG-документов')
    } finally {
      setLoading(false)
    }
  }, [page, pageSize, searchText, status, sourceType, hasSummary, sortBy, sortOrder])

  useEffect(() => {
    load()
  }, [load])

  const totalPages = useMemo(() => {
    if (!data) return 1
    return Math.max(1, Math.ceil(data.total / data.page_size))
  }, [data])

  const sourceTypeOptions = useMemo(() => {
    if (!data) return []
    return Object.keys(data.stats.source_type_counts)
  }, [data])

  return (
    <div style={{ display: 'grid', gap: 12 }}>
      {error && <div className="alert alert-danger">{error}</div>}

      <div className="card">
        <h3 style={{ marginTop: 0 }}>📚 Документы RAG</h3>
        <div className="filters-bar" style={{ marginBottom: 10 }}>
          <input
            type="text"
            className="input input-sm"
            placeholder="Поиск: filename / source_url / summary"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            maxLength={500}
            style={{ minWidth: 280 }}
          />

          <select
            className="input input-sm"
            value={status ?? ''}
            onChange={(e) => {
              setStatus((e.target.value || null) as 'active' | 'archived' | 'deleted' | null)
              setPage(1)
            }}
          >
            <option value="">Все статусы</option>
            <option value="active">active</option>
            <option value="archived">archived</option>
            <option value="deleted">deleted</option>
          </select>

          <select
            className="input input-sm"
            value={sourceType ?? ''}
            onChange={(e) => {
              setSourceType(e.target.value || null)
              setPage(1)
            }}
          >
            <option value="">Все источники</option>
            {sourceTypeOptions.map((source) => (
              <option key={source} value={source}>{source}</option>
            ))}
          </select>

          <select
            className="input input-sm"
            value={hasSummary === null ? '' : hasSummary ? 'yes' : 'no'}
            onChange={(e) => {
              const value = e.target.value
              if (!value) setHasSummary(null)
              else setHasSummary(value === 'yes')
              setPage(1)
            }}
          >
            <option value="">Summary: любые</option>
            <option value="yes">Summary: есть</option>
            <option value="no">Summary: нет</option>
          </select>

          <select
            className="input input-sm"
            value={`${sortBy}-${sortOrder}`}
            onChange={(e) => {
              const [newSortBy, newSortOrder] = e.target.value.split('-')
              setSortBy(newSortBy as typeof sortBy)
              setSortOrder(newSortOrder as 'asc' | 'desc')
              setPage(1)
            }}
          >
            <option value="updated_at-desc">Сначала обновлённые</option>
            <option value="updated_at-asc">Сначала давно обновлённые</option>
            <option value="created_at-desc">Сначала новые</option>
            <option value="created_at-asc">Сначала старые</option>
            <option value="filename-asc">Filename A→Z</option>
            <option value="filename-desc">Filename Z→A</option>
            <option value="chunks-desc">Больше чанков</option>
            <option value="chunks-asc">Меньше чанков</option>
            <option value="chunk_embeddings_ready-desc">Больше chunk embeddings</option>
            <option value="summary_embeddings_ready-desc">Больше summary embeddings</option>
          </select>

          <select
            className="input input-sm"
            value={String(pageSize)}
            onChange={(e) => {
              setPageSize(Number(e.target.value))
              setPage(1)
            }}
          >
            {PAGE_SIZE_OPTIONS.map((size) => (
              <option key={size} value={size}>{size} / стр</option>
            ))}
          </select>

          <button className="btn btn-sm" onClick={load}>🔄</button>
        </div>

        {loading ? (
          <div className="loading-text">Загрузка документов...</div>
        ) : !data ? (
          <div className="text-dim">Нет данных</div>
        ) : (
          <>
            <div style={{ display: 'grid', gap: 8, marginBottom: 10 }}>
              <div className="text-dim">
                Документов: <strong>{data.stats.documents_total}</strong> · Active: {data.stats.status_counts.active} · Archived: {data.stats.status_counts.archived} · Deleted: {data.stats.status_counts.deleted}
              </div>
              <div className="text-dim">
                Чанков: <strong>{data.stats.total_chunks}</strong> · Среднее чанков/док: {data.stats.avg_chunks_per_document} · Документов с summary: {data.stats.documents_with_summary}
              </div>
              <div className="text-dim">
                Chunk embeddings: ready {data.stats.chunk_embeddings.ready}, failed {data.stats.chunk_embeddings.failed}, stale {data.stats.chunk_embeddings.stale}
              </div>
              <div className="text-dim">
                Summary embeddings: ready {data.stats.summary_embeddings.ready}, failed {data.stats.summary_embeddings.failed}, stale {data.stats.summary_embeddings.stale}
              </div>
              <div className="text-dim">
                Последнее обновление документа: {formatDate(data.stats.last_document_updated_at)}
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {Object.entries(data.stats.source_type_counts).map(([source, count]) => (
                  <span key={source} className="badge badge-dim">{source}: {count}</span>
                ))}
              </div>
            </div>

            <table className="pm-table" style={{ marginBottom: 10 }}>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Filename</th>
                  <th>Источник</th>
                  <th>Статус</th>
                  <th>Чанки</th>
                  <th>Summary</th>
                  <th>Chunk Emb</th>
                  <th>Summary Emb</th>
                  <th>Обновлён</th>
                </tr>
              </thead>
              <tbody>
                {data.items.length === 0 ? (
                  <tr>
                    <td colSpan={9} className="text-dim" style={{ textAlign: 'center', padding: 14 }}>
                      Документы не найдены
                    </td>
                  </tr>
                ) : data.items.map((item) => (
                  <tr key={item.id}>
                    <td>{item.id}</td>
                    <td title={item.filename}>{truncateMiddle(item.filename, 72)}</td>
                    <td>{item.source_type || '—'}</td>
                    <td>
                      <span className={`badge ${item.status === 'active' ? 'badge-success' : item.status === 'archived' ? 'badge-warning' : 'badge-danger'}`}>
                        {item.status}
                      </span>
                    </td>
                    <td>{item.chunk_count}</td>
                    <td>
                      {item.has_summary ? (
                        <span title={item.summary_model_name || ''}>✓ {item.summary_model_name || 'summary'}</span>
                      ) : '—'}
                    </td>
                    <td title="ready/failed/stale">
                      {formatEmbeddingState(item.chunk_embeddings.ready, item.chunk_embeddings.failed, item.chunk_embeddings.stale)}
                    </td>
                    <td title="ready/failed/stale">
                      {formatEmbeddingState(item.summary_embeddings.ready, item.summary_embeddings.failed, item.summary_embeddings.stale)}
                    </td>
                    <td>{formatDate(item.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            <div className="text-dim" style={{ marginBottom: 6 }}>
              Embeddings в колонках показываются как `ready/failed/stale`; «нет данных» означает, что для документа индексация ещё не запускалась.
            </div>

            {totalPages > 1 && (
              <div className="pagination">
                <button className="btn btn-sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>← Назад</button>
                <span className="text-dim">Страница {page} из {totalPages} · {data.total} документов</span>
                <button className="btn btn-sm" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>Далее →</button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
