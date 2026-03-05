import { useState, useEffect } from 'react'
import type { Prompt, PromptCreatePayload } from '../api'

interface Props {
  initial?: Prompt
  onSave: (data: PromptCreatePayload) => Promise<void>
  onCancel: () => void
}

const DEFAULT_SYSTEM_PROMPT = `Ты — профессиональный технический редактор.

Создай краткое описание (summary) документа **"{document_name}"**.

Текст документа:
---
{document_excerpt}
---

Требования:
- Максимум {max_summary_chars} символов
- Передай ключевые тезисы и практическую пользу
- Используй профессиональный, но понятный язык`

export default function PromptEditor({ initial, onSave, onCancel }: Props) {
  const [label, setLabel] = useState(initial?.label ?? '')
  const [systemPrompt, setSystemPrompt] = useState(initial?.system_prompt_template ?? DEFAULT_SYSTEM_PROMPT)
  const [userMessage, setUserMessage] = useState(initial?.user_message ?? 'Создай summary для этого документа.')
  const [modelName, setModelName] = useState(initial?.model_name ?? '')
  const [temperature, setTemperature] = useState<string>(
    initial?.temperature != null ? String(initial.temperature) : ''
  )
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (initial) {
      setLabel(initial.label)
      setSystemPrompt(initial.system_prompt_template)
      setUserMessage(initial.user_message)
      setModelName(initial.model_name ?? '')
      setTemperature(initial.temperature != null ? String(initial.temperature) : '')
    }
  }, [initial])

  const handleSubmit = async () => {
    if (!label.trim()) { setError('Укажите название'); return }
    if (!systemPrompt.trim()) { setError('Укажите system prompt'); return }
    if (!userMessage.trim()) { setError('Укажите user message'); return }

    const temp = temperature.trim() ? parseFloat(temperature) : undefined
    if (temp !== undefined && (isNaN(temp) || temp < 0 || temp > 2)) {
      setError('Temperature должна быть от 0.0 до 2.0')
      return
    }

    setSaving(true)
    setError('')
    try {
      await onSave({
        label: label.trim(),
        system_prompt_template: systemPrompt.trim(),
        user_message: userMessage.trim(),
        model_name: modelName.trim() || undefined,
        temperature: temp,
      })
    } catch (e) {
      setError(String(e))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div style={{ maxHeight: '70vh', overflowY: 'auto', padding: '0 4px' }}>
      <div className="form-group">
        <label className="form-label">Название</label>
        <input
          className="form-input"
          value={label}
          onChange={e => setLabel(e.target.value)}
          placeholder="Промпт v2 — формальный стиль"
        />
        <div className="form-hint">Краткое название для идентификации в результатах</div>
      </div>

      <div className="form-group">
        <label className="form-label">System Prompt Template</label>
        <textarea
          className="form-textarea"
          value={systemPrompt}
          onChange={e => setSystemPrompt(e.target.value)}
          rows={10}
          placeholder="Шаблон system prompt с переменными {document_name}, {document_excerpt}, {max_summary_chars}"
        />
        <div className="form-hint">
          Переменные: <code>{'{document_name}'}</code>, <code>{'{document_excerpt}'}</code>, <code>{'{max_summary_chars}'}</code>
        </div>
      </div>

      <div className="form-group">
        <label className="form-label">User Message</label>
        <textarea
          className="form-textarea"
          value={userMessage}
          onChange={e => setUserMessage(e.target.value)}
          rows={3}
          placeholder="Создай summary для документа."
        />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <div className="form-group">
          <label className="form-label">Модель (необязательно)</label>
          <input
            className="form-input"
            value={modelName}
            onChange={e => setModelName(e.target.value)}
            placeholder="deepseek-chat (по умолчанию)"
          />
        </div>

        <div className="form-group">
          <label className="form-label">Temperature (необязательно)</label>
          <input
            className="form-input"
            type="number"
            step="0.1"
            min="0"
            max="2"
            value={temperature}
            onChange={e => setTemperature(e.target.value)}
            placeholder="0.7 (по умолчанию)"
          />
        </div>
      </div>

      {error && (
        <div style={{ color: 'var(--danger)', marginBottom: 12, fontSize: 13 }}>
          {error}
        </div>
      )}

      <div className="btn-group" style={{ justifyContent: 'flex-end', marginTop: 16 }}>
        <button className="btn" onClick={onCancel}>Отмена</button>
        <button className="btn btn-primary" onClick={handleSubmit} disabled={saving}>
          {saving ? 'Сохранение...' : initial ? 'Обновить' : 'Создать'}
        </button>
      </div>
    </div>
  )
}
