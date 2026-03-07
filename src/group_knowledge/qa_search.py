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
from src.core.ai.llm_provider import get_provider
from src.group_knowledge import database as gk_db
from src.group_knowledge.models import QAPair

try:
    from rank_bm25 import BM25Okapi
except ImportError:
    BM25Okapi = None  # type: ignore[misc,assignment]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Токенизация и нормализация текста
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"\d+(?:[\.,]\d+)+|[a-zа-яё0-9]+", re.IGNORECASE)
_SHORT_ALNUM_TOKEN_RE = re.compile(r"(?:[a-zа-яё]\d|\d[a-zа-яё])", re.IGNORECASE)
_CYRILLIC_TOKEN_RE = re.compile(r"[а-яё]", re.IGNORECASE)

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

# Термины, защищённые от нормализации и фильтрации по длине.
_GK_FIXED_TERMS: frozenset = frozenset({
    "осно", "усн", "псн", "енвд", "нпд", "сно",
    "фн", "ккт", "офд", "инн", "кпп", "аусн",
    "ип", "ндс", "ндфл", "ооо", "кбк",
    "ффд", "фд", "фп", "фпд", "рн", "зн", "ккм",
    "pos", "пин", "арм", "цто", "то", "усо", "атм",
    "nfc", "sim", "pin", "tcp", "usb", "lan", "gps",
})

# Промпт для генерации ответа на основе Q&A пар
ANSWER_GENERATION_PROMPT = """Ты — помощник технической поддержки для полевых инженеров компании СберСервис, обслуживающих банка Сбербанк.

На основе найденных пар вопрос-ответ из базы знаний технической поддержки ответь на вопрос инженера.

Найденные пары:
{qa_context}

Правила:
1. Отвечай максимально точно и конкретно, опираясь на найденные пары.
2. Если несколько пар релевантны — объедини информацию.
3. Если ни одна пара не релевантна вопросу — честно скажи, что не нашёл информации.
4. Не придумывай информацию, которой нет в найденных парах. Не придумывай факты.
5. Отвечай на русском языке.

Верни JSON:
{{
    "answer": "Текст ответа",
    "is_relevant": true/false,
    "confidence": 0.0-1.0,
    "used_pair_ids": [1, 2, ...]
}}"""


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
        self._model_name = model_name or ai_settings.GK_RESPONDER_MODEL
        self._top_k = ai_settings.GK_RESPONDER_TOP_K

        # Кэш BM25-корпуса
        self._corpus_pairs: List[QAPair] = []
        self._corpus_tokens: List[List[str]] = []
        self._corpus_loaded_at: float = 0.0
        self._corpus_signature: Optional[Tuple[int, int, int]] = None

        # Кэш нормализации токенов
        self._normalized_token_cache: Dict[str, str] = {}
        self._ru_morph_analyzer: Optional[object] = None
        self._ru_stemmer: Optional[object] = None
        self._normalization_warning_logged: bool = False

    # -----------------------------------------------------------------------
    # Публичный API
    # -----------------------------------------------------------------------

    async def search(
        self,
        query: str,
        top_k: Optional[int] = None,
    ) -> List[QAPair]:
        """
        Найти релевантные Q&A пары для запроса.

        Использует гибридный подход: BM25 + векторный поиск с RRF-слиянием.

        Args:
            query: Текст запроса.
            top_k: Число результатов (по умолчанию из настроек).

        Returns:
            Список релевантных QAPair, отсортированных по RRF-score.
        """
        k = top_k or self._top_k
        candidates_per_method = ai_settings.GK_SEARCH_CANDIDATES_PER_METHOD

        # BM25 (лексический) поиск
        bm25_results = self._bm25_search(query, candidates_per_method)

        # Векторный поиск
        vector_results = await self._vector_search(query, candidates_per_method)

        # Если гибридный режим выключен или один из методов пуст — fallback
        if not ai_settings.GK_HYBRID_ENABLED:
            logger.info(
                "GK гибридный поиск отключён, используются только vectorные результаты: "
                "query=%s vector_count=%d",
                query[:100], len(vector_results),
            )
            results = vector_results if vector_results else bm25_results
            return [pair for pair, _ in results[:k]]

        if not bm25_results and not vector_results:
            logger.info("GK поиск: нет результатов ни от BM25, ни от vector: query=%s", query[:100])
            return []

        if not bm25_results:
            logger.info(
                "GK поиск: BM25 не дал результатов, используется только vector: "
                "query=%s vector_count=%d",
                query[:100], len(vector_results),
            )
            return [pair for pair, _ in vector_results[:k]]

        if not vector_results:
            logger.info(
                "GK поиск: vector не дал результатов, используется только BM25: "
                "query=%s bm25_count=%d",
                query[:100], len(bm25_results),
            )
            return [pair for pair, _ in bm25_results[:k]]

        # RRF-слияние
        merged, diagnostics = self._rrf_merge(bm25_results, vector_results, k)

        # Диагностический лог
        self._log_rrf_diagnostics(query, diagnostics)

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
        }

        if preload_vector_model:
            try:
                from src.core.ai.vector_search import LocalEmbeddingProvider, LocalVectorIndex

                embedding_provider = LocalEmbeddingProvider()
                _ = embedding_provider.encode("прогрев модели gk поиска")
                _ = LocalVectorIndex(chunk_collection_name=ai_settings.GK_QA_VECTOR_COLLECTION)
                diagnostics["vector_model_preloaded"] = True
            except Exception as exc:
                diagnostics["vector_model_preloaded"] = False
                diagnostics["vector_warmup_error"] = str(exc)
                logger.warning("GK warmup: не удалось прогреть vector-модель: %s", exc)

        logger.info(
            "GK warmup: corpus_pairs=%d corpus_signature=%s vector_model_preloaded=%s",
            diagnostics["corpus_pairs"],
            diagnostics["corpus_signature"],
            diagnostics["vector_model_preloaded"],
        )
        return diagnostics

    async def answer_question(
        self,
        query: str,
    ) -> Optional[Dict]:
        """
        Ответить на вопрос, используя найденные Q&A пары.

        Args:
            query: Текст вопроса.

        Returns:
            Словарь с ключами: answer, confidence, source_pair_ids,
            is_relevant, primary_source_link, source_message_links.
            None если ответ не найден.
        """
        # Поиск релевантных пар
        relevant_pairs = await self.search(query)

        if not relevant_pairs:
            logger.info("Не найдены Q&A пары для вопроса: %s", query[:100])
            return None

        # Подготовить контекст из найденных пар
        qa_context_parts = []
        pair_id_map = {}
        for i, pair in enumerate(relevant_pairs, 1):
            qa_context_parts.append(
                f"Пара {i} (ID={pair.id}):\n"
                f"  Вопрос: {pair.question_text[:3500]}\n"
                f"  Ответ: {pair.answer_text[:3500]}"
            )
            if pair.id:
                pair_id_map[i] = pair.id

        qa_context = "\n\n".join(qa_context_parts)

        # Сгенерировать ответ через LLM
        prompt = ANSWER_GENERATION_PROMPT.format(qa_context=qa_context)
        provider = get_provider("deepseek")

        try:
            raw = await provider.chat(
                messages=[{"role": "user", "content": f"Вопрос пользователя: {query}"}],
                system_prompt=prompt,
                purpose="gk_answer",
                model_override=self._model_name,
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

            if not source_pair_ids and relevant_pairs and relevant_pairs[0].id:
                source_pair_ids.append(relevant_pairs[0].id)

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
            }
        except Exception as exc:
            logger.error(
                "Ошибка генерации ответа: query=%s error=%s",
                query[:100], exc,
                exc_info=True,
            )
            return None

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

        # Вычислить BM25-scores для всего корпуса
        scores = self._score_corpus_bm25(self._corpus_tokens, query_tokens)

        # Собрать результаты с ненулевым score
        scored: List[Tuple[QAPair, float]] = []
        for idx, score in enumerate(scores):
            if score > 0 and idx < len(self._corpus_pairs):
                scored.append((self._corpus_pairs[idx], score))

        scored.sort(key=lambda x: x[1], reverse=True)

        logger.info(
            "GK BM25: query_tokens_head=%s query_tokens_tail=%s query_tokens_total=%d "
            "raw_tokens_total=%d removed_short_tokens=%d removed_stopwords=%s removed_stopwords_count=%d "
            "corpus_size=%d scored_count=%d top_score=%.4f",
            query_tokens[:10],
            query_tokens[-5:] if len(query_tokens) > 10 else query_tokens,
            len(query_tokens),
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
        latest_signature = gk_db.get_approved_qa_pairs_corpus_signature()

        ttl_not_expired = self._corpus_pairs and (now - self._corpus_loaded_at) < ttl
        signature_unchanged = latest_signature is not None and latest_signature == self._corpus_signature

        if ttl_not_expired and signature_unchanged:
            return

        if latest_signature is not None and self._corpus_signature is not None and latest_signature != self._corpus_signature:
            logger.info(
                "GK BM25: обнаружено изменение версии корпуса: old=%s new=%s",
                self._corpus_signature,
                latest_signature,
            )

        try:
            pairs = gk_db.get_all_approved_qa_pairs()
            corpus_tokens = []
            for pair in pairs:
                text = f"{pair.question_text} {pair.answer_text}"
                tokens = self._tokenize(text)
                corpus_tokens.append(tokens)

            self._corpus_pairs = pairs
            self._corpus_tokens = corpus_tokens
            self._corpus_loaded_at = now
            self._corpus_signature = latest_signature or self._build_corpus_signature_from_pairs(pairs)

            logger.info(
                "GK BM25: корпус загружен — %d Q&A-пар, avg_tokens=%.1f signature=%s",
                len(pairs),
                (sum(len(t) for t in corpus_tokens) / max(len(corpus_tokens), 1)),
                self._corpus_signature,
            )
        except Exception as exc:
            logger.error("GK BM25: ошибка загрузки корпуса: %s", exc, exc_info=True)

    def invalidate_corpus_cache(self) -> None:
        """Инвалидировать кэш корпуса (вызывается после добавления новых пар)."""
        self._corpus_loaded_at = 0.0
        self._corpus_pairs = []
        self._corpus_tokens = []
        self._corpus_signature = None

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
            from src.core.ai.vector_search import LocalVectorIndex, LocalEmbeddingProvider

            embedding_provider = LocalEmbeddingProvider()
            collection_name = ai_settings.GK_QA_VECTOR_COLLECTION
            vector_index = LocalVectorIndex(chunk_collection_name=collection_name)

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
            for hit in hits:
                pair_id = getattr(hit, "document_id", 0)
                if not pair_id:
                    continue

                pair = gk_db.get_qa_pair_by_id(int(pair_id))
                if not pair:
                    continue

                score = float(getattr(hit, "score", 0.0) or 0.0)
                results.append((pair, score))

            logger.info(
                "GK Vector: query=%s hits=%d results=%d top_score=%.4f",
                query[:80],
                len(hits),
                len(results),
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
            bm25_results: Кандидаты от BM25 [(QAPair, score), ...], отсортированные по score desc.
            vector_results: Кандидаты от vector [(QAPair, score), ...], отсортированные по score desc.
            top_k: Число финальных результатов.

        Returns:
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

        return rrf_scored[:top_k], diagnostics[:top_k]

    @staticmethod
    def _log_rrf_diagnostics(query: str, diagnostics: List[Dict]) -> None:
        """Залогировать диагностическую таблицу RRF-результатов."""
        if not diagnostics:
            return

        lines = [
            f"GK RRF-поиск: query=\"{query[:100]}\" top_results={len(diagnostics)}"
        ]
        for i, d in enumerate(diagnostics, 1):
            bm25_r = f"bm25_rank={d['bm25_rank']}" if d["bm25_rank"] is not None else "bm25_rank=—"
            vec_r = f"vec_rank={d['vector_rank']}" if d["vector_rank"] is not None else "vec_rank=—"
            lines.append(
                f"  #{i} pair={d['pair_id']} rrf={d['rrf_score']:.6f} "
                f"{bm25_r} bm25_score={d['bm25_score']:.4f} "
                f"{vec_r} vec_score={d['vector_score']:.4f} "
                f"q=\"{d['question_preview']}\""
            )

        logger.info("\n".join(lines))

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
        raw_tokens = _TOKEN_RE.findall((text or "").lower())
        tokens = [
            token
            for token in raw_tokens
            if len(token) >= 3
            or token in _GK_FIXED_TERMS
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
        raw_tokens = _TOKEN_RE.findall((text or "").lower())
        length_filtered_tokens = [
            token
            for token in raw_tokens
            if len(token) >= 3
            or token in _GK_FIXED_TERMS
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
        safe_token = (token or "").strip().lower()
        if not safe_token:
            return ""

        if safe_token in _GK_FIXED_TERMS:
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
