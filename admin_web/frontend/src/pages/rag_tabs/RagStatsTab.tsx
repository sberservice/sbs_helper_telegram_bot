import { useCallback, useEffect, useState } from 'react'
import { api, type RAGCorpusStatsResponse } from '../../api'

function formatDate(value: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('ru-RU')
}

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`
}

export default function RagStatsTab() {
  const [stats, setStats] = useState<RAGCorpusStatsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await api.gkRAGCorpusStats()
      setStats(data)
    } catch (e: any) {
      setError(e?.message || 'Не удалось загрузить статистику RAG корпуса')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  if (loading) return <div className="loading-text">Загрузка статистики...</div>
  if (error) return <div className="alert alert-danger">{error}</div>
  if (!stats) return <div className="text-dim">Нет данных</div>

  return (
    <div style={{ display: 'grid', gap: 12 }}>
      <div className="card">
        <h3 style={{ marginTop: 0 }}>📄 Документы</h3>
        <p className="text-dim">Всего: <strong>{stats.documents.total}</strong> · Active: {stats.documents.active} · Archived: {stats.documents.archived} · Deleted: {stats.documents.deleted}</p>
        <p className="text-dim">Последнее обновление: {formatDate(stats.documents.last_updated_at)}</p>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {Object.entries(stats.documents.by_source_type).map(([sourceType, count]) => (
            <span key={sourceType} className="badge badge-dim">{sourceType}: {count}</span>
          ))}
        </div>
      </div>

      <div className="card">
        <h3 style={{ marginTop: 0 }}>🧩 Чанки</h3>
        <p className="text-dim">Всего чанков: <strong>{stats.chunks.total}</strong></p>
        <p className="text-dim">Среднее на документ: {stats.chunks.avg_per_document} · Максимум на документ: {stats.chunks.max_per_document}</p>
        <p className="text-dim">Последний создан: {formatDate(stats.chunks.last_created_at)}</p>
      </div>

      <div className="card">
        <h3 style={{ marginTop: 0 }}>📝 Summary</h3>
        <p className="text-dim">Всего summary: <strong>{stats.summaries.total}</strong> · с model_name: {stats.summaries.with_model_name}</p>
        <p className="text-dim">Последнее обновление: {formatDate(stats.summaries.last_updated_at)}</p>
      </div>

      <div className="card">
        <h3 style={{ marginTop: 0 }}>🧠 Embeddings (chunks)</h3>
        <p className="text-dim">Всего: <strong>{stats.chunk_embeddings.total}</strong> · Ready: {stats.chunk_embeddings.ready} · Failed: {stats.chunk_embeddings.failed} · Stale: {stats.chunk_embeddings.stale}</p>
        <p className="text-dim">Последнее обновление: {formatDate(stats.chunk_embeddings.last_updated_at)}</p>
      </div>

      <div className="card">
        <h3 style={{ marginTop: 0 }}>🧠 Embeddings (summary)</h3>
        <p className="text-dim">Всего: <strong>{stats.summary_embeddings.total}</strong> · Ready: {stats.summary_embeddings.ready} · Failed: {stats.summary_embeddings.failed} · Stale: {stats.summary_embeddings.stale}</p>
        <p className="text-dim">Последнее обновление: {formatDate(stats.summary_embeddings.last_updated_at)}</p>
      </div>

      <div className="card">
        <h3 style={{ marginTop: 0 }}>📊 Query Log</h3>
        <p className="text-dim">Всего запросов: <strong>{stats.query_log.total}</strong> · Cache hits: {stats.query_log.cache_hits} ({formatPercent(stats.query_log.cache_hit_ratio)})</p>
        <p className="text-dim">За 24ч: {stats.query_log.last_24h} · За 7д: {stats.query_log.last_7d} · Уникальных пользователей: {stats.query_log.unique_users}</p>
        <p className="text-dim">Последний запрос: {formatDate(stats.query_log.last_query_at)}</p>
      </div>

      <div className="card">
        <h3 style={{ marginTop: 0 }}>🧾 Версии корпуса</h3>
        <p className="text-dim">Всего версий: <strong>{stats.corpus_version.total_versions}</strong></p>
        <p className="text-dim">Последняя причина: {stats.corpus_version.last_reason || '—'}</p>
        <p className="text-dim">Последнее изменение версии: {formatDate(stats.corpus_version.last_created_at)}</p>
      </div>

      <div>
        <button className="btn btn-sm" onClick={load}>🔄 Обновить статистику</button>
      </div>
    </div>
  )
}
