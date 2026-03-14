"""
Поиск по Q&A-парам для подсистемы Group Knowledge.

Выполняет гибридный поиск (BM25 + vector) с объединением результатов
через Reciprocal Rank Fusion (RRF) и генерирует ответы с помощью LLM.
"""

import json
import logging
import math
import re
import time
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

from config import ai_settings
from src.core.ai.llm_provider import get_provider, is_provider_registered
from src.group_knowledge.acronyms import (
    select_best_acronyms_by_term,
    sort_acronym_records_for_prompt,
)
from src.group_knowledge import database as gk_db
from src.group_knowledge.models import QAPair
from src.group_knowledge.rag_text import enrich_question_for_rag

try:
    from rank_bm25 import BM25Okapi
except ImportError:
    BM25Okapi = None  # type: ignore[misc,assignment]

try:
    from symspellpy import SymSpell, Verbosity as _SymSpellVerbosity  # type: ignore[import-untyped]
except Exception:
    SymSpell = None  # type: ignore[misc,assignment]
    _SymSpellVerbosity = None  # type: ignore[misc,assignment]

logger = logging.getLogger(__name__)

# Regex для удаления markdown code fences из JSON-ответа LLM.
_JSON_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)

_ANSWER_ALLOWED_EXTRACTION_TYPES: Tuple[str, ...] = (
    "thread_reply",
    "llm_inferred",
)

# ---------------------------------------------------------------------------
# Токенизация и нормализация текста
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"\d+(?:[\.,]\d+)+|[a-zа-яё0-9_]+", re.IGNORECASE)
_SHORT_ALNUM_TOKEN_RE = re.compile(r"(?:[a-zа-яё]\d|\d[a-zа-яё])", re.IGNORECASE)
_CYRILLIC_TOKEN_RE = re.compile(r"[а-яё]", re.IGNORECASE)
_MULTISPACE_RE = re.compile(r"\s+", re.IGNORECASE)

# Стоп-слова: высокочастотные функциональные слова без предметной нагрузки.
_GK_STOPWORDS: frozenset = frozenset({
    "что", "это", "как", "так", "его", "все", "она", "они",
    "был", "уже", "тот", "или", "ещё", "еще", "нет", "более",
    "какой", "какая", "какое", "каком", "какие", "каких",
    "такое", "такой", "такая", "такие", "таких",
    "который", "которая", "которое", "которые",
    "этот", "этого", "этом", "этой",
    "свой", "своя", "свои", "своего",
    "можно", "нужно", "надо",
    "кто", "где", "когда", "зачем", "почему", "чего", "чем",
    "для", "при", "без", "под", "над", "между",
    "наша", "наш", "наше", "наши", "ваш", "ваша", "ваше", "ваши",
    "чтобы", "если", "также", "тоже",
})

# Хардкодные термины — fallback на случай недоступности БД.
_GK_FIXED_TERMS_FALLBACK: frozenset = frozenset({
    "осно", "усн", "псн", "енвд", "нпд", "сно",
    "фн", "ккт", "офд", "инн", "кпп", "аусн",
    "ип", "ндс", "ндфл", "ооо", "кбк",
    "ффд", "фд", "фп", "фпд", "рн", "зн", "ккм",
    "pos", "пин", "арм", "цто", "то", "усо", "атм",
    "nfc", "sim", "pin", "tcp", "usb", "lan", "gps",
    "гз", "гпн", "эвотор 6", "эво6", "эвотор6",
    "чз", "уз", "ца", "цк", "сбс", "рм", "тст", "утп", "лкп", "лкк",
    "1с",
})

# ---------------------------------------------------------------------------
# Кэш загрузки терминов из БД (lazy; fallback на хардкод)
# ---------------------------------------------------------------------------
_terms_cache: Dict[Optional[int], Tuple[frozenset, float]] = {}


def load_fixed_terms(group_id: Optional[int] = None) -> frozenset:
    """Загрузить approved защищённые термины из БД с TTL-кэшированием.

    Кэш хранится per-group_id, чтобы не вызывать thrashing при
    обслуживании нескольких групп.

    Все approved-термины становятся защищёнными BM25-токенами
    (независимо от наличия definition).

    Если БД недоступна, возвращает хардкодный fallback.
    """
    now = time.time()
    ttl = ai_settings.GK_TERMS_CACHE_TTL_SECONDS

    cached = _terms_cache.get(group_id)
    if cached is not None:
        data, ts = cached
        if (now - ts) < ttl:
            return data

    try:
        terms_set = set(gk_db.get_approved_terms(group_id) or set())

        if terms_set:
            result = frozenset(terms_set)
            _terms_cache[group_id] = (result, now)
            return result
    except Exception:
        logger.debug("Не удалось загрузить термины из БД, используется fallback")

    return _GK_FIXED_TERMS_FALLBACK


def build_derived_term_structures(
    terms: frozenset,
) -> Tuple[
    Tuple[str, ...],
    Dict[str, str],
    Dict[str, str],
    frozenset,
]:
    """Построить производные структуры из множества защищённых терминов.

    Returns:
        (phrases, term_token_map, token_term_map, tokens_set)
    """
    phrases = tuple(
        sorted((t for t in terms if " " in t), key=len, reverse=True),
    )
    term_token_map: Dict[str, str] = {
        t: _MULTISPACE_RE.sub("_", t.strip().lower()) for t in terms
    }
    token_term_map: Dict[str, str] = {
        tok: t for t, tok in term_token_map.items()
    }
    tokens_set = frozenset(term_token_map.values())
    return phrases, term_token_map, token_term_map, tokens_set


# Совместимость: модульные переменные, загружаемые из fallback.
# Используются только кодом, который не имеет доступа к экземпляру
# QASearchService (тесты, утилиты).
_GK_FIXED_TERMS = _GK_FIXED_TERMS_FALLBACK
_GK_FIXED_PHRASES, _GK_FIXED_TERM_TOKEN_MAP, _GK_FIXED_TOKEN_TO_TERM_MAP, _GK_FIXED_TOKENS = (
    build_derived_term_structures(_GK_FIXED_TERMS_FALLBACK)
)


def _canonical_fixed_token(token: str, fixed_tokens: Optional[frozenset] = None,
                           term_token_map: Optional[Dict[str, str]] = None) -> str:
    """Привести токен к каноничному виду для protected terms."""
    safe_token = (token or "").strip().lower()
    if not safe_token:
        return ""

    tokens_set = fixed_tokens if fixed_tokens is not None else _GK_FIXED_TOKENS
    t_map = term_token_map if term_token_map is not None else _GK_FIXED_TERM_TOKEN_MAP

    if safe_token in tokens_set:
        return safe_token

    mapped = t_map.get(safe_token)
    if mapped:
        return mapped

    return safe_token

#3. Если ни одна пара не релевантна вопросу — честно скажи, что не нашёл информации.

# Промпт для генерации ответа на основе Q&A пар
_ANSWER_PROMPT_BASE = """Ты — помощник технической поддержки для полевых инженеров компании СберСервис, обслуживающих банк Сбербанк.

На основе найденных пар вопрос-ответ из базы знаний технической поддержки ответь на вопрос инженера по тематике ККТ (контрольно-кассовая техника).


Верни JSON:
{{
    "answer": "Текст ответа",
    "is_relevant": true/false,
    "confidence": Это не confidence пар, а другой параметр, создай его с нуля 0.0-1.0
    "confidence_reason": "Краткое объяснение, почему такой уровень confidence (макс 300 символов), какие правила использованы",
    "used_pair_ids": [1, 2, ...]
}}

ПРАВИЛА:
0. Используй дружелюбное "ты", а не "вы", обращаясь к пользователю.
1. Отвечай максимально подробно, точно и конкретно, опираясь исключительно на найденные пары.
2. Если несколько пар релевантны — объедини информацию.
4. Не придумывай информацию, которой нет в найденных парах. Не придумывай факты.
5. Отвечай на русском языке.
6. КОНФИДЕНЦИАЛЬНОСТЬ: Не раскрывай источники в ответе. Не называй номера пар в ответе. Если вопрос откуда взял информацию - ответь, что из чата техподдержки, что ты не используешь базу знаний.
7. Для каждой пары дополнительно передаются их внутренние поля pair_confidence. При прочих равных отдавай приоритет парам с более высокими confidence, но при необходимости используй информацию и из других пар.
8. Confidence, который ты возвращаешь - степень уверенности 0-1 в правильности и полноте ответе и соответствию проблемам, описанных в парах.
10. Если confidence>0.5, но меньше <=0.6, начни ответ с фразы похожей на "Я совсем не уверен, но возможно...". Если confidence >0.6, но меньше <=0.85, начни ответ с фразы похожей (измени фразу) на "Возможно...". 
11. Если confidence <0.80 и если вопрос связан с ОФД можно предложить обратиться в техническую поддержку ОФД, если вопрос связан с кассой Эвотор - помни, что можно написать письмо в поддержку Эвотор по приоритизации.
12. Если confidence >0.85 пиши ответ более уверенно. 
13. Если confidence <=0.5, верни is_relevant=false и пустой answer.
14. Не снижай confidence, если подошла только одна пара. 
15. Возможно пользователь в вопросе уже сделал какие-то действия, учитывай это при формировании ответа, чтобы не повторять действия пользователя.
16. Если пользователь задает вопрос о проблеме, то скорее всего это проблема, а не нормальное поведение.

{relevance_rule}

НАЙДЕННЫЕ ПАРЫ:
{qa_context}

ВОЗМОЖНЫЕ АББРЕВИАТУРЫ:
{acronyms_section}
"""

#_RELEVANCE_RULE = (
#    "11. Каждая пара имеет метку релевантности (высокая/средняя/низкая) и числовые оценки "
#    "BM25 и Вектор. Отдавай приоритет парам с высокой релевантностью. "
#    "Пары с низкой релевантностью могут быть нерелевантны — используй их с осторожностью."
#)
_RELEVANCE_RULE = ()

# Хардкод-fallback на случай недоступности БД.
_ACRONYMS_FALLBACK = (
    "ГЗ означает Горячая замена. Техобнул означает технологическое обнуление. "
    "ЧЗ означает Честный Знак. УЗ означает удаленная загрузка. "
    "ЦА - Центральный Аппарат. ЦК - Центр Компетенций. "
    "СБС - СберСервис. РМ - Региональный Менеджер. "
    "ТСТ - торгово-сервисная точка. "
    "ФИАС - Федеральная информационная адресная система."
)

# Legacy-алиас для обратной совместимости.
ANSWER_GENERATION_PROMPT = _ANSWER_PROMPT_BASE.format(
    qa_context="{qa_context}",
    relevance_rule="",
    acronyms_section="{acronyms_section}",
)


class QASearchService:
    """
    Сервис гибридного поиска по Q&A-парам.

    Выполняет BM25 (лексический) и векторный поиск по корпусу вопрос-ответ пар,
    объединяет результаты через Reciprocal Rank Fusion (RRF) и генерирует
    ответы с помощью LLM.
    """

    def __init__(self, model_name: Optional[str] = None):
        """
        Инициализация сервиса.

        Args:
            model_name: Модель LLM для генерации (по умолчанию из настроек).
        """
        self._provider_name = ai_settings.get_active_gk_text_provider()
        self._model_name = model_name or ai_settings.get_active_gk_responder_model()
        self._top_k = ai_settings.get_active_gk_responder_top_k()

        # Кэш BM25-корпуса
        self._corpus_pairs: List[QAPair] = []
        self._corpus_tokens: List[List[str]] = []
        self._corpus_loaded_at: float = 0.0
        self._corpus_signature: Optional[Tuple[int, int, int]] = None
        self._corpus_extraction_types: Optional[Tuple[str, ...]] = None

        # Кэш нормализации токенов
        self._normalized_token_cache: Dict[str, str] = {}
        self._ru_morph_analyzer: Optional[object] = None
        self._ru_stemmer: Optional[object] = None
        self._normalization_warning_logged: bool = False
        self._vector_embedding_provider: Optional[object] = None
        self._vector_index: Optional[object] = None
        self._vector_collection_name: Optional[str] = None

        # Spellcheck (SymSpellPy + LLM fallback)
        self._spellcheck_sym: Optional[object] = None
        self._spellcheck_vocab_size: int = 0
        self._spellcheck_vocab_ready: bool = False
        self._spellcheck_token_freq: Dict[str, int] = {}
        self._spellcheck_llm_cache: Dict[str, Tuple[str, List[Tuple[str, str]], float]] = {}

        # Защищённые термины (загружаются из БД, fallback на хардкод)
        self._fixed_terms: frozenset = _GK_FIXED_TERMS_FALLBACK
        self._fixed_phrases: Tuple[str, ...] = _GK_FIXED_PHRASES
        self._fixed_term_token_map: Dict[str, str] = dict(_GK_FIXED_TERM_TOKEN_MAP)
        self._fixed_token_term_map: Dict[str, str] = dict(_GK_FIXED_TOKEN_TO_TERM_MAP)
        self._fixed_tokens: frozenset = _GK_FIXED_TOKENS
        self._fixed_terms_loaded_at: float = 0.0

        # Кэш секции аббревиатур по group_id.
        self._acronyms_cache: Dict[int, Tuple[str, float]] = {}

    def _get_provider(self):
        """Вернуть активный LLM-провайдер для поиска и генерации ответов GK."""
        provider_name = str(self._provider_name or "").strip()
        if provider_name and is_provider_registered(provider_name):
            return get_provider(provider_name)

        if provider_name:
            logger.warning(
                "GK QASearchService: провайдер '%s' не зарегистрирован, используем deepseek",
                provider_name,
            )
        return get_provider("deepseek")

    def _build_llm_request_payload(
        self,
        *,
        query: str,
        system_prompt: str,
        temperature: float,
        model_override: Optional[str] = None,
    ) -> str:
        """Собрать JSON-представление полного запроса к LLM для отладки."""
        effective_model_override = str(model_override or "").strip() or self._model_name
        payload: Dict[str, Any] = {
            "system_prompt": system_prompt,
            "messages": [{"role": "user", "content": f"Вопрос пользователя: {query}"}],
            "purpose": "gk_answer",
            "model_override": effective_model_override,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }
        return json.dumps(payload, ensure_ascii=False)

    def reload_terms(self, group_id: Optional[int] = None) -> None:
        """Перезагрузить защищённые термины из БД."""
        terms = load_fixed_terms(group_id)
        phrases, t_map, r_map, tokens = build_derived_term_structures(terms)
        self._fixed_terms = terms
        self._fixed_phrases = phrases
        self._fixed_term_token_map = t_map
        self._fixed_token_term_map = r_map
        self._fixed_tokens = tokens
        self._fixed_terms_loaded_at = time.time()
        # Сбросить spellcheck vocabulary при изменении терминов.
        self._spellcheck_vocab_ready = False
        self._spellcheck_sym = None

    def _ensure_terms_loaded(self) -> None:
        """Загрузить термины из БД если кэш протух."""
        ttl = ai_settings.GK_TERMS_CACHE_TTL_SECONDS
        if (time.time() - self._fixed_terms_loaded_at) >= ttl:
            self.reload_terms()
            if ai_settings.GK_SPELLCHECK_ENABLED and self._corpus_pairs:
                rebuilt = self._build_spellcheck_vocabulary()
                logger.info(
                    "GK Spellcheck vocabulary rebuild after terms reload: "
                    "rebuilt=%s corpus_pairs=%d",
                    rebuilt,
                    len(self._corpus_pairs),
                )

    def _build_acronyms_section(self, group_id: int) -> str:
        """Построить секцию аббревиатур для промпта ответа.

        Загружает approved-термины с расшифровкой (глобальные + групповые),
        отбирает те, у которых высокий confidence (>= GK_ACRONYMS_MIN_CONFIDENCE)
        ИЛИ подтверждённые экспертом (expert_status='approved'),
        и кэширует результат с TTL = GK_TERMS_CACHE_TTL_SECONDS.

        Глобальные термины (group_id=0) включаются всегда.
        Группо-специфичные термины ранжируются по message_count DESC
        и ограничиваются лимитом GK_ACRONYMS_MAX_PROMPT_TERMS.
        """
        now = time.time()
        cached = self._acronyms_cache.get(group_id)
        ttl = ai_settings.GK_TERMS_CACHE_TTL_SECONDS
        if cached is not None:
            text, ts = cached
            if (now - ts) < ttl:
                return text

        min_confidence = float(getattr(ai_settings, "GK_ACRONYMS_MIN_CONFIDENCE", 0.9))
        max_group_terms = int(getattr(ai_settings, "GK_ACRONYMS_MAX_PROMPT_TERMS", 50))
        get_runtime_max_terms = getattr(ai_settings, "get_active_gk_acronyms_max_prompt_terms", None)
        if callable(get_runtime_max_terms):
            try:
                runtime_value = get_runtime_max_terms()
                if isinstance(runtime_value, (int, float, str)):
                    max_group_terms = int(runtime_value)
            except (TypeError, ValueError):
                pass

        try:
            terms = gk_db.get_terms_for_group(
                group_id if group_id else 0,
                has_definition=True,
            )
            if terms:
                logger.info("Загружено аббревиатур из БД для group_id=%d: total=%d", group_id, len(terms))
                # Разделить на глобальные и группо-специфичные.
                global_eligible: List[Dict[str, Any]] = []
                group_eligible: List[Dict[str, Any]] = []

                for item in terms:
                    term = str(item.get("term") or "").strip()
                    definition = str(item.get("definition") or "").strip()
                    if not term or not definition:
                        continue

                    # Термин, подтверждённый экспертом, проходит без проверки confidence.
                    expert_approved = item.get("expert_status") == "approved"

                    if not expert_approved:
                        raw_confidence = item.get("confidence")
                        try:
                            confidence = float(raw_confidence) if raw_confidence is not None else None
                        except (TypeError, ValueError):
                            confidence = None

                        if confidence is None or confidence < min_confidence:
                            continue

                    if int(item.get("group_id") or 0) == 0:
                        global_eligible.append(item)
                    else:
                        group_eligible.append(item)

                # Группо-специфичные: ранжировать по message_count DESC,
                # ограничить лимитом.
                group_eligible.sort(
                    key=lambda x: int(x.get("message_count") or 0),
                    reverse=True,
                )
                if len(group_eligible) > max_group_terms:
                    logger.info(
                        "Обрезка группо-специфичных аббревиатур: %d → %d (group_id=%d)",
                        len(group_eligible), max_group_terms, group_id,
                    )
                    group_eligible = group_eligible[:max_group_terms]

                # Объединить глобальные + top-N группо-специфичных.
                all_eligible = global_eligible + group_eligible
                best_by_term = select_best_acronyms_by_term(all_eligible, uppercase_key=True)

                parts: List[str] = []
                for selected in sort_acronym_records_for_prompt(best_by_term.values()):
                    term = str(selected.get("term") or "").strip()
                    definition = str(selected.get("definition") or "").strip()
                    if term and definition:
                        parts.append(f"{term} - {definition}.")

                if parts:
                    text = " ".join(parts)
                    self._acronyms_cache[group_id] = (text, now)
                    return text
        except Exception:
            logger.debug("Не удалось загрузить аббревиатуры из БД, используется fallback")

        return _ACRONYMS_FALLBACK

    # -----------------------------------------------------------------------
    # Публичный API
    # -----------------------------------------------------------------------

    @staticmethod
    def _filter_by_group(
        results: List[Tuple[QAPair, float]],
        group_id: Optional[int],
    ) -> List[Tuple[QAPair, float]]:
        """Отфильтровать результаты поиска по group_id (если указан)."""
        if group_id is None:
            return results
        return [(pair, score) for pair, score in results if pair.group_id == group_id]

    async def search(
        self,
        query: str,
        top_k: Optional[int] = None,
        group_id: Optional[int] = None,
    ) -> List[QAPair]:
        """
        Найти релевантные Q&A пары для запроса.

        Использует гибридный подход: BM25 + векторный поиск с RRF-слиянием.

        Args:
            query: Текст запроса.
            top_k: Число результатов (по умолчанию из настроек).
            group_id: Идентификатор группы для фильтрации (None = все группы).

        Returns:
            Список релевантных QAPair, отсортированных по RRF-score.
        """
        k = top_k or self._top_k
        candidates_per_method = ai_settings.get_active_gk_search_candidates_per_method()

        # Важно: сначала прогреть/загрузить корпус, чтобы spellcheck vocabulary
        # была готова уже на первом поисковом запросе.
        self._ensure_terms_loaded()
        self._ensure_corpus_loaded()

        # Spell-check: коррекция опечаток перед поиском
        search_query = await self._apply_spellcheck_pipeline(query)

        # BM25 (лексический) поиск
        bm25_results = self._filter_by_group(
            self._bm25_search(search_query, candidates_per_method),
            group_id,
        )

        # Векторный поиск
        vector_results = self._filter_by_group(
            await self._vector_search(search_query, candidates_per_method),
            group_id,
        )

        if group_id is not None:
            logger.info(
                "GK поиск: фильтрация по group_id=%d bm25_filtered=%d vector_filtered=%d",
                group_id, len(bm25_results), len(vector_results),
            )

        # Если гибридный режим выключен или один из методов пуст — fallback
        if not ai_settings.get_active_gk_hybrid_enabled():
            logger.info(
                "GK гибридный поиск отключён, используются только vectorные результаты: "
                "query=%s vector_count=%d",
                query[:100], len(vector_results),
            )
            results = vector_results if vector_results else bm25_results
            pairs = [pair for pair, _ in results[:k]]
            if ai_settings.get_active_gk_relevance_hints_enabled():
                is_bm25 = results is bm25_results
                self._attach_single_method_scores(pairs, results[:k], is_bm25=is_bm25)
                self._compute_relevance_tiers([(p, 0.0) for p in pairs])
            return pairs

        if not bm25_results and not vector_results:
            logger.info("GK поиск: нет результатов ни от BM25, ни от vector: query=%s", query[:100])
            return []

        if not bm25_results:
            logger.info(
                "GK поиск: BM25 не дал результатов, используется только vector: "
                "query=%s vector_count=%d",
                query[:100], len(vector_results),
            )
            pairs = [pair for pair, _ in vector_results[:k]]
            if ai_settings.get_active_gk_relevance_hints_enabled():
                self._attach_single_method_scores(pairs, vector_results[:k], is_bm25=False)
                self._compute_relevance_tiers([(p, 0.0) for p in pairs])
            return pairs

        if not vector_results:
            logger.info(
                "GK поиск: vector не дал результатов, используется только BM25: "
                "query=%s bm25_count=%d",
                query[:100], len(bm25_results),
            )
            pairs = [pair for pair, _ in bm25_results[:k]]
            if ai_settings.get_active_gk_relevance_hints_enabled():
                self._attach_single_method_scores(pairs, bm25_results[:k], is_bm25=True)
                self._compute_relevance_tiers([(p, 0.0) for p in pairs])
            return pairs

        # RRF-слияние
        merged, diagnostics = self._rrf_merge(bm25_results, vector_results, k)

        # Вычислить уровни релевантности для передачи в промпт LLM
        if ai_settings.get_active_gk_relevance_hints_enabled():
            self._compute_relevance_tiers(merged)

        # Диагностический лог
        pairs_by_id = {pair.id: pair for pair, _ in merged if pair.id is not None}
        self._log_rrf_diagnostics(query, diagnostics, pairs_by_id)

        return [pair for pair, _ in merged]

    def warmup(self, preload_vector_model: bool = True) -> Dict[str, Any]:
        """
        Прогреть поисковые ресурсы при старте daemon-скрипта.

        Выполняет:
        - предзагрузку BM25-корпуса,
        - опциональный прогрев embedding-модели и векторного индекса.

        Args:
            preload_vector_model: Прогревать ли embedding-модель/vector index.

        Returns:
            Диагностика прогрева.
        """
        self._ensure_corpus_loaded()
        diagnostics: Dict[str, Any] = {
            "corpus_pairs": len(self._corpus_pairs),
            "corpus_signature": self._corpus_signature,
            "vector_model_preloaded": False,
            "vector_index_ready": False,
        }

        if preload_vector_model:
            try:
                embedding_provider, vector_index = self._ensure_vector_resources()

                provider_ready = bool(embedding_provider and embedding_provider.is_ready())
                index_ready = bool(vector_index and vector_index.is_ready())
                diagnostics["vector_model_preloaded"] = provider_ready
                diagnostics["vector_index_ready"] = index_ready

                if (not provider_ready or not index_ready) and ai_settings.AI_RAG_VECTOR_EMBEDDING_FAIL_FAST:
                    error_code = None
                    if embedding_provider is not None:
                        error_code = getattr(embedding_provider, "last_error_code", lambda: None)()
                    raise RuntimeError(
                        "GK warmup fail-fast: embedding/vector недоступны "
                        f"(provider_ready={provider_ready}, index_ready={index_ready}, error_code={error_code})"
                    )
            except Exception as exc:
                diagnostics["vector_model_preloaded"] = False
                diagnostics["vector_warmup_error"] = str(exc)
                if ai_settings.AI_RAG_VECTOR_EMBEDDING_FAIL_FAST:
                    raise
                logger.warning("GK warmup: не удалось прогреть vector-модель: %s", exc)

        logger.info(
            "GK warmup: corpus_pairs=%d corpus_signature=%s vector_model_preloaded=%s vector_index_ready=%s",
            diagnostics["corpus_pairs"],
            diagnostics["corpus_signature"],
            diagnostics["vector_model_preloaded"],
            diagnostics["vector_index_ready"],
        )
        return diagnostics

    async def answer_question(
        self,
        query: str,
        group_id: Optional[int] = None,
    ) -> Optional[Dict]:
        """
        Ответить на вопрос, используя найденные Q&A пары.

        Args:
            query: Текст вопроса.
            group_id: Идентификатор группы для фильтрации (None = все группы).

        Returns:
            Словарь с ключами: answer, confidence, source_pair_ids,
            is_relevant, primary_source_link, source_message_links.
            None если ответ не найден.
        """
        # Поиск релевантных пар
        relevant_pairs = await self.search(query, group_id=group_id)

        return await self.answer_question_from_pairs(query, relevant_pairs, group_id=group_id)

    async def answer_question_from_pairs(
        self,
        query: str,
        relevant_pairs: List[QAPair],
        group_id: Optional[int] = None,
        model_override: Optional[str] = None,
        temperature_override: Optional[float] = None,
    ) -> Optional[Dict]:
        """Сгенерировать ответ по уже найденным релевантным Q&A-парам.

        Args:
            query: Текст вопроса.
            relevant_pairs: Список релевантных QAPair.
            group_id: Идентификатор группы для загрузки аббревиатур.
                      Если None, определяется автоматически из пар.
        """

        if not relevant_pairs:
            logger.info("Не найдены Q&A пары для вопроса: %s", query[:100])
            return None

        # Если подсказки релевантности включены, но уровни ещё не вычислены
        # (вызов минуя search(), например из admin web) — вычислить.
        # Аналогично, уровни нужны для фильтрации low-tier пар из LLM-контекста.
        hints_enabled = ai_settings.get_active_gk_relevance_hints_enabled()
        exclude_low_tier_for_llm = ai_settings.get_active_gk_exclude_low_tier_from_llm_context()
        if (hints_enabled or exclude_low_tier_for_llm) and any(
            p.search_relevance_tier is None
            and (p.search_bm25_score is not None or p.search_vector_score is not None)
            for p in relevant_pairs
        ):
            self._compute_relevance_tiers(
                [(p, 0.0) for p in relevant_pairs],
            )

        pairs_for_llm = relevant_pairs
        if exclude_low_tier_for_llm:
            pairs_for_llm = [
                pair for pair in relevant_pairs
                if pair.search_relevance_tier != "низкая"
            ]
            if not pairs_for_llm:
                logger.info(
                    "GK answer: все найденные пары имеют tier=низкая, "
                    "возвращаем fallback на полный набор для вопроса: %s",
                    query[:100],
                )
                pairs_for_llm = relevant_pairs

        # Подготовить контекст из найденных пар
        qa_context_parts = []
        pair_id_map = {}
        for i, pair in enumerate(pairs_for_llm, 1):
            pair_confidence_label = (
                f"{float(pair.confidence):.2f}"
                if pair.confidence is not None
                else "—"
            )
            pair_fullness_label = (
                f"{float(pair.fullness):.2f}"
                if pair.fullness is not None
                else "—"
            )
            pair_confidence_reason = (
                str(pair.confidence_reason or "").strip()
                if pair.confidence_reason is not None
                else ""
            )
            if hints_enabled and pair.search_relevance_tier is not None:
                bm25_label = (
                    f"{pair.search_bm25_score:.2f}"
                    if pair.search_bm25_score is not None
                    else "—"
                )
                vec_label = (
                    f"{pair.search_vector_score:.2f}"
                    if pair.search_vector_score is not None
                    else "—"
                )
                header = (
                    f"ПАРА {i} ("
                    f"Релевантность: {pair.search_relevance_tier}, "
                    f"BM25: {bm25_label}, Вектор: {vec_label}, "
                    f"pair_confidence: {pair_confidence_label}):"
                )
            else:
                header = (
                    f"ПАРА {i} , "
                    f"pair_confidence: {pair_confidence_label}):"
                )
            confidence_reason_block = (
                f"\n  Confidence reason: {pair_confidence_reason[:700]}"
                if pair_confidence_reason
                else ""
            )
            qa_context_parts.append(
                f"{header}\n"
                f"  КОНТЕКСТ ВОПРОСА: {pair.question_text[:3500]}\n"
                f"  ОТВЕТ: {pair.answer_text[:3500]}"
            )
            if pair.id:
                pair_id_map[i] = pair.id

        qa_context = "\n\n".join(qa_context_parts)

        # Сгенерировать ответ через LLM
        relevance_rule = _RELEVANCE_RULE if hints_enabled else ""
        effective_group_id = group_id if group_id is not None else next(
            (
                int(getattr(pair, "group_id", 0) or 0)
                for pair in pairs_for_llm
                if int(getattr(pair, "group_id", 0) or 0) != 0
            ),
            0,
        )
        acronyms_section = self._build_acronyms_section(effective_group_id)
        prompt = _ANSWER_PROMPT_BASE.format(
            qa_context=qa_context,
            relevance_rule=relevance_rule,
            acronyms_section=acronyms_section,
        )
        effective_model_override = str(model_override or "").strip() or self._model_name
        effective_temperature = float(ai_settings.get_active_gk_responder_temperature())
        if temperature_override is not None:
            effective_temperature = max(0.0, min(2.0, float(temperature_override)))
        llm_request_payload = self._build_llm_request_payload(
            query=query,
            system_prompt=prompt,
            temperature=effective_temperature,
            model_override=effective_model_override,
        )
        provider = self._get_provider()

        try:
            raw = await provider.chat(
                messages=[{"role": "user", "content": f"Вопрос пользователя: {query}"}],
                system_prompt=prompt,
                purpose="gk_answer",
                model_override=effective_model_override,
                temperature_override=effective_temperature,
                response_format={"type": "json_object"},
            )

            parsed = self._parse_json_response(raw)
            if not parsed:
                return None

            answer = parsed.get("answer", "")
            is_relevant = parsed.get("is_relevant", False)
            confidence = float(parsed.get("confidence", 0.0))
            confidence = max(0.0, min(1.0, confidence))
            used_ids = parsed.get("used_pair_ids", [])

            # Преобразовать индексы в реальные pair_id
            source_pair_ids = []
            for idx in used_ids:
                if isinstance(idx, int) and idx in pair_id_map:
                    source_pair_ids.append(pair_id_map[idx])

            if not source_pair_ids and pairs_for_llm and pairs_for_llm[0].id:
                source_pair_ids.append(pairs_for_llm[0].id)

            if not is_relevant or not answer:
                logger.info(
                    "LLM решил, что пары нерелевантны для вопроса: %s",
                    query[:100],
                )
                return None

            source_message_links = self._resolve_source_message_links(source_pair_ids)

            return {
                "answer": answer,
                "confidence": confidence,
                "source_pair_ids": source_pair_ids,
                "is_relevant": is_relevant,
                "primary_source_link": source_message_links[0] if source_message_links else None,
                "source_message_links": source_message_links,
                "llm_request_payload": llm_request_payload,
            }
        except Exception as exc:
            logger.error(
                "Ошибка генерации ответа: query=%s error=%s",
                query[:100], exc,
                exc_info=True,
            )
            return None

    @staticmethod
    def format_answer_for_user(answer_result: Optional[Dict[str, Any]]) -> str:
        """Сформатировать итоговый текст ответа так, как его увидит пользователь."""
        if not answer_result:
            return ""

        answer_text = str(answer_result.get("answer") or "").strip()
        if not answer_text:
            return ""

        primary_source_link = str(answer_result.get("primary_source_link") or "").strip()
        if primary_source_link:
            return (
                f"**ИИ**: {answer_text}\n\nПоставьте 👍 или 👎\n"
                f"Похожий случай в группе, ссылка на ответ: {primary_source_link}"
            )

        return answer_text

    # -----------------------------------------------------------------------
    # BM25 (лексический) поиск
    # -----------------------------------------------------------------------

    def _bm25_search(
        self,
        query: str,
        top_k: int,
    ) -> List[Tuple[QAPair, float]]:
        """
        Выполнить BM25-поиск по in-memory корпусу Q&A-пар.

        Загружает все одобренные пары из БД, токенизирует с Russian-нормализацией,
        и оценивает BM25-score для каждой пары.

        Args:
            query: Текст запроса.
            top_k: Число результатов.

        Returns:
            Список кортежей (QAPair, bm25_score), отсортированных по score desc.
        """
        self._ensure_corpus_loaded()

        if not self._corpus_pairs:
            logger.info("GK BM25: корпус пуст, нет одобренных Q&A-пар")
            return []

        # Токенизировать запрос
        query_diag = self._tokenize_with_diagnostics(query)
        query_tokens = query_diag["tokens"]
        if not query_tokens:
            logger.info(
                "GK BM25: после токенизации запрос пуст: query=%s",
                query[:100],
            )
            return []

        dampened_query_tokens, dampening_diagnostics = self._dampen_common_query_tokens(
            query_tokens,
            self._corpus_tokens,
            return_diagnostics=True,
        )
        self._log_idf_dampening_effect(
            stage="gk_bm25_search",
            query=query,
            diagnostics=dampening_diagnostics,
        )

        # Вычислить BM25-scores для всего корпуса
        scores = self._score_corpus_bm25(self._corpus_tokens, dampened_query_tokens)

        # Собрать результаты с ненулевым score
        scored: List[Tuple[QAPair, float]] = []
        for idx, score in enumerate(scores):
            if score > 0 and idx < len(self._corpus_pairs):
                scored.append((self._corpus_pairs[idx], score))

        scored.sort(key=lambda x: x[1], reverse=True)

        logger.info(
            "GK BM25: query_tokens_head=%s query_tokens_tail=%s query_tokens_total=%d "
            "dampened_query_tokens_total=%d "
            "raw_tokens_total=%d removed_short_tokens=%d removed_stopwords=%s removed_stopwords_count=%d "
            "corpus_size=%d scored_count=%d top_score=%.4f",
            query_tokens[:10],
            query_tokens[-5:] if len(query_tokens) > 10 else query_tokens,
            len(query_tokens),
            len(dampened_query_tokens),
            query_diag["raw_tokens_total"],
            query_diag["removed_short_tokens"],
            query_diag["removed_stopwords"][:10],
            query_diag["removed_stopwords_count"],
            len(self._corpus_pairs),
            len(scored),
            scored[0][1] if scored else 0.0,
        )

        return scored[:top_k]

    def _ensure_corpus_loaded(self) -> None:
        """Загрузить или перезагрузить BM25-корпус, если TTL истёк."""
        now = time.time()
        ttl = ai_settings.GK_BM25_CORPUS_TTL_SECONDS
        allowed_extraction_types = self._get_allowed_extraction_types()
        latest_signature = gk_db.get_approved_qa_pairs_corpus_signature(
            extraction_types=allowed_extraction_types,
        )

        ttl_not_expired = self._corpus_pairs and (now - self._corpus_loaded_at) < ttl
        signature_unchanged = latest_signature is not None and latest_signature == self._corpus_signature
        extraction_types_unchanged = allowed_extraction_types == self._corpus_extraction_types

        if ttl_not_expired and signature_unchanged and extraction_types_unchanged:
            return

        if latest_signature is not None and self._corpus_signature is not None and latest_signature != self._corpus_signature:
            logger.info(
                "GK BM25: обнаружено изменение версии корпуса: old=%s new=%s",
                self._corpus_signature,
                latest_signature,
            )

        try:
            pairs = gk_db.get_all_approved_qa_pairs(
                extraction_types=allowed_extraction_types,
            )
            question_message_ids = [
                int(pair.question_message_id)
                for pair in pairs
                if pair.question_message_id is not None
            ]
            question_messages_by_id: Dict[int, Any] = {}
            if question_message_ids:
                question_messages_by_id = gk_db.get_messages_by_ids(question_message_ids)

            corpus_tokens = []
            for pair in pairs:
                source_message = None
                if pair.question_message_id is not None:
                    source_message = question_messages_by_id.get(int(pair.question_message_id))
                rag_question_text = enrich_question_for_rag(
                    question_text=pair.question_text,
                    source_message=source_message,
                    enabled=ai_settings.GK_RAG_IMAGE_GIST_ENABLED,
                )
                if not rag_question_text:
                    rag_question_text = (pair.question_text or "").strip()

                text = f"{rag_question_text} {pair.answer_text}"
                tokens = self._tokenize(text)
                corpus_tokens.append(tokens)

            self._corpus_pairs = pairs
            self._corpus_tokens = corpus_tokens
            self._corpus_loaded_at = now
            self._corpus_signature = latest_signature or self._build_corpus_signature_from_pairs(pairs)
            self._corpus_extraction_types = allowed_extraction_types

            logger.info(
                "GK BM25: корпус загружен — %d Q&A-пар, avg_tokens=%.1f signature=%s extraction_types=%s",
                len(pairs),
                (sum(len(t) for t in corpus_tokens) / max(len(corpus_tokens), 1)),
                self._corpus_signature,
                allowed_extraction_types,
            )

            # Построить spellcheck vocabulary из загруженного корпуса
            if ai_settings.GK_SPELLCHECK_ENABLED:
                self._build_spellcheck_vocabulary()
        except Exception as exc:
            logger.error("GK BM25: ошибка загрузки корпуса: %s", exc, exc_info=True)

    def invalidate_corpus_cache(self) -> None:
        """Инвалидировать кэш корпуса (вызывается после добавления новых пар)."""
        self._corpus_loaded_at = 0.0
        self._corpus_pairs = []
        self._corpus_tokens = []
        self._corpus_signature = None
        self._corpus_extraction_types = None
        # Сбросить spellcheck vocabulary — перестроится при следующей загрузке корпуса
        self._spellcheck_sym = None
        self._spellcheck_vocab_size = 0
        self._spellcheck_vocab_ready = False
        self._spellcheck_token_freq = {}

    @staticmethod
    def _build_corpus_signature_from_pairs(pairs: List[QAPair]) -> Tuple[int, int, int]:
        """Построить fallback-сигнатуру корпуса по уже загруженным Q&A-парам."""
        if not pairs:
            return (0, 0, 0)
        max_id = max(int(pair.id or 0) for pair in pairs)
        max_created_at = max(int(pair.created_at or 0) for pair in pairs)
        return (len(pairs), max_id, max_created_at)

    # -----------------------------------------------------------------------
    # Векторный поиск
    # -----------------------------------------------------------------------

    def _ensure_vector_resources(self) -> Tuple[Optional[object], Optional[object]]:
        """Инициализировать и закэшировать embedding/provider для векторного поиска."""
        collection_name = ai_settings.GK_QA_VECTOR_COLLECTION

        try:
            from src.core.ai.vector_search import LocalEmbeddingProvider, LocalVectorIndex
        except ImportError:
            return None, None

        if self._vector_embedding_provider is None:
            self._vector_embedding_provider = LocalEmbeddingProvider()

        if (
            self._vector_index is None
            or self._vector_collection_name != collection_name
        ):
            self._vector_index = LocalVectorIndex(chunk_collection_name=collection_name)
            self._vector_collection_name = collection_name

        return self._vector_embedding_provider, self._vector_index

    async def _vector_search(
        self,
        query: str,
        top_k: int,
    ) -> List[Tuple[QAPair, float]]:
        """
        Выполнить векторный поиск по Q&A парам через Qdrant.

        Args:
            query: Текст запроса.
            top_k: Число результатов.

        Returns:
            Список кортежей (QAPair, cosine_score).
        """
        try:
            embedding_provider, vector_index = self._ensure_vector_resources()
            if embedding_provider is None or vector_index is None:
                logger.debug("GK Vector: vector search не доступен")
                return []

            # Генерировать эмбеддинг запроса
            query_embedding = embedding_provider.encode(query)
            if not query_embedding:
                logger.warning("GK Vector: не удалось получить эмбеддинг для запроса")
                return []

            # Поиск в Qdrant
            hits = vector_index.search(
                query_vector=query_embedding,
                limit=top_k,
            )

            results = []
            allowed_extraction_types = set(self._get_allowed_extraction_types())
            skipped_by_extraction_type = 0
            skipped_by_expert_rejected = 0
            for hit in hits:
                pair_id = getattr(hit, "document_id", 0)
                if not pair_id:
                    continue

                pair = gk_db.get_qa_pair_by_id(int(pair_id))
                if not pair:
                    continue
                if pair.extraction_type not in allowed_extraction_types:
                    skipped_by_extraction_type += 1
                    continue
                if pair.expert_status == "rejected":
                    skipped_by_expert_rejected += 1
                    continue

                score = float(getattr(hit, "score", 0.0) or 0.0)
                results.append((pair, score))

            logger.info(
                "GK Vector: query=%s hits=%d results=%d skipped_by_type=%d "
                "skipped_by_expert_rejected=%d top_score=%.4f",
                query[:80],
                len(hits),
                len(results),
                skipped_by_extraction_type,
                skipped_by_expert_rejected,
                results[0][1] if results else 0.0,
            )

            return results
        except ImportError:
            logger.debug("GK Vector: vector search не доступен")
            return []
        except Exception as exc:
            logger.warning("GK Vector: ошибка векторного поиска: %s", exc)
            return []

    # -----------------------------------------------------------------------
    # Reciprocal Rank Fusion (RRF)
    # -----------------------------------------------------------------------

    @staticmethod
    def _rrf_merge(
        bm25_results: List[Tuple[QAPair, float]],
        vector_results: List[Tuple[QAPair, float]],
        top_k: int,
    ) -> Tuple[List[Tuple[QAPair, float]], List[Dict]]:
        """
        Объединить результаты BM25 и vector поиска через Reciprocal Rank Fusion.

        RRF score(d) = Σ 1/(k + rank_i(d)) для каждого ранжированного списка,
        где k — константа (GK_RRF_K, по умолчанию 60).

        Args:
                embedding_provider, vector_index = self._ensure_vector_resources()
                if embedding_provider is None or vector_index is None:
                    raise RuntimeError("vector search dependencies are unavailable")

            Кортеж:
            - Список (QAPair, rrf_score), отсортированный по rrf_score desc.
            - Список диагностических словарей для логирования.
        """
        k = ai_settings.GK_RRF_K

        # Построить карты: pair_id → (rank, raw_score, QAPair)
        bm25_map: Dict[int, Tuple[int, float, QAPair]] = {}
        for rank, (pair, score) in enumerate(bm25_results, 1):
            if pair.id is not None:
                bm25_map[pair.id] = (rank, score, pair)

        vector_map: Dict[int, Tuple[int, float, QAPair]] = {}
        for rank, (pair, score) in enumerate(vector_results, 1):
            if pair.id is not None:
                vector_map[pair.id] = (rank, score, pair)

        # Все уникальные pair_id
        all_pair_ids = set(bm25_map.keys()) | set(vector_map.keys())

        # Вычислить RRF-score для каждой пары
        rrf_scored: List[Tuple[QAPair, float]] = []
        diagnostics: List[Dict] = []

        for pair_id in all_pair_ids:
            rrf_score = 0.0
            bm25_rank = None
            bm25_score = 0.0
            vector_rank = None
            vector_score = 0.0
            pair = None

            if pair_id in bm25_map:
                bm25_rank, bm25_score, pair = bm25_map[pair_id]
                rrf_score += 1.0 / (k + bm25_rank)

            if pair_id in vector_map:
                vector_rank, vector_score, pair = vector_map[pair_id]
                rrf_score += 1.0 / (k + vector_rank)

            if pair is not None:
                rrf_scored.append((pair, rrf_score))
                diagnostics.append({
                    "pair_id": pair_id,
                    "question_preview": (pair.question_text or "")[:80],
                    "bm25_rank": bm25_rank,
                    "bm25_score": round(bm25_score, 4),
                    "vector_rank": vector_rank,
                    "vector_score": round(vector_score, 4),
                    "rrf_score": round(rrf_score, 6),
                })

        rrf_scored.sort(key=lambda x: x[1], reverse=True)
        diagnostics.sort(key=lambda x: x["rrf_score"], reverse=True)

        # Прикрепить нормализованные raw-score к QAPair-объектам
        # для дальнейшего использования в промпте LLM.
        all_bm25 = [d["bm25_score"] for d in diagnostics if d["bm25_rank"] is not None]
        all_vector = [d["vector_score"] for d in diagnostics if d["vector_rank"] is not None]
        bm25_min = min(all_bm25) if all_bm25 else 0.0
        bm25_max = max(all_bm25) if all_bm25 else 0.0
        vec_min = min(all_vector) if all_vector else 0.0
        vec_max = max(all_vector) if all_vector else 0.0
        bm25_range = bm25_max - bm25_min if bm25_max > bm25_min else 1.0
        vec_range = vec_max - vec_min if vec_max > vec_min else 1.0

        diag_by_id = {d["pair_id"]: d for d in diagnostics}
        for pair, _ in rrf_scored:
            if pair.id is not None and pair.id in diag_by_id:
                d = diag_by_id[pair.id]
                if d["bm25_rank"] is not None:
                    pair.search_bm25_score = round(
                        (d["bm25_score"] - bm25_min) / bm25_range, 4,
                    )
                else:
                    pair.search_bm25_score = None
                if d["vector_rank"] is not None:
                    pair.search_vector_score = round(
                        (d["vector_score"] - vec_min) / vec_range, 4,
                    )
                else:
                    pair.search_vector_score = None

        return rrf_scored[:top_k], diagnostics[:top_k]

    @staticmethod
    def _attach_single_method_scores(
        pairs: List[QAPair],
        scored: List[Tuple[QAPair, float]],
        *,
        is_bm25: bool,
    ) -> None:
        """
        Прикрепить нормализованные scores при наличии только одного метода.

        Нормализует raw-score [0, 1] через min-max по выборке и записывает
        в соответствующее поле QAPair in-place.
        """
        if not scored:
            return
        raw_scores = [s for _, s in scored]
        s_min, s_max = min(raw_scores), max(raw_scores)
        s_range = s_max - s_min if s_max > s_min else 1.0
        score_map = {id(pair): round((score - s_min) / s_range, 4) for pair, score in scored}
        for pair in pairs:
            norm = score_map.get(id(pair), 0.0)
            if is_bm25:
                pair.search_bm25_score = norm
                pair.search_vector_score = None
            else:
                pair.search_bm25_score = None
                pair.search_vector_score = norm

    @staticmethod
    def _get_allowed_extraction_types() -> Tuple[str, ...]:
        """Получить типы Q&A-пар, разрешённые для построения ответа пользователю."""
        if ai_settings.get_active_gk_include_llm_inferred_answers():
            return _ANSWER_ALLOWED_EXTRACTION_TYPES
        return ("thread_reply",)

    @staticmethod
    def _compute_relevance_tiers(
        merged: List[Tuple[QAPair, float]],
    ) -> None:
        """
        Вычислить уровень релевантности для каждой пары на основе
        нормализованных BM25 и vector scores.

        Используется обнаружение «обрыва» (cliff detection): если
        комбинированный score падает больше чем на GK_SCORE_CLIFF_THRESHOLD
        относительно лучшего результата — пары ниже обрыва понижаются.

        Результаты записываются in-place в поле pair.search_relevance_tier.
        """
        if not merged:
            return

        cliff_threshold = ai_settings.GK_SCORE_CLIFF_THRESHOLD

        # Вычислить combined quality score для каждой пары
        combined: List[Tuple[QAPair, float]] = []
        for pair, _rrf in merged:
            bm25_n = pair.search_bm25_score if pair.search_bm25_score is not None else 0.0
            vec_n = pair.search_vector_score if pair.search_vector_score is not None else 0.0
            # Если пара найдена обоими методами — среднее;
            # если только одним — берём тот что есть, но штрафуем на 50%.
            if pair.search_bm25_score is not None and pair.search_vector_score is not None:
                quality = (bm25_n + vec_n) / 2.0
            else:
                quality = max(bm25_n, vec_n) * 0.5
            combined.append((pair, quality))

        # Combined уже отсортирован по RRF (merged порядок), но
        # для cliff detection сортируем по quality desc.
        combined.sort(key=lambda x: x[1], reverse=True)
        quality_scores = [q for _, q in combined]

        # Найти индекс обрыва: первый индекс i где gap > cliff_threshold * best.
        best = quality_scores[0] if quality_scores else 1.0
        cliff_idx: Optional[int] = None
        if best > 0:
            for i in range(len(quality_scores) - 1):
                gap = quality_scores[i] - quality_scores[i + 1]
                if gap > cliff_threshold * best:
                    cliff_idx = i + 1
                    break

        # Назначить уровни.
        for idx, (pair, quality) in enumerate(combined):
            if cliff_idx is not None and idx >= cliff_idx:
                # Ниже обрыва — понижаем, но высокий абсолютный score
                # всё равно может дать «средняя».
                if quality >= 0.3:
                    pair.search_relevance_tier = "средняя"
                else:
                    pair.search_relevance_tier = "низкая"
            elif quality >= 0.6:
                pair.search_relevance_tier = "высокая"
            elif quality >= 0.3:
                pair.search_relevance_tier = "средняя"
            else:
                pair.search_relevance_tier = "низкая"

    @staticmethod
    def _log_rrf_diagnostics(
        query: str,
        diagnostics: List[Dict],
        pairs_by_id: Optional[Dict[int, QAPair]] = None,
    ) -> None:
        """Залогировать диагностическую таблицу RRF-результатов."""
        if not diagnostics:
            return

        lines = [
            f"GK RRF-поиск: query=\"{query[:100]}\" top_results={len(diagnostics)}"
        ]
        for i, d in enumerate(diagnostics, 1):
            bm25_r = f"bm25_rank={d['bm25_rank']}" if d["bm25_rank"] is not None else "bm25_rank=—"
            vec_r = f"vec_rank={d['vector_rank']}" if d["vector_rank"] is not None else "vec_rank=—"
            tier_str = ""
            if pairs_by_id:
                pair = pairs_by_id.get(d["pair_id"])
                if pair and pair.search_relevance_tier:
                    tier_str = f" tier={pair.search_relevance_tier}"
                    if pair.search_bm25_score is not None:
                        tier_str += f" bm25_n={pair.search_bm25_score:.2f}"
                    if pair.search_vector_score is not None:
                        tier_str += f" vec_n={pair.search_vector_score:.2f}"
            lines.append(
                f"  #{i} pair={d['pair_id']} rrf={d['rrf_score']:.6f} "
                f"{bm25_r} bm25_score={d['bm25_score']:.4f} "
                f"{vec_r} vec_score={d['vector_score']:.4f}"
                f"{tier_str} "
                f"q=\"{d['question_preview']}\""
            )

        logger.info("\n".join(lines))

    # -----------------------------------------------------------------------
    # Spell-check (корпусная коррекция опечаток + LLM fallback)
    # -----------------------------------------------------------------------

    def _build_spellcheck_vocabulary(self) -> bool:
        """Построить словарь SymSpell из BM25-корпуса GK Q&A-пар.

        Словарь строится из токенов всех загруженных Q&A-пар (question + answer),
        плюс все защищённые термины из ``_GK_FIXED_TERMS`` с высокой
        искусственной частотой.

        Returns:
            True, если словарь успешно построен.
        """
        if SymSpell is None:
            logger.warning(
                "GK Spellcheck: symspellpy не установлен, словарь не будет построен",
            )
            return False

        started_at = time.time()

        try:
            max_edit = max(1, int(ai_settings.GK_SPELLCHECK_MAX_EDIT_DISTANCE))
            sym = SymSpell(max_dictionary_edit_distance=max_edit, prefix_length=7)

            token_freq: Counter = Counter()

            for pair in self._corpus_pairs:
                text = f"{pair.question_text or ''} {pair.answer_text or ''}"
                prepared_text = self._prepare_text_for_fixed_terms(text)
                raw_tokens = [_canonical_fixed_token(token, self._fixed_tokens, self._fixed_term_token_map) for token in _TOKEN_RE.findall(prepared_text)]
                for t in raw_tokens:
                    if len(t) >= 2:
                        token_freq[t] += 1

            # Добавить защищённые термины с высокой частотой
            protected_freq = (
                max(1000, max(token_freq.values()) * 10) if token_freq else 1000
            )
            for term in self._fixed_tokens:
                token_freq[term] = max(token_freq.get(term, 0), protected_freq)

            if not token_freq:
                logger.warning("GK Spellcheck: словарь пуст, vocabulary не построен")
                return False

            for token, freq in token_freq.items():
                sym.create_dictionary_entry(token, freq)

            self._spellcheck_sym = sym
            self._spellcheck_vocab_size = len(token_freq)
            self._spellcheck_vocab_ready = True
            self._spellcheck_token_freq = dict(token_freq)

            duration_ms = int((time.time() - started_at) * 1000)
            logger.info(
                "GK Spellcheck vocabulary built: vocab_size=%d protected_terms=%d "
                "corpus_pairs=%d duration_ms=%d",
                self._spellcheck_vocab_size,
                len(self._fixed_terms),
                len(self._corpus_pairs),
                duration_ms,
            )
            return True

        except Exception:
            self._spellcheck_token_freq = {}
            logger.exception("GK Spellcheck: не удалось построить словарь")
            return False

    def _spellcheck_tokens(
        self,
        tokens: List[str],
    ) -> Tuple[List[str], List[Tuple[str, str]]]:
        """Исправить опечатки в списке токенов через corpus-based словарь.

        Защищённые термины (``_GK_FIXED_TERMS``), короткие токены,
        латинские и числовые токены пропускаются без изменений.

        Args:
            tokens: Список токенов для проверки.

        Returns:
            Кортеж (исправленные токены, список изменений [(original, corrected)]).
        """
        if not self._spellcheck_vocab_ready or self._spellcheck_sym is None:
            return tokens, []

        if _SymSpellVerbosity is None:
            return tokens, []

        min_length = max(2, int(ai_settings.GK_SPELLCHECK_MIN_TOKEN_LENGTH))
        max_edit = max(1, int(ai_settings.GK_SPELLCHECK_MAX_EDIT_DISTANCE))

        corrected_tokens: List[str] = []
        changes: List[Tuple[str, str]] = []
        exact_match_rare_freq_threshold = 2

        for token in tokens:
            canonical_token = _canonical_fixed_token(token, self._fixed_tokens, self._fixed_term_token_map)

            # Пропускаем защищённые термины
            if canonical_token in self._fixed_tokens:
                corrected_tokens.append(canonical_token)
                continue

            # Пропускаем короткие токены
            if len(canonical_token) < min_length:
                corrected_tokens.append(canonical_token)
                continue

            # Пропускаем не-кириллические токены (латиница, числа)
            if not _CYRILLIC_TOKEN_RE.search(canonical_token):
                corrected_tokens.append(canonical_token)
                continue

            # Ищем коррекцию через SymSpell
            try:
                suggestions = self._spellcheck_sym.lookup(
                    canonical_token,
                    _SymSpellVerbosity.CLOSEST,
                    max_edit_distance=max_edit,
                )
            except Exception:
                corrected_tokens.append(canonical_token)
                continue

            candidate: Optional[str] = None
            if suggestions:
                top = suggestions[0]
                if top.distance > 0:
                    candidate = top.term
                else:
                    token_freq = int(getattr(self, "_spellcheck_token_freq", {}).get(canonical_token, 0) or 0)
                    if token_freq <= exact_match_rare_freq_threshold:
                        try:
                            all_suggestions = self._spellcheck_sym.lookup(
                                canonical_token,
                                _SymSpellVerbosity.ALL,
                                max_edit_distance=max_edit,
                            )
                        except Exception:
                            all_suggestions = []

                        for alt in all_suggestions:
                            alt_term = str(getattr(alt, "term", "") or "")
                            if not alt_term or alt_term == canonical_token:
                                continue
                            if int(getattr(alt, "distance", 0) or 0) <= 0:
                                continue
                            alt_freq = int(
                                getattr(self, "_spellcheck_token_freq", {}).get(
                                    alt_term,
                                    int(getattr(alt, "count", 0) or 0),
                                )
                                or 0
                            )
                            if alt_freq >= max(5, token_freq * 5):
                                candidate = alt_term
                                break

                    if candidate is None:
                        logger.info(
                            "GK Spellcheck token kept as-is: token=%s token_freq=%d "
                            "reason=exact_match_in_vocab max_edit=%d",
                            canonical_token,
                            token_freq,
                            max_edit,
                        )

            normalized_candidate = _canonical_fixed_token(candidate or "", self._fixed_tokens, self._fixed_term_token_map)
            if (
                normalized_candidate
                and (
                    normalized_candidate not in self._fixed_tokens
                    or canonical_token in self._fixed_tokens
                )
            ):
                corrected_tokens.append(normalized_candidate)
                changes.append((canonical_token, normalized_candidate))
            else:
                corrected_tokens.append(canonical_token)

        return corrected_tokens, changes

    def _get_suspicious_uncorrected_count(
        self,
        tokens: List[str],
        changes: List[Tuple[str, str]],
    ) -> Tuple[int, int]:
        """Подсчитать «подозрительные» токены, не исправленные corpus-коррекцией.

        Подозрительный токен — кириллический, длина ≥ min_length,
        не в словаре и не в защищённых терминах.

        Returns:
            (suspicious_uncorrected_count, total_suspicious_count)
        """
        if not self._spellcheck_vocab_ready or self._spellcheck_sym is None:
            return 0, 0

        min_length = max(2, int(ai_settings.GK_SPELLCHECK_MIN_TOKEN_LENGTH))
        corrected_originals = {orig for orig, _ in changes}

        suspicious_total = 0
        suspicious_uncorrected = 0

        for token in tokens:
            canonical_token = _canonical_fixed_token(token, self._fixed_tokens, self._fixed_term_token_map)
            if canonical_token in self._fixed_tokens:
                continue
            if len(canonical_token) < min_length:
                continue
            if not _CYRILLIC_TOKEN_RE.search(canonical_token):
                continue

            # Проверяем, есть ли токен в словаре
            try:
                suggestions = self._spellcheck_sym.lookup(
                    canonical_token,
                    _SymSpellVerbosity.CLOSEST,
                    max_edit_distance=0,
                )
                in_vocab = bool(suggestions)
            except Exception:
                in_vocab = False

            if not in_vocab:
                suspicious_total += 1
                if canonical_token not in corrected_originals:
                    suspicious_uncorrected += 1

        return suspicious_uncorrected, suspicious_total

    def _apply_spellcheck_to_query(
        self,
        query: str,
    ) -> Tuple[str, List[Tuple[str, str]], str]:
        """Применить corpus-based коррекцию к строке запроса.

        Токенизирует запрос, применяет ``_spellcheck_tokens``,
        реконструирует строку путём замены оригинальных подстрок.

        Args:
            query: Исходный запрос.

        Returns:
            (corrected_query, changes, source) где source — ``corpus``
            или ``none``.
        """
        if not ai_settings.GK_SPELLCHECK_ENABLED:
            return query, [], "disabled"

        if not self._spellcheck_vocab_ready:
            return query, [], "vocab_not_ready"

        prepared_query = self._prepare_text_for_fixed_terms(query or "")
        original_tokens = [_canonical_fixed_token(token, self._fixed_tokens, self._fixed_term_token_map) for token in _TOKEN_RE.findall(prepared_query)]
        if not original_tokens:
            return query, [], "none"

        _, changes = self._spellcheck_tokens(original_tokens)
        if not changes:
            return query, [], "none"

        # Реконструкция: заменяем подстроки в исходном запросе
        corrected = self._prepare_text_for_fixed_terms(query)
        for orig, repl in changes:
            pattern = re.compile(re.escape(orig), re.IGNORECASE)
            corrected = pattern.sub(repl, corrected, count=1)

        for fixed_token in self._fixed_tokens:
            restored = self._restore_fixed_token(fixed_token)
            corrected = corrected.replace(fixed_token, restored)

        return corrected, changes, "corpus"

    async def _spellcheck_llm_fallback(
        self,
        query: str,
    ) -> Tuple[str, List[Tuple[str, str]]]:
        """Исправить опечатки через LLM (dedicated call).

        Вызывается, когда corpus-based коррекция не справилась и
        в запросе остались подозрительные токены.
        Результаты кэшируются с TTL.

        Args:
            query: Исходный вопрос.

        Returns:
            (исправленный текст, список изменений [(from, to)]).
        """
        cache_key = query.strip().lower()

        # Проверка кэша
        now = time.time()
        cached = self._spellcheck_llm_cache.get(cache_key)
        if cached is not None:
            cached_text, cached_changes, expires_at = cached
            if expires_at > now:
                logger.info(
                    "GK Spellcheck LLM cache hit: query='%.60s' changes=%d",
                    query,
                    len(cached_changes),
                )
                return cached_text, cached_changes

        # LLM вызов
        try:
            from src.core.ai.prompts import build_spellcheck_prompt

            provider = get_provider("deepseek")
            max_chars = max(50, int(ai_settings.GK_SPELLCHECK_LLM_MAX_CHARS))
            truncated = query.strip()[:max_chars]
            protected_terms_list = sorted(self._fixed_terms)

            prompt = build_spellcheck_prompt(truncated, protected_terms_list)
            raw_response = await provider.chat(
                messages=[{"role": "user", "content": truncated}],
                system_prompt=prompt,
                purpose="gk_spell_correction",
                response_format={"type": "json_object"},
            )

            if not raw_response or not raw_response.strip():
                return query, []

            # Парсинг JSON-ответа
            response_text = raw_response.strip()
            fence_match = _JSON_CODE_FENCE_RE.match(response_text)
            if fence_match:
                response_text = fence_match.group(1).strip()

            parsed = json.loads(response_text)
            corrected = str(parsed.get("corrected") or query).strip()
            raw_changes = parsed.get("changes") or []

            changes: List[Tuple[str, str]] = []
            for change in raw_changes:
                if isinstance(change, dict):
                    from_val = str(change.get("from") or "").strip()
                    to_val = str(change.get("to") or "").strip()
                    if from_val and to_val and from_val != to_val:
                        changes.append((from_val, to_val))

            # Safety guard: LLM не должен удалять защищённые термины
            corrected_lower = self._prepare_text_for_fixed_terms(corrected)
            query_lower = self._prepare_text_for_fixed_terms(query)
            for term in self._fixed_tokens:
                if term in query_lower and term not in corrected_lower:
                    logger.warning(
                        "GK Spellcheck LLM removed protected term '%s', "
                        "reverting to original",
                        term,
                    )
                    return query, []

            # Кэширование
            ttl = max(30, int(ai_settings.GK_SPELLCHECK_LLM_CACHE_TTL_SECONDS))
            self._spellcheck_llm_cache[cache_key] = (corrected, changes, now + ttl)

            # Очистка просроченных записей (до 10 за вызов)
            expired_keys = [
                k
                for k, (_, _, exp) in list(self._spellcheck_llm_cache.items())[:50]
                if exp <= now
            ]
            for k in expired_keys[:10]:
                self._spellcheck_llm_cache.pop(k, None)

            logger.info(
                "GK Spellcheck LLM corrected: query='%.60s' corrected='%.60s' changes=%d",
                query,
                corrected,
                len(changes),
            )
            return corrected, changes

        except Exception as exc:
            logger.warning(
                "GK Spellcheck LLM fallback failed, returning original: "
                "query='%.60s' error_type=%s error=%r",
                query,
                type(exc).__name__,
                exc,
            )
            return query, []

    async def _apply_spellcheck_pipeline(self, query: str) -> str:
        """Полный pipeline коррекции опечаток: corpus-based → LLM fallback.

        1. Применяет corpus-based коррекцию (SymSpellPy).
        2. Если включён LLM fallback и доля подозрительных неисправленных
           токенов превышает порог — вызывает LLM для дополнительной коррекции.

        Args:
            query: Исходный запрос пользователя.

        Returns:
            Исправленный запрос (или оригинал, если коррекция не требуется).
        """
        if not ai_settings.GK_SPELLCHECK_ENABLED:
            logger.info("GK Spellcheck pipeline skipped: reason=disabled query='%.80s'", query)
            return query

        # Если в запрос уже добавлен image-gist, корректируем только пользовательскую
        # часть до маркера, чтобы длинный хвост описания изображения не занижал
        # чувствительность spellcheck fallback.
        image_marker = "\n[Суть по изображению:"
        safe_query = query or ""
        image_suffix = ""
        marker_idx = safe_query.find(image_marker)
        if marker_idx >= 0:
            image_suffix = safe_query[marker_idx:]
            safe_query = safe_query[:marker_idx]
        if not safe_query.strip():
            logger.info("GK Spellcheck pipeline skipped: reason=empty_query query='%.80s'", query)
            return query

        # Шаг 1: corpus-based коррекция
        corrected, corpus_changes, source = self._apply_spellcheck_to_query(safe_query)

        # Шаг 2: оценить, нужен ли LLM fallback
        llm_changes: List[Tuple[str, str]] = []
        llm_used = False
        suspicious_uncorrected = 0
        suspicious_total = 0
        checkable = 0
        threshold = float(ai_settings.GK_SPELLCHECK_LLM_FALLBACK_THRESHOLD)
        llm_fallback_enabled = bool(ai_settings.GK_SPELLCHECK_LLM_FALLBACK_ENABLED)
        if (
            llm_fallback_enabled
            and self._spellcheck_vocab_ready
        ):
            original_tokens = _TOKEN_RE.findall((safe_query or "").lower())
            suspicious_uncorrected, suspicious_total = (
                self._get_suspicious_uncorrected_count(original_tokens, corpus_changes)
            )
            checkable = sum(
                1
                for t in original_tokens
                if (
                    t not in self._fixed_tokens
                    and len(t) >= max(2, int(ai_settings.GK_SPELLCHECK_MIN_TOKEN_LENGTH))
                    and _CYRILLIC_TOKEN_RE.search(t)
                )
            )
            if checkable > 0 and suspicious_uncorrected / checkable >= threshold:
                corrected, llm_changes = await self._spellcheck_llm_fallback(corrected)
                llm_used = True
            else:
                logger.info(
                    "GK Spellcheck LLM skipped: query='%.80s' checkable=%d "
                    "suspicious_uncorrected=%d suspicious_total=%d threshold=%.3f",
                    safe_query,
                    checkable,
                    suspicious_uncorrected,
                    suspicious_total,
                    threshold,
                )
        elif llm_fallback_enabled and not self._spellcheck_vocab_ready:
            logger.info(
                "GK Spellcheck LLM skipped: reason=vocab_not_ready query='%.80s'",
                safe_query,
            )
        else:
            logger.info(
                "GK Spellcheck LLM skipped: reason=disabled query='%.80s'",
                safe_query,
            )

        total_changes = len(corpus_changes) + len(llm_changes)
        logger.info(
            "GK Spellcheck pipeline: original='%.80s' corrected='%.80s' source=%s "
            "corpus_changes=%d llm_fallback_enabled=%s llm_used=%s llm_changes=%d "
            "vocab_ready=%s suspicious_uncorrected=%d suspicious_total=%d "
            "checkable=%d threshold=%.3f total_changes=%d",
            query,
            corrected,
            source,
            len(corpus_changes),
            llm_fallback_enabled,
            llm_used,
            len(llm_changes),
            self._spellcheck_vocab_ready,
            suspicious_uncorrected,
            suspicious_total,
            checkable,
            threshold,
            total_changes,
        )

        return f"{corrected}{image_suffix}" if image_suffix else corrected

    def _prepare_text_for_fixed_terms(self, text: str) -> str:
        """Защитить multi-word термины, заменив пробелы в них на подчёркивания."""
        prepared = (text or "").lower()
        if not prepared or not self._fixed_phrases:
            return prepared

        for phrase in self._fixed_phrases:
            token = self._fixed_term_token_map.get(phrase, phrase)
            pattern = re.compile(rf"(?<![a-zа-яё0-9]){re.escape(phrase)}(?![a-zа-яё0-9])", re.IGNORECASE)
            prepared = pattern.sub(token, prepared)

        return prepared

    def _restore_fixed_token(self, token: str) -> str:
        """Восстановить человекочитаемый protected term по токену, если возможно."""
        safe_token = (token or "").strip().lower()
        if not safe_token:
            return ""
        return self._fixed_token_term_map.get(safe_token, safe_token)

    # -----------------------------------------------------------------------
    # Токенизация и нормализация (Russian)
    # -----------------------------------------------------------------------

    def _tokenize(self, text: str) -> List[str]:
        """
        Токенизировать текст для BM25 с опциональной Russian-нормализацией.

        Извлекает слова regex-паттерном, фильтрует короткие (кроме защищённых),
        удаляет стоп-слова и нормализует через лемматизацию/стемминг.

        Args:
            text: Исходный текст.

        Returns:
            Список нормализованных токенов.
        """
        prepared = self._prepare_text_for_fixed_terms(text or "")
        raw_tokens = [_canonical_fixed_token(token, self._fixed_tokens, self._fixed_term_token_map) for token in _TOKEN_RE.findall(prepared)]
        tokens = [
            token
            for token in raw_tokens
            if len(token) >= 3
            or token in self._fixed_tokens
            or bool(_SHORT_ALNUM_TOKEN_RE.fullmatch(token))
            or (token.isdigit() and len(token) >= 2)
        ]
        if not tokens:
            return []

        # Удалить стоп-слова
        filtered = [t for t in tokens if t not in _GK_STOPWORDS]
        if not filtered:
            filtered = tokens  # safety guard

        # Russian-нормализация
        if ai_settings.GK_RU_NORMALIZATION_ENABLED:
            return [self._normalize_token(t) for t in filtered if t]

        return filtered

    def _tokenize_with_diagnostics(self, text: str) -> Dict[str, object]:
        """Токенизировать текст и вернуть расширенную диагностику этапов фильтрации."""
        prepared = self._prepare_text_for_fixed_terms(text or "")
        raw_tokens = [_canonical_fixed_token(token, self._fixed_tokens, self._fixed_term_token_map) for token in _TOKEN_RE.findall(prepared)]
        length_filtered_tokens = [
            token
            for token in raw_tokens
            if len(token) >= 3
            or token in self._fixed_tokens
            or bool(_SHORT_ALNUM_TOKEN_RE.fullmatch(token))
            or (token.isdigit() and len(token) >= 2)
        ]

        removed_short_tokens = max(0, len(raw_tokens) - len(length_filtered_tokens))
        if not length_filtered_tokens:
            return {
                "tokens": [],
                "raw_tokens_total": len(raw_tokens),
                "removed_short_tokens": removed_short_tokens,
                "removed_stopwords": [],
                "removed_stopwords_count": 0,
            }

        removed_stopwords = [token for token in length_filtered_tokens if token in _GK_STOPWORDS]
        filtered_tokens = [token for token in length_filtered_tokens if token not in _GK_STOPWORDS]
        if not filtered_tokens:
            filtered_tokens = length_filtered_tokens
            removed_stopwords = []

        if ai_settings.GK_RU_NORMALIZATION_ENABLED:
            normalized_tokens = [self._normalize_token(token) for token in filtered_tokens if token]
        else:
            normalized_tokens = [token for token in filtered_tokens if token]

        return {
            "tokens": normalized_tokens,
            "raw_tokens_total": len(raw_tokens),
            "removed_short_tokens": removed_short_tokens,
            "removed_stopwords": removed_stopwords,
            "removed_stopwords_count": len(removed_stopwords),
        }

    def _normalize_token(self, token: str) -> str:
        """Нормализовать токен: лемматизация + стемминг для русского языка."""
        safe_token = _canonical_fixed_token((token or "").strip().lower(), self._fixed_tokens, self._fixed_term_token_map)
        if not safe_token:
            return ""

        if safe_token in self._fixed_tokens:
            return safe_token

        cached = self._normalized_token_cache.get(safe_token)
        if cached is not None:
            return cached

        if not _CYRILLIC_TOKEN_RE.search(safe_token):
            self._normalized_token_cache[safe_token] = safe_token
            return safe_token

        # Лемматизация → стемминг
        normalized = self._lemmatize_ru_token(safe_token)
        normalized = self._stem_ru_token(normalized)
        normalized = normalized or safe_token

        self._normalized_token_cache[safe_token] = normalized
        return normalized

    def _lemmatize_ru_token(self, token: str) -> str:
        """Лемматизировать русский токен через pymorphy3 с graceful fallback."""
        analyzer = self._get_ru_morph_analyzer()
        if analyzer is None:
            return token
        try:
            parsed = analyzer.parse(token)
            if parsed:
                normal_form = str(getattr(parsed[0], "normal_form", "") or "").strip().lower()
                if normal_form:
                    return normal_form
        except Exception:
            return token
        return token

    def _stem_ru_token(self, token: str) -> str:
        """Стемминг русского токена через snowballstemmer."""
        stemmer = self._get_ru_stemmer()
        if stemmer is None:
            return token
        try:
            stemmed = stemmer.stemWord(token)
            return str(stemmed or token).strip().lower()
        except Exception:
            return token

    def _get_ru_morph_analyzer(self) -> Optional[object]:
        """Ленивая инициализация pymorphy3 MorphAnalyzer."""
        if self._ru_morph_analyzer is not None:
            return self._ru_morph_analyzer
        try:
            import pymorphy3
            self._ru_morph_analyzer = pymorphy3.MorphAnalyzer()
            return self._ru_morph_analyzer
        except Exception as exc:
            if not self._normalization_warning_logged:
                logger.warning("GK нормализация: pymorphy3 недоступен: %s", exc)
                self._normalization_warning_logged = True
            return None

    def _get_ru_stemmer(self) -> Optional[object]:
        """Ленивая инициализация snowballstemmer для русского."""
        if self._ru_stemmer is not None:
            return self._ru_stemmer
        try:
            import snowballstemmer
            self._ru_stemmer = snowballstemmer.stemmer("russian")
            return self._ru_stemmer
        except Exception as exc:
            if not self._normalization_warning_logged:
                logger.warning("GK нормализация: snowballstemmer недоступен: %s", exc)
                self._normalization_warning_logged = True
            return None

    # -----------------------------------------------------------------------
    # BM25 scoring
    # -----------------------------------------------------------------------

    @staticmethod
    def _dampen_common_query_tokens(
        query_tokens: List[str],
        corpus_tokens: List[List[str]],
        return_diagnostics: bool = False,
    ) -> List[str] | Tuple[List[str], Dict[str, object]]:
        """Подавить common-токены запроса с высокой DF в BM25-корпусе GK."""
        def _result(
            tokens: List[str],
            *,
            reason: str,
            doc_count: int,
            threshold: float,
            dampen_ratio: float,
            dampen_factor: float,
            common_tokens: Optional[set[str]] = None,
            rare_tokens: Optional[List[str]] = None,
            boost_factor: int = 1,
        ) -> List[str] | Tuple[List[str], Dict[str, object]]:
            if not return_diagnostics:
                return tokens

            before_counts = Counter(query_tokens)
            after_counts = Counter(tokens)
            changed_counts: Dict[str, Dict[str, int]] = {}
            for token in sorted(set(before_counts) | set(after_counts)):
                before = int(before_counts.get(token, 0))
                after = int(after_counts.get(token, 0))
                if before != after:
                    changed_counts[token] = {"before": before, "after": after}

            diagnostics: Dict[str, object] = {
                "applied": bool(reason == "applied"),
                "reason": reason,
                "doc_count": int(doc_count),
                "threshold_docs": float(threshold),
                "dampen_ratio": float(dampen_ratio),
                "dampen_factor": float(dampen_factor),
                "boost_factor": int(boost_factor),
                "before_count": len(query_tokens),
                "after_count": len(tokens),
                "before_tokens": list(query_tokens),
                "after_tokens": list(tokens),
                "common_tokens": sorted(common_tokens or set()),
                "rare_tokens": sorted(set(rare_tokens or [])),
                "changed_token_counts": changed_counts,
            }
            return tokens, diagnostics

        dampen_ratio = max(0.0, min(1.0, float(ai_settings.get_active_gk_bm25_idf_dampen_ratio())))
        dampen_factor = max(0.0, min(1.0, float(ai_settings.get_active_gk_bm25_idf_dampen_factor())))

        if not query_tokens or not corpus_tokens:
            return _result(
                list(query_tokens),
                reason="empty_input",
                doc_count=len(corpus_tokens),
                threshold=0.0,
                dampen_ratio=dampen_ratio,
                dampen_factor=dampen_factor,
            )

        if dampen_ratio >= 1.0:
            return _result(
                list(query_tokens),
                reason="ratio_disabled",
                doc_count=len(corpus_tokens),
                threshold=0.0,
                dampen_ratio=dampen_ratio,
                dampen_factor=dampen_factor,
            )

        doc_count = len(corpus_tokens)
        if doc_count == 0:
            return _result(
                list(query_tokens),
                reason="empty_corpus",
                doc_count=doc_count,
                threshold=0.0,
                dampen_ratio=dampen_ratio,
                dampen_factor=dampen_factor,
            )

        unique_query_tokens = set(query_tokens)
        doc_freq: Dict[str, int] = {}
        for token in unique_query_tokens:
            count = sum(1 for doc_tokens in corpus_tokens if token in doc_tokens)
            doc_freq[token] = count

        threshold = dampen_ratio * doc_count
        common_tokens = {token for token, df in doc_freq.items() if df > threshold}

        if not common_tokens:
            return _result(
                list(query_tokens),
                reason="no_common_tokens",
                doc_count=doc_count,
                threshold=threshold,
                dampen_ratio=dampen_ratio,
                dampen_factor=dampen_factor,
                common_tokens=common_tokens,
            )

        rare_tokens = [t for t in query_tokens if t not in common_tokens]
        if not rare_tokens:
            return _result(
                list(query_tokens),
                reason="all_tokens_common",
                doc_count=doc_count,
                threshold=threshold,
                dampen_ratio=dampen_ratio,
                dampen_factor=dampen_factor,
                common_tokens=common_tokens,
                rare_tokens=rare_tokens,
            )

        boost_factor = max(1, int(round(1.0 / max(dampen_factor, 0.01))))
        dampened_query: List[str] = []
        seen_common: set[str] = set()
        for token in query_tokens:
            if token in common_tokens:
                if token not in seen_common:
                    dampened_query.append(token)
                    seen_common.add(token)
            else:
                for _ in range(boost_factor):
                    dampened_query.append(token)

        return _result(
            dampened_query,
            reason="applied",
            doc_count=doc_count,
            threshold=threshold,
            dampen_ratio=dampen_ratio,
            dampen_factor=dampen_factor,
            common_tokens=common_tokens,
            rare_tokens=rare_tokens,
            boost_factor=boost_factor,
        )

    @staticmethod
    def _trim_tokens_for_log(tokens: List[str], limit: int = 20) -> List[str]:
        """Ограничить длину списка токенов в диагностических логах GK."""
        if len(tokens) <= limit:
            return list(tokens)
        return list(tokens[:limit]) + [f"...(+{len(tokens) - limit})"]

    def _log_idf_dampening_effect(
        self,
        *,
        stage: str,
        query: str,
        diagnostics: Dict[str, object],
    ) -> None:
        """Записать детальный диагностический лог применения IDF-dampening в GK."""
        query_preview = _MULTISPACE_RE.sub(" ", str(query or "").strip())
        if len(query_preview) > 160:
            query_preview = f"{query_preview[:159]}…"

        before_tokens = [str(token) for token in diagnostics.get("before_tokens", [])]
        after_tokens = [str(token) for token in diagnostics.get("after_tokens", [])]
        common_tokens = [str(token) for token in diagnostics.get("common_tokens", [])]
        rare_tokens = [str(token) for token in diagnostics.get("rare_tokens", [])]
        changed_token_counts = diagnostics.get("changed_token_counts", {})
        if not isinstance(changed_token_counts, dict):
            changed_token_counts = {}

        payload = {
            "query": query_preview,
            "applied": bool(diagnostics.get("applied", False)),
            "reason": str(diagnostics.get("reason", "unknown")),
            "doc_count": int(diagnostics.get("doc_count", 0) or 0),
            "threshold_docs": round(float(diagnostics.get("threshold_docs", 0.0) or 0.0), 3),
            "dampen_ratio": round(float(diagnostics.get("dampen_ratio", 0.0) or 0.0), 3),
            "dampen_factor": round(float(diagnostics.get("dampen_factor", 0.0) or 0.0), 3),
            "boost_factor": int(diagnostics.get("boost_factor", 1) or 1),
            "before_count": int(diagnostics.get("before_count", len(before_tokens)) or 0),
            "after_count": int(diagnostics.get("after_count", len(after_tokens)) or 0),
            "before_tokens": self._trim_tokens_for_log(before_tokens),
            "after_tokens": self._trim_tokens_for_log(after_tokens),
            "common_tokens": self._trim_tokens_for_log(common_tokens, limit=10),
            "rare_tokens": self._trim_tokens_for_log(rare_tokens, limit=10),
            "changed_token_counts": changed_token_counts,
        }

        logger.info(
            "GK IDF dampening [%s]: %s",
            stage,
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
        )

    @staticmethod
    def _score_corpus_bm25(
        corpus_tokens: List[List[str]],
        query_tokens: List[str],
    ) -> List[float]:
        """
        Вычислить BM25-score для корпуса документов по токенам запроса.

        Использует rank_bm25.BM25Okapi, если доступен, иначе ручную реализацию.

        Args:
            corpus_tokens: Токенизированные документы корпуса.
            query_tokens: Токенизированный запрос.

        Returns:
            Список BM25-score для каждого документа корпуса.
        """
        if not corpus_tokens or not query_tokens:
            return [0.0 for _ in corpus_tokens]

        safe_corpus = [tokens if tokens else [""] for tokens in corpus_tokens]
        k1 = max(0.01, float(ai_settings.GK_BM25_K1))
        b = max(0.0, min(1.0, float(ai_settings.GK_BM25_B)))

        if BM25Okapi is not None:
            try:
                bm25 = BM25Okapi(safe_corpus, k1=k1, b=b)
                return [max(0.0, float(score)) for score in bm25.get_scores(query_tokens)]
            except Exception:
                pass

        # Ручная fallback-реализация BM25
        doc_count = len(safe_corpus)
        avg_doc_len = sum(len(dt) for dt in safe_corpus) / max(doc_count, 1)

        doc_freq: Dict[str, int] = {}
        term_freq_by_doc: List[Counter] = []
        for doc_tokens in safe_corpus:
            tf = Counter(doc_tokens)
            term_freq_by_doc.append(tf)
            for t in tf.keys():
                doc_freq[t] = doc_freq.get(t, 0) + 1

        query_tf = Counter(query_tokens)
        scores: List[float] = [0.0 for _ in safe_corpus]

        for token, qf in query_tf.items():
            df = doc_freq.get(token, 0)
            if df <= 0:
                continue
            idf = math.log(1.0 + ((doc_count - df + 0.5) / (df + 0.5)))
            for idx, tf in enumerate(term_freq_by_doc):
                freq = tf.get(token, 0)
                if freq <= 0:
                    continue
                doc_len = len(safe_corpus[idx])
                denominator = freq + (k1 * (1.0 - b + (b * doc_len / max(avg_doc_len, 1e-9))))
                if denominator <= 0:
                    continue
                scores[idx] += idf * ((freq * (k1 + 1.0)) / denominator) * qf

        return [max(0.0, float(s)) for s in scores]

    # -----------------------------------------------------------------------
    # Вспомогательные методы
    # -----------------------------------------------------------------------

    def _resolve_source_message_links(self, pair_ids: List[int]) -> List[str]:
        """Построить ссылки на сообщения с похожими кейсами по найденным Q&A-парам."""
        links: List[str] = []
        seen_links: set = set()

        for pair_id in pair_ids:
            pair = gk_db.get_qa_pair_by_id(pair_id)
            if not pair:
                continue

            message = None
            if pair.answer_message_id:
                message = gk_db.get_message_by_id(pair.answer_message_id)
            if message is None and pair.question_message_id:
                message = gk_db.get_message_by_id(pair.question_message_id)
            if not message:
                continue

            link = self._build_group_message_link(
                group_id=message.group_id,
                telegram_message_id=message.telegram_message_id,
            )
            if link and link not in seen_links:
                links.append(link)
                seen_links.add(link)

        return links

    @staticmethod
    def _build_group_message_link(group_id: int, telegram_message_id: int) -> Optional[str]:
        """Построить Telegram-ссылку на сообщение внутри группы/супергруппы."""
        if not group_id or not telegram_message_id:
            return None

        normalized_group_id = str(abs(group_id))
        if normalized_group_id.startswith("100"):
            normalized_group_id = normalized_group_id[3:]
        if not normalized_group_id:
            return None

        return f"https://t.me/c/{normalized_group_id}/{telegram_message_id}"

    @staticmethod
    def _parse_json_response(raw: str) -> Optional[Dict]:
        """Извлечь JSON из ответа LLM."""
        if not raw or not raw.strip():
            return None

        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            if len(lines) >= 3:
                text = "\n".join(lines[1:-1])
            else:
                text = text.strip("`").strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = raw.find("{")
            end = raw.rfind("}")
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(raw[start : end + 1])
                except json.JSONDecodeError:
                    pass

        logger.warning("Не удалось распарсить JSON из LLM: %s", raw[:200])
        return None
