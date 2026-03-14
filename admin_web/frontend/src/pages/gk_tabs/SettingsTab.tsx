/**
 * Вкладка «Настройки» — runtime-настройки LLM Group Knowledge.
 *
 * Позволяет менять провайдера и модели для ключевых GK-сценариев
 * без перезапуска приложения.
 */

import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, type GKLLMSettingsResponse, type GKLLMSettingsUpdateRequest } from '../../api'

type TextModelKey = 'analysis' | 'responder' | 'question_detection' | 'terms_scan'

const TEXT_MODEL_LABELS: Array<{ key: TextModelKey; label: string }> = [
  { key: 'analysis', label: 'Модель анализатора Q&A' },
  { key: 'responder', label: 'Модель автоответчика' },
  { key: 'question_detection', label: 'Модель классификатора вопроса' },
  { key: 'terms_scan', label: 'Модель сканирования терминов' },
]

export default function SettingsTab() {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const [sourceSettings, setSourceSettings] = useState<GKLLMSettingsResponse | null>(null)

  const [textProvider, setTextProvider] = useState('')
  const [imageProvider, setImageProvider] = useState('')
  const [imageModel, setImageModel] = useState('')
  const [responderConfidenceThreshold, setResponderConfidenceThreshold] = useState('0.7')
  const [responderTopK, setResponderTopK] = useState('10')
  const [responderTemperature, setResponderTemperature] = useState('0.4')
  const [includeLLMInferredAnswers, setIncludeLLMInferredAnswers] = useState(false)
  const [excludeLowTierFromLLMContext, setExcludeLowTierFromLLMContext] = useState(true)
  const [analysisQuestionConfidenceThreshold, setAnalysisQuestionConfidenceThreshold] = useState('0.9')
  const [analysisTemperature, setAnalysisTemperature] = useState('0.2')
  const [questionDetectionTemperature, setQuestionDetectionTemperature] = useState('0.1')
  const [generateLLMInferredQAPairs, setGenerateLLMInferredQAPairs] = useState(false)
  const [acronymsMaxPromptTerms, setAcronymsMaxPromptTerms] = useState('50')
  const [termsScanTemperature, setTermsScanTemperature] = useState('0.2')
  const [hybridEnabled, setHybridEnabled] = useState(true)
  const [relevanceHintsEnabled, setRelevanceHintsEnabled] = useState(true)
  const [searchCandidatesPerMethod, setSearchCandidatesPerMethod] = useState('20')
  const [textModels, setTextModels] = useState<Record<TextModelKey, string>>({
    analysis: '',
    responder: '',
    question_detection: '',
    terms_scan: '',
  })

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    setSuccess('')
    try {
      const settings = await api.gkLLMSettings()
      setSourceSettings(settings)
      setTextProvider(settings.text_provider || '')
      setImageProvider(settings.image_provider || '')
      setImageModel(settings.image_model || '')
      setResponderConfidenceThreshold(String(settings.main_settings.responder.confidence_threshold))
      setResponderTopK(String(settings.main_settings.responder.top_k))
      setResponderTemperature(String(settings.main_settings.responder.temperature))
      setIncludeLLMInferredAnswers(Boolean(settings.main_settings.responder.include_llm_inferred_answers))
      setExcludeLowTierFromLLMContext(Boolean(settings.main_settings.responder.exclude_low_tier_from_llm_context))
      setAnalysisQuestionConfidenceThreshold(String(settings.main_settings.analysis.question_confidence_threshold))
      setAnalysisTemperature(String(settings.main_settings.analysis.temperature))
      setQuestionDetectionTemperature(String(settings.main_settings.analysis.question_detection_temperature))
      setGenerateLLMInferredQAPairs(Boolean(settings.main_settings.analysis.generate_llm_inferred_qa_pairs))
      setAcronymsMaxPromptTerms(String(settings.main_settings.terms.acronyms_max_prompt_terms))
      setTermsScanTemperature(String(settings.main_settings.terms.scan_temperature))
      setHybridEnabled(Boolean(settings.main_settings.search.hybrid_enabled))
      setRelevanceHintsEnabled(Boolean(settings.main_settings.search.relevance_hints_enabled))
      setSearchCandidatesPerMethod(String(settings.main_settings.search.candidates_per_method))
      setTextModels({
        analysis: settings.text_models.analysis || '',
        responder: settings.text_models.responder || '',
        question_detection: settings.text_models.question_detection || '',
        terms_scan: settings.text_models.terms_scan || '',
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось загрузить настройки')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const textModelSuggestions = useMemo(() => {
    if (!sourceSettings) return []
    return sourceSettings.text_model_options_by_provider[textProvider] || []
  }, [sourceSettings, textProvider])

  const imageModelSuggestions = useMemo(() => {
    if (!sourceSettings) return []
    return sourceSettings.image_model_options_by_provider[imageProvider] || []
  }, [sourceSettings, imageProvider])

  const onSave = useCallback(async () => {
    if (!sourceSettings) return

    setSaving(true)
    setError('')
    setSuccess('')

    const payload: GKLLMSettingsUpdateRequest = {}

    if (textProvider.trim() && textProvider.trim() !== sourceSettings.text_provider) {
      payload.text_provider = textProvider.trim()
    }

    const changedTextModels: Partial<Record<TextModelKey, string>> = {}
    const sourceTextModels = sourceSettings.text_models
    for (const key of ['analysis', 'responder', 'question_detection', 'terms_scan'] as TextModelKey[]) {
      const nextValue = (textModels[key] || '').trim()
      const sourceValue = (sourceTextModels[key] || '').trim()
      if (nextValue && nextValue !== sourceValue) {
        changedTextModels[key] = nextValue
      }
    }

    if (Object.keys(changedTextModels).length > 0) {
      payload.text_models = changedTextModels
    }

    if (imageProvider.trim() && imageProvider.trim() !== sourceSettings.image_provider) {
      payload.image_provider = imageProvider.trim()
    }

    if (imageModel.trim() && imageModel.trim() !== (sourceSettings.image_model || '').trim()) {
      payload.image_model = imageModel.trim()
    }

    const mainSettingsPayload: NonNullable<GKLLMSettingsUpdateRequest['main_settings']> = {}
    const responderMainPayload: NonNullable<NonNullable<GKLLMSettingsUpdateRequest['main_settings']>['responder']> = {}
    const analysisMainPayload: NonNullable<NonNullable<GKLLMSettingsUpdateRequest['main_settings']>['analysis']> = {}
    const termsMainPayload: NonNullable<NonNullable<GKLLMSettingsUpdateRequest['main_settings']>['terms']> = {}
    const searchMainPayload: NonNullable<NonNullable<GKLLMSettingsUpdateRequest['main_settings']>['search']> = {}

    const parsedResponderThreshold = Number(responderConfidenceThreshold)
    if (Number.isFinite(parsedResponderThreshold)) {
      const sourceResponderThreshold = Number(sourceSettings.main_settings.responder.confidence_threshold)
      if (parsedResponderThreshold !== sourceResponderThreshold) {
        responderMainPayload.confidence_threshold = parsedResponderThreshold
      }
    }

    const parsedResponderTopK = Number(responderTopK)
    if (Number.isInteger(parsedResponderTopK)) {
      const sourceResponderTopK = Number(sourceSettings.main_settings.responder.top_k)
      if (parsedResponderTopK !== sourceResponderTopK) {
        responderMainPayload.top_k = parsedResponderTopK
      }
    }

    const parsedResponderTemperature = Number(responderTemperature)
    if (Number.isFinite(parsedResponderTemperature)) {
      const sourceResponderTemperature = Number(sourceSettings.main_settings.responder.temperature)
      if (parsedResponderTemperature !== sourceResponderTemperature) {
        responderMainPayload.temperature = parsedResponderTemperature
      }
    }

    if (includeLLMInferredAnswers !== Boolean(sourceSettings.main_settings.responder.include_llm_inferred_answers)) {
      responderMainPayload.include_llm_inferred_answers = includeLLMInferredAnswers
    }

    if (excludeLowTierFromLLMContext !== Boolean(sourceSettings.main_settings.responder.exclude_low_tier_from_llm_context)) {
      responderMainPayload.exclude_low_tier_from_llm_context = excludeLowTierFromLLMContext
    }

    const parsedAnalysisThreshold = Number(analysisQuestionConfidenceThreshold)
    if (Number.isFinite(parsedAnalysisThreshold)) {
      const sourceAnalysisThreshold = Number(sourceSettings.main_settings.analysis.question_confidence_threshold)
      if (parsedAnalysisThreshold !== sourceAnalysisThreshold) {
        analysisMainPayload.question_confidence_threshold = parsedAnalysisThreshold
      }
    }

    const parsedAnalysisTemperature = Number(analysisTemperature)
    if (Number.isFinite(parsedAnalysisTemperature)) {
      const sourceAnalysisTemperature = Number(sourceSettings.main_settings.analysis.temperature)
      if (parsedAnalysisTemperature !== sourceAnalysisTemperature) {
        analysisMainPayload.temperature = parsedAnalysisTemperature
      }
    }

    const parsedQuestionDetectionTemperature = Number(questionDetectionTemperature)
    if (Number.isFinite(parsedQuestionDetectionTemperature)) {
      const sourceQuestionDetectionTemperature = Number(sourceSettings.main_settings.analysis.question_detection_temperature)
      if (parsedQuestionDetectionTemperature !== sourceQuestionDetectionTemperature) {
        analysisMainPayload.question_detection_temperature = parsedQuestionDetectionTemperature
      }
    }

    if (generateLLMInferredQAPairs !== Boolean(sourceSettings.main_settings.analysis.generate_llm_inferred_qa_pairs)) {
      analysisMainPayload.generate_llm_inferred_qa_pairs = generateLLMInferredQAPairs
    }

    const parsedAcronymsMaxPromptTerms = Number(acronymsMaxPromptTerms)
    if (Number.isInteger(parsedAcronymsMaxPromptTerms)) {
      const sourceAcronymsMaxPromptTerms = Number(sourceSettings.main_settings.terms.acronyms_max_prompt_terms)
      if (parsedAcronymsMaxPromptTerms !== sourceAcronymsMaxPromptTerms) {
        termsMainPayload.acronyms_max_prompt_terms = parsedAcronymsMaxPromptTerms
      }
    }

    const parsedTermsScanTemperature = Number(termsScanTemperature)
    if (Number.isFinite(parsedTermsScanTemperature)) {
      const sourceTermsScanTemperature = Number(sourceSettings.main_settings.terms.scan_temperature)
      if (parsedTermsScanTemperature !== sourceTermsScanTemperature) {
        termsMainPayload.scan_temperature = parsedTermsScanTemperature
      }
    }

    if (hybridEnabled !== Boolean(sourceSettings.main_settings.search.hybrid_enabled)) {
      searchMainPayload.hybrid_enabled = hybridEnabled
    }

    if (relevanceHintsEnabled !== Boolean(sourceSettings.main_settings.search.relevance_hints_enabled)) {
      searchMainPayload.relevance_hints_enabled = relevanceHintsEnabled
    }

    const parsedSearchCandidatesPerMethod = Number(searchCandidatesPerMethod)
    if (Number.isInteger(parsedSearchCandidatesPerMethod)) {
      const sourceSearchCandidatesPerMethod = Number(sourceSettings.main_settings.search.candidates_per_method)
      if (parsedSearchCandidatesPerMethod !== sourceSearchCandidatesPerMethod) {
        searchMainPayload.candidates_per_method = parsedSearchCandidatesPerMethod
      }
    }

    if (Object.keys(responderMainPayload).length > 0) {
      mainSettingsPayload.responder = responderMainPayload
    }
    if (Object.keys(analysisMainPayload).length > 0) {
      mainSettingsPayload.analysis = analysisMainPayload
    }
    if (Object.keys(termsMainPayload).length > 0) {
      mainSettingsPayload.terms = termsMainPayload
    }
    if (Object.keys(searchMainPayload).length > 0) {
      mainSettingsPayload.search = searchMainPayload
    }
    if (Object.keys(mainSettingsPayload).length > 0) {
      payload.main_settings = mainSettingsPayload
    }

    if (Object.keys(payload).length === 0) {
      setSuccess('Изменений нет')
      setSaving(false)
      return
    }

    try {
      await api.gkUpdateLLMSettings(payload)
      setSuccess('Настройки сохранены')
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось сохранить настройки')
    } finally {
      setSaving(false)
    }
  }, [
    acronymsMaxPromptTerms,
    analysisQuestionConfidenceThreshold,
    analysisTemperature,
    excludeLowTierFromLLMContext,
    generateLLMInferredQAPairs,
    hybridEnabled,
    imageModel,
    imageProvider,
    includeLLMInferredAnswers,
    load,
    questionDetectionTemperature,
    relevanceHintsEnabled,
    responderConfidenceThreshold,
    responderTemperature,
    responderTopK,
    searchCandidatesPerMethod,
    sourceSettings,
    termsScanTemperature,
    textModels,
    textProvider,
  ])

  if (loading) {
    return (
      <div className="card">
        <div className="loading-text">Загрузка настроек...</div>
      </div>
    )
  }

  if (!sourceSettings) {
    return (
      <div className="card">
        <div className="alert alert-danger">Не удалось загрузить настройки</div>
      </div>
    )
  }

  return (
    <div className="settings-tab">
      <div className="card" style={{ marginBottom: 16 }}>
        <h3 style={{ marginTop: 0 }}>⚙️ Текстовые LLM-модели GK</h3>
        <p className="text-dim" style={{ marginTop: 0 }}>
          Эти настройки используются анализатором Q&A, автоответчиком, классификатором вопросов и сканером терминов.
        </p>

        <div style={{ display: 'grid', gap: 10 }}>
          <label>
            Провайдер (движок LLM для текстовых задач GK)
            <select
              className="input"
              value={textProvider}
              onChange={(e) => setTextProvider(e.target.value)}
            >
              {sourceSettings.text_provider_options.map((providerName) => (
                <option key={providerName} value={providerName}>
                  {providerName}
                </option>
              ))}
            </select>
          </label>

          {TEXT_MODEL_LABELS.map((row) => (
            <label key={row.key}>
              {row.label} (конкретная модель для этого сценария)
              <input
                className="input"
                value={textModels[row.key]}
                onChange={(e) => setTextModels((prev) => ({ ...prev, [row.key]: e.target.value }))}
                placeholder="Введите имя модели"
                list={`gk-text-models-${row.key}`}
              />
              <datalist id={`gk-text-models-${row.key}`}>
                {textModelSuggestions.map((modelName) => (
                  <option key={`${row.key}-${modelName}`} value={modelName} />
                ))}
              </datalist>
            </label>
          ))}
        </div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <h3 style={{ marginTop: 0 }}>🖼 Vision-модель GK</h3>
        <p className="text-dim" style={{ marginTop: 0 }}>
          Используется для описания изображений в очереди Group Knowledge.
        </p>

        <div style={{ display: 'grid', gap: 10 }}>
          <label>
            Провайдер (движок Vision/мультимодального анализа)
            <select
              className="input"
              value={imageProvider}
              onChange={(e) => setImageProvider(e.target.value)}
            >
              {sourceSettings.image_provider_options.map((providerName) => (
                <option key={providerName} value={providerName}>
                  {providerName}
                </option>
              ))}
            </select>
          </label>

          <label>
            Модель описания изображений (используется для `image_description` в GK)
            <input
              className="input"
              value={imageModel}
              onChange={(e) => setImageModel(e.target.value)}
              placeholder="Введите имя модели"
              list="gk-image-models"
            />
            <datalist id="gk-image-models">
              {imageModelSuggestions.map((modelName) => (
                <option key={modelName} value={modelName} />
              ))}
            </datalist>
          </label>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <h3 style={{ marginTop: 0 }}>🤖 Основные настройки автоответчика</h3>
        <p className="text-dim" style={{ marginTop: 0 }}>
          Ключевые runtime-параметры генерации финального ответа и отбора контекста.
        </p>

        <div style={{ display: 'grid', gap: 10 }}>
          <label>
            Порог уверенности автоответчика (0..1, ниже порога ответ пользователю не отправляется)
            <input
              className="input"
              type="number"
              min={0}
              max={1}
              step={0.01}
              value={responderConfidenceThreshold}
              onChange={(e) => setResponderConfidenceThreshold(e.target.value)}
            />
          </label>

          <label>
            Температура автоответчика (0..2, ниже = стабильнее и строже, выше = креативнее и риск шума выше)
            <input
              className="input"
              type="number"
              min={0}
              max={2}
              step={0.01}
              value={responderTemperature}
              onChange={(e) => setResponderTemperature(e.target.value)}
            />
          </label>

          <label>
            Число Q&A-пар в контексте ответа (top-k, сколько найденных пар передаётся в LLM)
            <input
              className="input"
              type="number"
              min={1}
              max={100}
              step={1}
              value={responderTopK}
              onChange={(e) => setResponderTopK(e.target.value)}
            />
          </label>

          <label style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <input
              type="checkbox"
              checked={includeLLMInferredAnswers}
              onChange={(e) => setIncludeLLMInferredAnswers(e.target.checked)}
            />
            <span>Использовать llm_inferred пары при поиске ответа (включает пары, созданные LLM вне reply-цепочек)</span>
          </label>

          <label style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <input
              type="checkbox"
              checked={excludeLowTierFromLLMContext}
              onChange={(e) => setExcludeLowTierFromLLMContext(e.target.checked)}
            />
            <span>Исключать пары tier=«низкая» из финального LLM-контекста (уменьшает шум в ответе)</span>
          </label>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <h3 style={{ marginTop: 0 }}>🧬 Основные настройки анализатора</h3>
        <p className="text-dim" style={{ marginTop: 0 }}>
          Порог QUESTION_HINT для определения сообщения-вопроса в thread-анализе.
        </p>
        <div style={{ display: 'grid', gap: 10 }}>
          <label>
            Порог question_confidence_threshold (0..1, граница для QUESTION_HINT в thread-анализе)
            <input
              className="input"
              type="number"
              min={0}
              max={1}
              step={0.01}
              value={analysisQuestionConfidenceThreshold}
              onChange={(e) => setAnalysisQuestionConfidenceThreshold(e.target.value)}
            />
          </label>

          <label>
            Температура анализатора Q&A (0..2, для thread-validation и LLM-inferred; ниже = меньше фантазирования)
            <input
              className="input"
              type="number"
              min={0}
              max={2}
              step={0.01}
              value={analysisTemperature}
              onChange={(e) => setAnalysisTemperature(e.target.value)}
            />
          </label>

          <label>
            Температура классификатора вопросов (0..2, ниже = меньше ложных срабатываний, выше = выше чувствительность)
            <input
              className="input"
              type="number"
              min={0}
              max={2}
              step={0.01}
              value={questionDetectionTemperature}
              onChange={(e) => setQuestionDetectionTemperature(e.target.value)}
            />
          </label>

          <label style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <input
              type="checkbox"
              checked={generateLLMInferredQAPairs}
              onChange={(e) => setGenerateLLMInferredQAPairs(e.target.checked)}
            />
            <span>Генерировать llm_inferred Q&A-пары в анализаторе (дополняет thread-based пары)</span>
          </label>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <h3 style={{ marginTop: 0 }}>📖 Основные настройки аббревиатур</h3>
        <p className="text-dim" style={{ marginTop: 0 }}>
          Ограничение числа группо-специфичных аббревиатур, передаваемых в LLM-промпт.
        </p>

        <div style={{ display: 'grid', gap: 10 }}>
          <label>
            Максимум аббревиатур в промпте (1..500, ограничивает размер acronyms_section)
            <input
              className="input"
              type="number"
              min={1}
              max={500}
              step={1}
              value={acronymsMaxPromptTerms}
              onChange={(e) => setAcronymsMaxPromptTerms(e.target.value)}
            />
          </label>

          <label>
            Температура сканера терминов (0..2, ниже = чище кандидаты, выше = шире покрытие и риск ложноположительных)
            <input
              className="input"
              type="number"
              min={0}
              max={2}
              step={0.01}
              value={termsScanTemperature}
              onChange={(e) => setTermsScanTemperature(e.target.value)}
            />
          </label>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <h3 style={{ marginTop: 0 }}>🔎 Основные настройки поиска</h3>
        <p className="text-dim" style={{ marginTop: 0 }}>
          Управление гибридным поиском BM25+Vector и правилами передачи relevance-подсказок в LLM.
        </p>

        <div style={{ display: 'grid', gap: 10 }}>
          <label style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <input
              type="checkbox"
              checked={hybridEnabled}
              onChange={(e) => setHybridEnabled(e.target.checked)}
            />
            <span>Включить гибридный поиск (BM25 + Vector, иначе используется один метод)</span>
          </label>

          <label style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <input
              type="checkbox"
              checked={relevanceHintsEnabled}
              onChange={(e) => setRelevanceHintsEnabled(e.target.checked)}
            />
            <span>Передавать relevance-подсказки в LLM (tier/BM25/vector в контексте пар)</span>
          </label>

          <label>
            Кандидатов на метод перед RRF (candidates_per_method, размер пула BM25 и Vector до слияния)
            <input
              className="input"
              type="number"
              min={1}
              max={200}
              step={1}
              value={searchCandidatesPerMethod}
              onChange={(e) => setSearchCandidatesPerMethod(e.target.value)}
            />
          </label>
        </div>
      </div>

      {error && <div className="alert alert-danger" style={{ marginBottom: 12 }}>{error}</div>}
      {success && <div className="alert alert-success" style={{ marginBottom: 12 }}>{success}</div>}

      <button className="btn btn-primary" onClick={onSave} disabled={saving}>
        {saving ? 'Сохранение...' : '💾 Сохранить настройки'}
      </button>
    </div>
  )
}
