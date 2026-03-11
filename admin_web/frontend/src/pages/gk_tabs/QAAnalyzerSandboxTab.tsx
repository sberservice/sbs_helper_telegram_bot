/**
 * Вкладка «Песочница анализатора» — интерактивное тестирование промптов QA Analyzer.
 *
 * Позволяет искать сообщения по тексту, реконструировать цепочку обсуждения
 * (тем же алгоритмом, что и QAAnalyzer), редактировать промпт и запускать
 * анализ с произвольной моделью / температурой.
 */

import { useCallback, useEffect, useState } from 'react'
import {
  api,
  type ChainMessage,
  type GKGroup,
  type GKSupportedModelsResponse,
  type QAAnalyzerDefaultPrompt,
  type QAAnalyzerRunResult,
  type QAAnalyzerSearchMessage,
} from '../../api'

/* ------------------------------------------------------------------ */
/*  Вспомогательные компоненты                                        */
/* ------------------------------------------------------------------ */

function ChainMessageCard({
  message,
  isQuestionMsg,
  isAnswerMsg,
}: {
  message: ChainMessage
  isQuestionMsg?: boolean
  isAnswerMsg?: boolean
}) {
  const timestamp = message.message_date
    ? new Date(message.message_date * 1000).toLocaleString('ru-RU', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      })
    : ''
  const fullText = [
    message.message_text,
    message.caption ? `[Подпись] ${message.caption}` : null,
    message.image_description ? `[Изображение] ${message.image_description}` : null,
  ]
    .filter(Boolean)
    .join('\n')

  let extraClass = ''
  if (isQuestionMsg) extraClass = ' chain-msg-question'
  else if (isAnswerMsg) extraClass = ' chain-msg-answer'
  else if (message.is_question) extraClass = ' chain-msg-question'

  return (
    <div className={`chain-msg${extraClass}`}>
      <div className="chain-msg-header">
        <span className="chain-msg-id">[{message.telegram_message_id}]</span>
        <span className="chain-msg-sender">
          {message.sender_name || `User ${message.sender_id}`}
        </span>
        <span className="chain-msg-time">{timestamp}</span>
        {message.reply_to_message_id && (
          <span className="chain-msg-reply">→ ответ на {message.reply_to_message_id}</span>
        )}
        {message.has_image && <span className="badge badge-dim">📷</span>}
        {message.is_question && (
          <span
            className="badge badge-info"
            title={`Уверенность: ${(message.question_confidence ?? 0) * 100}%`}
          >
            ❓ {((message.question_confidence ?? 0) * 100).toFixed(0)}%
          </span>
        )}
        {isQuestionMsg && <span className="badge badge-info">ВОПРОС</span>}
        {isAnswerMsg && <span className="badge badge-success">ОТВЕТ</span>}
      </div>
      <div className="chain-msg-text">{fullText || '(пустое сообщение)'}</div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Основной компонент вкладки                                        */
/* ------------------------------------------------------------------ */

export default function QAAnalyzerSandboxTab() {
  // Поиск
  const [searchQuery, setSearchQuery] = useState('')
  const [searchGroupId, setSearchGroupId] = useState<number | undefined>(undefined)
  const [searchResults, setSearchResults] = useState<QAAnalyzerSearchMessage[]>([])
  const [searching, setSearching] = useState(false)
  const [searchError, setSearchError] = useState('')
  const [searched, setSearched] = useState(false)

  // Группы
  const [groups, setGroups] = useState<GKGroup[]>([])

  // Цепочка
  const [chain, setChain] = useState<ChainMessage[]>([])
  const [chainLoading, setChainLoading] = useState(false)
  const [chainError, setChainError] = useState('')
  const [selectedMessage, setSelectedMessage] = useState<QAAnalyzerSearchMessage | null>(null)

  // Промпт / настройки
  const [promptTemplate, setPromptTemplate] = useState('')
  const [systemPrompt, setSystemPrompt] = useState('')
  const [questionConfidenceThreshold, setQuestionConfidenceThreshold] = useState(0.9)
  const [model, setModel] = useState('')
  const [temperature, setTemperature] = useState<number | ''>('')
  const [models, setModels] = useState<string[]>([])
  const [defaultModel, setDefaultModel] = useState<string | null>(null)

  // Результат
  const [result, setResult] = useState<QAAnalyzerRunResult | null>(null)
  const [running, setRunning] = useState(false)
  const [runError, setRunError] = useState('')

  // Коллапсы
  const [showRenderedPrompt, setShowRenderedPrompt] = useState(false)
  const [showThreadContext, setShowThreadContext] = useState(false)
  const [showRawResponse, setShowRawResponse] = useState(false)

  // Загрузить группы, модели и промпт по умолчанию при маунте.
  useEffect(() => {
    api.gkGroups().then(setGroups).catch(() => {})
    api.gkQAAnalyzerSupportedModels().then((res: GKSupportedModelsResponse) => {
      setModels(res.models)
      setDefaultModel(res.default_model)
      if (res.default_model && !model) setModel(res.default_model)
    }).catch(() => {})
    api.gkQAAnalyzerDefaultPrompt().then((res: QAAnalyzerDefaultPrompt) => {
      if (!promptTemplate) setPromptTemplate(res.prompt_template)
      if (!systemPrompt) setSystemPrompt(res.system_prompt)
      setQuestionConfidenceThreshold(res.question_confidence_threshold)
    }).catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  /* ---- Поиск ---- */
  const doSearch = useCallback(async () => {
    const q = searchQuery.trim()
    if (q.length < 3) return
    setSearching(true)
    setSearchError('')
    try {
      const res = await api.gkQAAnalyzerSearch(q, searchGroupId, 50)
      setSearchResults(res)
      setSearched(true)
    } catch (err) {
      setSearchError(err instanceof Error ? err.message : 'Ошибка поиска')
    } finally {
      setSearching(false)
    }
  }, [searchQuery, searchGroupId])

  const handleSearchKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      doSearch()
    }
  }

  /* ---- Загрузка цепочки ---- */
  const loadChain = useCallback(
    async (msg: QAAnalyzerSearchMessage) => {
      setSelectedMessage(msg)
      setChainLoading(true)
      setChainError('')
      setResult(null)
      setRunError('')
      try {
        const res = await api.gkQAAnalyzerChain(msg.group_id, msg.telegram_message_id)
        setChain(res)
      } catch (err) {
        setChainError(err instanceof Error ? err.message : 'Ошибка загрузки цепочки')
        setChain([])
      } finally {
        setChainLoading(false)
      }
    },
    [],
  )

  /* ---- Запуск анализа ---- */
  const doRun = useCallback(async () => {
    if (!selectedMessage || chain.length === 0 || !promptTemplate.trim()) return
    setRunning(true)
    setRunError('')
    setResult(null)
    try {
      const res = await api.gkQAAnalyzerRun({
        group_id: selectedMessage.group_id,
        telegram_message_id: selectedMessage.telegram_message_id,
        prompt_template: promptTemplate,
        system_prompt: systemPrompt,
        model: model || undefined,
        temperature: temperature !== '' ? Number(temperature) : undefined,
        question_confidence_threshold: questionConfidenceThreshold,
      })
      setResult(res)
    } catch (err) {
      setRunError(err instanceof Error ? err.message : 'Ошибка выполнения')
    } finally {
      setRunning(false)
    }
  }, [selectedMessage, chain, promptTemplate, systemPrompt, model, temperature, questionConfidenceThreshold])

  /* ---- Сброс промпта ---- */
  const resetPrompt = useCallback(() => {
    api.gkQAAnalyzerDefaultPrompt().then((res: QAAnalyzerDefaultPrompt) => {
      setPromptTemplate(res.prompt_template)
      setSystemPrompt(res.system_prompt)
      setQuestionConfidenceThreshold(res.question_confidence_threshold)
    }).catch(() => {})
  }, [])

  /* ------------------------------------------------------------------ */
  /*  Рендер                                                            */
  /* ------------------------------------------------------------------ */

  const fmtTime = (ts: number) =>
    new Date(ts * 1000).toLocaleString('ru-RU', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })

  return (
    <div className="qa-analyzer-sandbox-tab">
      {/* ========== ПОИСК ========== */}
      <div className="card" style={{ marginBottom: 16 }}>
        <h3 style={{ marginTop: 0 }}>🔍 Поиск сообщений</h3>
        {searchError && <div className="alert alert-danger">{searchError}</div>}

        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          <input
            type="text"
            className="input"
            style={{ flex: 1, minWidth: 200 }}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={handleSearchKeyDown}
            placeholder="Поиск по тексту сообщения (минимум 3 символа)..."
            maxLength={500}
          />
          <select
            className="input input-sm"
            style={{ minWidth: 180 }}
            value={searchGroupId ?? ''}
            onChange={(e) =>
              setSearchGroupId(e.target.value ? Number(e.target.value) : undefined)
            }
          >
            <option value="">Все группы</option>
            {groups.map((g) => (
              <option key={g.group_id} value={g.group_id}>
                {g.group_title || `Группа ${g.group_id}`}
              </option>
            ))}
          </select>
          <button
            className="btn btn-primary"
            onClick={doSearch}
            disabled={searching || searchQuery.trim().length < 3}
          >
            {searching ? '...' : '🔍 Поиск'}
          </button>
        </div>

        {/* Результаты поиска */}
        {searched && searchResults.length === 0 && (
          <div className="empty-state" style={{ marginTop: 12 }}>
            <p>Ничего не найдено</p>
          </div>
        )}

        {searchResults.length > 0 && (
          <div style={{ marginTop: 12 }}>
            <div className="text-dim" style={{ marginBottom: 6 }}>
              Найдено: {searchResults.length}
            </div>
            <div style={{ maxHeight: 400, overflowY: 'auto' }}>
              <table className="table" style={{ fontSize: '0.9em' }}>
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Группа</th>
                    <th>Отправитель</th>
                    <th>Текст</th>
                    <th>Дата</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {searchResults.map((msg) => (
                    <tr
                      key={`${msg.group_id}-${msg.telegram_message_id}`}
                      className={
                        selectedMessage?.telegram_message_id === msg.telegram_message_id &&
                        selectedMessage?.group_id === msg.group_id
                          ? 'table-row-selected'
                          : ''
                      }
                    >
                      <td style={{ whiteSpace: 'nowrap' }}>{msg.telegram_message_id}</td>
                      <td style={{ whiteSpace: 'nowrap', maxWidth: 140, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {msg.group_title || String(msg.group_id)}
                      </td>
                      <td style={{ whiteSpace: 'nowrap', maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {msg.sender_name || `User ${msg.sender_id}`}
                      </td>
                      <td style={{ maxWidth: 400, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {msg.message_text?.slice(0, 200) || msg.caption?.slice(0, 200) || '(нет текста)'}
                        {msg.has_image && ' 📷'}
                        {msg.is_question && ` ❓${((msg.question_confidence ?? 0) * 100).toFixed(0)}%`}
                      </td>
                      <td style={{ whiteSpace: 'nowrap' }}>{fmtTime(msg.message_date)}</td>
                      <td>
                        <button
                          className="btn btn-sm btn-primary"
                          onClick={() => loadChain(msg)}
                          disabled={chainLoading}
                        >
                          Цепочка
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      {/* ========== ЦЕПОЧКА СООБЩЕНИЙ ========== */}
      {(chain.length > 0 || chainLoading || chainError) && (
        <div className="card" style={{ marginBottom: 16 }}>
          <h3 style={{ marginTop: 0 }}>
            💬 Цепочка сообщений
            {selectedMessage && (
              <span className="text-dim" style={{ fontSize: '0.85em', marginLeft: 8 }}>
                [{selectedMessage.telegram_message_id}] {selectedMessage.group_title}
              </span>
            )}
          </h3>
          {chainError && <div className="alert alert-danger">{chainError}</div>}
          {chainLoading && <div className="text-dim">Загрузка цепочки...</div>}
          {chain.length > 0 && (
            <div style={{ maxHeight: 500, overflowY: 'auto' }}>
              <div className="text-dim" style={{ marginBottom: 6 }}>
                Сообщений в цепочке: {chain.length}
              </div>
              {chain.map((msg) => (
                <ChainMessageCard
                  key={msg.telegram_message_id}
                  message={msg}
                  isQuestionMsg={
                    result ? msg.telegram_message_id === result.question_message_id : false
                  }
                  isAnswerMsg={
                    result?.parsed
                      ? msg.telegram_message_id === result.parsed.answer_message_id
                      : false
                  }
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* ========== ПРОМПТ И НАСТРОЙКИ ========== */}
      {chain.length > 0 && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>⚙️ Промпт и настройки</h3>
            <button className="btn btn-sm" onClick={resetPrompt}>
              ↩ Сбросить
            </button>
          </div>

          <div style={{ marginBottom: 8 }}>
            <label className="text-dim" style={{ display: 'block', marginBottom: 4 }}>
              Системный промпт
            </label>
            <input
              type="text"
              className="input"
              style={{ width: '100%' }}
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
            />
          </div>

          <div style={{ marginBottom: 8 }}>
            <label className="text-dim" style={{ display: 'block', marginBottom: 4 }}>
              Шаблон промпта
              <span style={{ fontSize: '0.8em', marginLeft: 8, opacity: 0.7 }}>
                Переменные: {'{question}'}, {'{thread_context}'}, {'{question_confidence_threshold}'}
              </span>
            </label>
            <textarea
              className="input"
              style={{ width: '100%', minHeight: 300, fontFamily: 'monospace', fontSize: '0.85em' }}
              value={promptTemplate}
              onChange={(e) => setPromptTemplate(e.target.value)}
            />
          </div>

          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'end' }}>
            <div>
              <label className="text-dim" style={{ display: 'block', marginBottom: 4 }}>
                Модель
              </label>
              <select
                className="input input-sm"
                value={model}
                onChange={(e) => setModel(e.target.value)}
                style={{ minWidth: 200 }}
              >
                {models.map((m) => (
                  <option key={m} value={m}>
                    {m}
                    {m === defaultModel ? ' (по умолчанию)' : ''}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-dim" style={{ display: 'block', marginBottom: 4 }}>
                Температура
              </label>
              <input
                type="number"
                className="input input-sm"
                style={{ width: 80 }}
                value={temperature}
                onChange={(e) =>
                  setTemperature(e.target.value === '' ? '' : Number(e.target.value))
                }
                min={0}
                max={2}
                step={0.1}
                placeholder="авто"
              />
            </div>
            <div>
              <label className="text-dim" style={{ display: 'block', marginBottom: 4 }}>
                Порог вопроса
              </label>
              <input
                type="number"
                className="input input-sm"
                style={{ width: 80 }}
                value={questionConfidenceThreshold}
                onChange={(e) => setQuestionConfidenceThreshold(Number(e.target.value))}
                min={0}
                max={1}
                step={0.05}
              />
            </div>
            <button
              className="btn btn-primary"
              onClick={doRun}
              disabled={running || chain.length === 0 || !promptTemplate.trim()}
            >
              {running ? '⏳ Выполнение...' : '▶ Запустить'}
            </button>
          </div>
        </div>
      )}

      {/* ========== РЕЗУЛЬТАТ ========== */}
      {runError && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="alert alert-danger">{runError}</div>
        </div>
      )}

      {result && (
        <div className="card" style={{ marginBottom: 16 }}>
          <h3 style={{ marginTop: 0 }}>
            📋 Результат
            <span className="text-dim" style={{ fontSize: '0.85em', marginLeft: 8 }}>
              {result.model} · {result.duration_ms} мс
            </span>
          </h3>

          {result.parsed ? (
            <div>
              {/* Статус валидности */}
              <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 12 }}>
                <span
                  className={`badge ${result.parsed.is_valid_qa ? 'badge-success' : 'badge-danger'}`}
                  style={{ fontSize: '1em', padding: '4px 10px' }}
                >
                  {result.parsed.is_valid_qa ? '✓ Валидная Q&A пара' : '✗ Не валидная'}
                </span>
                {result.parsed.confidence != null && (
                  <span className="pair-confidence" style={{ fontSize: '1em' }}>
                    {(result.parsed.confidence * 100).toFixed(0)}%
                  </span>
                )}
                {result.parsed.answer_message_id != null && (
                  <span className="text-dim">
                    Ответное сообщение: [{result.parsed.answer_message_id}]
                  </span>
                )}
              </div>

              {/* Чистый вопрос */}
              {result.parsed.clean_question && (
                <div style={{ marginBottom: 12 }}>
                  <div className="text-dim" style={{ marginBottom: 4 }}>
                    <strong>Чистый вопрос:</strong>
                  </div>
                  <pre
                    style={{
                      whiteSpace: 'pre-wrap',
                      background: 'var(--bg-secondary, #1a1a2e)',
                      padding: 10,
                      borderRadius: 6,
                      margin: 0,
                      fontFamily: 'inherit',
                    }}
                  >
                    {result.parsed.clean_question}
                  </pre>
                </div>
              )}

              {/* Чистый ответ */}
              {result.parsed.clean_answer && (
                <div style={{ marginBottom: 12 }}>
                  <div className="text-dim" style={{ marginBottom: 4 }}>
                    <strong>Чистый ответ:</strong>
                  </div>
                  <pre
                    style={{
                      whiteSpace: 'pre-wrap',
                      background: 'var(--bg-secondary, #1a1a2e)',
                      padding: 10,
                      borderRadius: 6,
                      margin: 0,
                      fontFamily: 'inherit',
                    }}
                  >
                    {result.parsed.clean_answer}
                  </pre>
                </div>
              )}
            </div>
          ) : (
            <div className="alert alert-danger">Не удалось распарсить ответ LLM</div>
          )}

          {/* Коллапсируемые секции */}
          <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
            {/* Raw response */}
            <div>
              <button
                className="btn btn-sm"
                onClick={() => setShowRawResponse(!showRawResponse)}
              >
                {showRawResponse ? '▼' : '▶'} Сырой ответ LLM
              </button>
              {showRawResponse && (
                <pre
                  style={{
                    whiteSpace: 'pre-wrap',
                    background: 'var(--bg-secondary, #1a1a2e)',
                    padding: 10,
                    borderRadius: 6,
                    marginTop: 6,
                    fontSize: '0.85em',
                    maxHeight: 400,
                    overflowY: 'auto',
                  }}
                >
                  {result.raw_response}
                </pre>
              )}
            </div>

            {/* Rendered prompt */}
            <div>
              <button
                className="btn btn-sm"
                onClick={() => setShowRenderedPrompt(!showRenderedPrompt)}
              >
                {showRenderedPrompt ? '▼' : '▶'} Отрисованный промпт
              </button>
              {showRenderedPrompt && (
                <pre
                  style={{
                    whiteSpace: 'pre-wrap',
                    background: 'var(--bg-secondary, #1a1a2e)',
                    padding: 10,
                    borderRadius: 6,
                    marginTop: 6,
                    fontSize: '0.85em',
                    maxHeight: 400,
                    overflowY: 'auto',
                  }}
                >
                  {result.rendered_prompt}
                </pre>
              )}
            </div>

            {/* Thread context */}
            <div>
              <button
                className="btn btn-sm"
                onClick={() => setShowThreadContext(!showThreadContext)}
              >
                {showThreadContext ? '▼' : '▶'} Контекст цепочки
              </button>
              {showThreadContext && (
                <pre
                  style={{
                    whiteSpace: 'pre-wrap',
                    background: 'var(--bg-secondary, #1a1a2e)',
                    padding: 10,
                    borderRadius: 6,
                    marginTop: 6,
                    fontSize: '0.85em',
                    maxHeight: 400,
                    overflowY: 'auto',
                  }}
                >
                  {result.thread_context}
                </pre>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
