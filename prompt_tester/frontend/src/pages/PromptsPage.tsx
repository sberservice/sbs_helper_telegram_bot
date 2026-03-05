import { useEffect, useState } from 'react'
import { api, type Prompt, type PromptCreatePayload } from '../api'
import PromptEditor from '../components/PromptEditor'

export default function PromptsPage() {
  const [prompts, setPrompts] = useState<Prompt[]>([])
  const [loading, setLoading] = useState(true)
  const [showEditor, setShowEditor] = useState(false)
  const [editingPrompt, setEditingPrompt] = useState<Prompt | null>(null)
  const [previewData, setPreviewData] = useState<{ id: number; data: object } | null>(null)
  const [showInactive, setShowInactive] = useState(false)

  const loadPrompts = async () => {
    setLoading(true)
    try {
      const data = await api.listPrompts(!showInactive)
      setPrompts(data)
    } catch (e) {
      console.error('Ошибка загрузки промптов:', e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadPrompts() }, [showInactive])

  const handleCreate = async (data: PromptCreatePayload) => {
    await api.createPrompt(data)
    setShowEditor(false)
    loadPrompts()
  }

  const handleUpdate = async (data: PromptCreatePayload) => {
    if (!editingPrompt) return
    await api.updatePrompt(editingPrompt.id, data)
    setEditingPrompt(null)
    loadPrompts()
  }

  const handleDelete = async (id: number) => {
    if (!confirm('Архивировать этот промпт?')) return
    await api.deletePrompt(id)
    loadPrompts()
  }

  const handleDuplicate = async (id: number) => {
    await api.duplicatePrompt(id)
    loadPrompts()
  }

  const handlePreview = async (id: number) => {
    try {
      const data = await api.previewPrompt(id)
      setPreviewData({ id, data })
    } catch (e) {
      alert(`Ошибка предпросмотра: ${e}`)
    }
  }

  return (
    <>
      <div className="page-header">
        <h1 className="page-title">Пары промптов</h1>
        <div className="btn-group">
          <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: 'var(--text-dim)' }}>
            <input type="checkbox" checked={showInactive} onChange={(e) => setShowInactive(e.target.checked)} />
            Показать архивные
          </label>
          <button className="btn btn-primary" onClick={() => { setEditingPrompt(null); setShowEditor(true) }}>
            + Создать пару
          </button>
        </div>
      </div>

      {loading ? (
        <div className="loading">Загрузка...</div>
      ) : prompts.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-icon">📝</div>
          <p>Нет промптов. Создайте первую пару для начала тестирования.</p>
          <button className="btn btn-primary mt-4" onClick={() => setShowEditor(true)}>
            Создать пару промптов
          </button>
        </div>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Название</th>
              <th>Модель</th>
              <th>Temp</th>
              <th>Тестов</th>
              <th>Обновлён</th>
              <th>Действия</th>
            </tr>
          </thead>
          <tbody>
            {prompts.map(p => (
              <tr key={p.id} style={{ opacity: p.is_active ? 1 : 0.5 }}>
                <td>{p.id}</td>
                <td>
                  <strong>{p.label}</strong>
                  {!p.is_active && <span className="badge badge-danger" style={{ marginLeft: 8 }}>архив</span>}
                </td>
                <td><span className="badge badge-info">{p.model_name || 'default'}</span></td>
                <td>{p.temperature != null ? p.temperature.toFixed(1) : '—'}</td>
                <td>{p.usage_count}</td>
                <td className="text-dim">{new Date(p.updated_at).toLocaleDateString('ru')}</td>
                <td>
                  <div className="btn-group">
                    <button className="btn" onClick={() => { setEditingPrompt(p); setShowEditor(true) }} title="Редактировать">✏️</button>
                    <button className="btn" onClick={() => handleDuplicate(p.id)} title="Клонировать">📋</button>
                    <button className="btn" onClick={() => handlePreview(p.id)} title="Предпросмотр">👁</button>
                    {p.is_active && (
                      <button className="btn" onClick={() => handleDelete(p.id)} title="Архивировать">🗑</button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {/* Editor modal */}
      {showEditor && (
        <div className="modal-overlay" onClick={() => { setShowEditor(false); setEditingPrompt(null) }}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h2 className="modal-title">{editingPrompt ? 'Редактировать промпт' : 'Новый промпт'}</h2>
              <button className="modal-close" onClick={() => { setShowEditor(false); setEditingPrompt(null) }}>&times;</button>
            </div>
            <PromptEditor
              initial={editingPrompt ?? undefined}
              onSave={editingPrompt ? handleUpdate : handleCreate}
              onCancel={() => { setShowEditor(false); setEditingPrompt(null) }}
            />
          </div>
        </div>
      )}

      {/* Preview modal */}
      {previewData && (
        <div className="modal-overlay" onClick={() => setPreviewData(null)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h2 className="modal-title">Предпросмотр промпта</h2>
              <button className="modal-close" onClick={() => setPreviewData(null)}>&times;</button>
            </div>
            <div className="form-group">
              <label className="form-label">Документ</label>
              <code>{(previewData.data as Record<string, string>).document_name}</code>
            </div>
            <div className="form-group">
              <label className="form-label">System Prompt (после подстановки)</label>
              <pre style={{ background: 'var(--bg)', padding: 12, borderRadius: 'var(--radius)', whiteSpace: 'pre-wrap', fontSize: 12, maxHeight: 300, overflow: 'auto' }}>
                {(previewData.data as Record<string, string>).rendered_system_prompt}
              </pre>
            </div>
            <div className="form-group">
              <label className="form-label">User Message</label>
              <pre style={{ background: 'var(--bg)', padding: 12, borderRadius: 'var(--radius)', whiteSpace: 'pre-wrap', fontSize: 12 }}>
                {(previewData.data as Record<string, string>).user_message}
              </pre>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
