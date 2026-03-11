/**
 * Вкладка «Очередь изображений» — мониторинг обработки скриншотов GigaChat Vision.
 */

import { useCallback, useEffect, useState } from 'react'
import {
  api,
  type GKImageQueueStatus,
  type GKImageQueueItem,
} from '../../api'

const STATUS_LABELS: Record<number, string> = {
  0: 'Ожидание',
  1: 'Обработка',
  2: 'Готово',
  3: 'Ошибка',
}

const STATUS_BADGE: Record<number, string> = {
  0: 'badge-dim',
  1: 'badge-info',
  2: 'badge-success',
  3: 'badge-danger',
}

export default function ImagesTab() {
  const [status, setStatus] = useState<GKImageQueueStatus | null>(null)
  const [items, setItems] = useState<GKImageQueueItem[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const [page, setPage] = useState(1)
  const [pageSize] = useState(20)
  const [statusFilter, setStatusFilter] = useState<number | null>(null)
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [uploadGroupId, setUploadGroupId] = useState('0')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [st, listRes] = await Promise.all([
        api.gkImageStatus(),
        api.gkImageList({ page, page_size: pageSize, status: statusFilter }),
      ])
      setStatus(st)
      setItems(listRes.items)
      setTotal(listRes.total)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка загрузки')
    } finally {
      setLoading(false)
    }
  }, [page, pageSize, statusFilter])

  useEffect(() => { load() }, [load])

  const uploadImage = async () => {
    if (!uploadFile) {
      setError('Выберите файл изображения для загрузки')
      return
    }
    setUploading(true)
    setError('')
    try {
      const formData = new FormData()
      formData.append('image', uploadFile)
      formData.append('group_id', uploadGroupId || '0')
      await api.gkImageUpload(formData)
      setUploadFile(null)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка загрузки изображения')
    } finally {
      setUploading(false)
    }
  }

  const totalPages = Math.ceil(total / pageSize)

  return (
    <div className="gk-images-tab">
      {error && <div className="alert alert-danger">{error}</div>}

      {/* Статус очереди */}
      {status && (
        <div className="stats-bar">
          <div className="stat">
            <span className="stat-value">{status.pending}</span>
            <span className="stat-label">Ожидание</span>
          </div>
          <div className="stat stat-accent">
            <span className="stat-value">{status.processing}</span>
            <span className="stat-label">Обработка</span>
          </div>
          <div className="stat stat-success">
            <span className="stat-value">{status.done}</span>
            <span className="stat-label">Готово</span>
          </div>
          <div className="stat stat-danger">
            <span className="stat-value">{status.error}</span>
            <span className="stat-label">Ошибка</span>
          </div>
        </div>
      )}

      {/* Фильтр */}
      <div className="filters-bar">
        <select className="input input-sm" value={statusFilter ?? ''} onChange={e => { setStatusFilter(e.target.value !== '' ? Number(e.target.value) : null); setPage(1) }}>
          <option value="">Все статусы</option>
          <option value="0">Ожидание</option>
          <option value="1">Обработка</option>
          <option value="2">Готово</option>
          <option value="3">Ошибка</option>
        </select>
      </div>

      <div className="card" style={{ marginBottom: 12 }}>
        <h3 style={{ marginBottom: 8 }}>Добавить изображение</h3>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <input type="file" accept="image/*" onChange={e => setUploadFile(e.target.files?.[0] || null)} />
          <input
            className="input input-sm"
            style={{ width: 160 }}
            value={uploadGroupId}
            onChange={e => setUploadGroupId(e.target.value)}
            placeholder="group_id (опц.)"
          />
          <button className="btn btn-primary" disabled={uploading || !uploadFile} onClick={uploadImage}>
            {uploading ? 'Загрузка...' : 'Загрузить'}
          </button>
        </div>
      </div>

      {/* Список */}
      {loading ? (
        <div className="loading-text">Загрузка...</div>
      ) : items.length === 0 ? (
        <div className="card empty-state"><p>Нет элементов в очереди</p></div>
      ) : (
        <>
          <div className="image-queue-list">
            {items.map(item => (
              <div
                key={item.id}
                className="card image-queue-item"
                onClick={() => setExpandedId(expandedId === item.id ? null : item.id)}
              >
                <div className="responder-entry-header">
                  <span className="pair-id">#{item.id}</span>
                  <span className={`badge ${STATUS_BADGE[item.status] || 'badge-dim'}`}>
                    {STATUS_LABELS[item.status] || item.status_label}
                  </span>
                  <span className="text-dim">Группа: {item.group_id}</span>
                  <span className="text-dim">Сообщ: {item.message_id}</span>
                  {item.created_at && <span className="text-dim">{item.created_at}</span>}
                </div>
                {expandedId === item.id && (
                  <div style={{ marginTop: 8 }}>
                    <div style={{ marginBottom: 8 }}>
                      <img
                        src={`/api/gk-knowledge/images/${item.id}/preview`}
                        alt={`preview-${item.id}`}
                        style={{ maxWidth: '100%', maxHeight: 220, borderRadius: 6, border: '1px solid var(--border)' }}
                      />
                    </div>
                    {(item.image_path || item.file_path) && <div className="text-dim" style={{ fontSize: 12 }}>Путь: {item.image_path || item.file_path}</div>}
                    {item.image_description && (
                      <div style={{ marginTop: 6 }}>
                        <strong>Описание:</strong>
                        <div className="qa-text" style={{ marginTop: 4 }}>{item.image_description}</div>
                      </div>
                    )}
                    {!item.image_description && item.status === 2 && (
                      <div className="text-dim">Описание отсутствует</div>
                    )}
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
