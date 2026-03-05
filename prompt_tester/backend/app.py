"""FastAPI-приложение тестера промптов.

Предоставляет REST API для:
- CRUD пар промптов (system_prompt + user_message)
- Создания и управления тестовыми сессиями
- Слепого попарного голосования
- Просмотра результатов с Elo-рейтингом

Запуск: python -m prompt_tester
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import sys
import os
from itertools import combinations
from pathlib import Path
from typing import Any, Dict, List, Optional

# Добавляем корень проекта в sys.path для импорта src.*
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from prompt_tester.backend import db, document_sampler, llm_judge, scoring, summary_generator
from prompt_tester.backend.models import (
    AggregateResults,
    ComparisonResponse,
    DocumentContentResponse,
    PromptCreate,
    PromptResponse,
    PromptUpdate,
    SessionCreate,
    SessionListItem,
    SessionResponse,
    SessionResults,
    VoteRequest,
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Prompt Tester",
    description="Слепое A/B тестирование промптов для генерации summary",
    version="1.0.0",
)

# CORS для dev-сервера React (Vite на :5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Статика (React build)
# ---------------------------------------------------------------------------

_FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


@app.on_event("startup")
async def _mount_static() -> None:
    """Подключить статику React-билда если она существует."""
    if _FRONTEND_DIST.is_dir():
        app.mount("/assets", StaticFiles(directory=str(_FRONTEND_DIST / "assets")), name="assets")
        logger.info("Статика React подключена из %s", _FRONTEND_DIST)
    else:
        logger.warning("React build не найден: %s — запустите npm run build", _FRONTEND_DIST)


@app.get("/")
async def serve_index() -> FileResponse:
    """Главная страница — React SPA."""
    index_file = _FRONTEND_DIST / "index.html"
    if index_file.is_file():
        return FileResponse(str(index_file))
    raise HTTPException(404, "React build не найден. Запустите: cd prompt_tester/frontend && npm run build")


# ---------------------------------------------------------------------------
# API: Промпты (CRUD)
# ---------------------------------------------------------------------------


@app.get("/api/prompts")
async def api_list_prompts(active_only: bool = True) -> List[Dict[str, Any]]:
    """Получить список пар промптов."""
    rows = db.list_prompts(active_only=active_only)
    return rows


@app.post("/api/prompts", status_code=201)
async def api_create_prompt(body: PromptCreate) -> Dict[str, Any]:
    """Создать новую пару промптов."""
    prompt_id = db.create_prompt(
        label=body.label,
        system_prompt_template=body.system_prompt_template,
        user_message=body.user_message,
        model_name=body.model_name,
        temperature=body.temperature,
    )
    return {"id": prompt_id, "message": "Пара промптов создана"}


@app.get("/api/prompts/{prompt_id}")
async def api_get_prompt(prompt_id: int) -> Dict[str, Any]:
    """Получить пару промптов по ID."""
    row = db.get_prompt(prompt_id)
    if not row:
        raise HTTPException(404, "Промпт не найден")
    return row


@app.put("/api/prompts/{prompt_id}")
async def api_update_prompt(prompt_id: int, body: PromptUpdate) -> Dict[str, Any]:
    """Обновить пару промптов."""
    fields: Dict[str, Any] = {}
    if body.label is not None:
        fields["label"] = body.label
    if body.system_prompt_template is not None:
        fields["system_prompt_template"] = body.system_prompt_template
    if body.user_message is not None:
        fields["user_message"] = body.user_message
    if body.model_name is not None:
        fields["model_name"] = body.model_name
    if body.clear_model_name:
        fields["model_name"] = None
    if body.temperature is not None:
        fields["temperature"] = body.temperature
    if body.clear_temperature:
        fields["temperature"] = None

    if not fields:
        raise HTTPException(400, "Нет полей для обновления")

    success = db.update_prompt(prompt_id, **fields)
    if not success:
        raise HTTPException(404, "Промпт не найден")
    return {"message": "Промпт обновлён"}


@app.delete("/api/prompts/{prompt_id}")
async def api_delete_prompt(prompt_id: int) -> Dict[str, Any]:
    """Архивировать пару промптов (мягкое удаление)."""
    success = db.delete_prompt(prompt_id)
    if not success:
        raise HTTPException(404, "Промпт не найден")
    return {"message": "Промпт архивирован"}


@app.post("/api/prompts/{prompt_id}/duplicate", status_code=201)
async def api_duplicate_prompt(prompt_id: int) -> Dict[str, Any]:
    """Клонировать пару промптов."""
    new_id = db.duplicate_prompt(prompt_id)
    if new_id is None:
        raise HTTPException(404, "Промпт не найден")
    return {"id": new_id, "message": "Промпт клонирован"}


@app.get("/api/prompts/{prompt_id}/preview")
async def api_preview_prompt(prompt_id: int) -> Dict[str, Any]:
    """Предпросмотр промпта с подстановкой переменных из случайного документа."""
    prompt = db.get_prompt(prompt_id)
    if not prompt:
        raise HTTPException(404, "Промпт не найден")

    doc = db.get_random_document_for_preview()
    if not doc:
        raise HTTPException(404, "Нет доступных документов для предпросмотра")

    from config import ai_settings

    excerpt = (doc.get("excerpt") or "")[:int(ai_settings.AI_RAG_SUMMARY_INPUT_MAX_CHARS)]

    rendered = summary_generator.render_system_prompt(
        template=prompt["system_prompt_template"],
        document_name=doc["filename"],
        document_excerpt=excerpt,
    )
    return {
        "document_name": doc["filename"],
        "rendered_system_prompt": rendered,
        "user_message": prompt["user_message"],
        "excerpt_length": len(excerpt),
    }


# ---------------------------------------------------------------------------
# API: Сессии
# ---------------------------------------------------------------------------


@app.get("/api/sessions")
async def api_list_sessions() -> List[Dict[str, Any]]:
    """Получить список тестовых сессий."""
    rows = db.list_sessions()
    result = []
    for row in rows:
        prompt_ids = row.get("prompt_ids_snapshot", [])
        doc_ids = row.get("document_ids", [])
        result.append({
            "id": row["id"],
            "name": row["name"],
            "status": row["status"],
            "total_comparisons": row["total_comparisons"],
            "completed_comparisons": row["completed_comparisons"],
            "judge_mode": row["judge_mode"],
            "prompt_count": len(prompt_ids) if isinstance(prompt_ids, list) else 0,
            "document_count": len(doc_ids) if isinstance(doc_ids, list) else 0,
            "created_at": str(row["created_at"]),
        })
    return result


@app.post("/api/sessions", status_code=201)
async def api_create_session(body: SessionCreate, background_tasks: BackgroundTasks) -> Dict[str, Any]:
    """Создать тестовую сессию и запустить генерацию summary в фоне."""
    # Проверяем промпты
    prompts = db.get_prompts_by_ids(body.prompt_ids)
    found_ids = {p["id"] for p in prompts}
    missing = [pid for pid in body.prompt_ids if pid not in found_ids]
    if missing:
        raise HTTPException(400, f"Промпты не найдены: {missing}")

    if len(prompts) < 2:
        raise HTTPException(400, "Необходимо минимум 2 активных промпта")

    # Выбираем документы
    document_ids = document_sampler.sample_documents(body.document_count)
    if len(document_ids) < 2:
        raise HTTPException(400, "Недостаточно документов для тестирования (нужно >= 2)")

    # Подсчитываем попарные сравнения
    num_pairs = len(list(combinations(prompts, 2)))
    total_comparisons = len(document_ids) * num_pairs

    # Создаём snapshot конфигурации
    prompts_config = []
    for p in prompts:
        prompts_config.append({
            "id": p["id"],
            "label": p["label"],
            "system_prompt_template": p["system_prompt_template"],
            "user_message": p["user_message"],
            "model_name": p.get("model_name"),
            "temperature": p.get("temperature"),
        })

    prompt_ids = [p["id"] for p in prompts]
    session_id = db.create_session(
        name=body.name,
        prompt_ids=prompt_ids,
        prompts_config=prompts_config,
        document_ids=document_ids,
        total_comparisons=total_comparisons,
        judge_mode=body.judge_mode,
    )

    # Запускаем генерацию в фоне
    background_tasks.add_task(
        _generate_all_summaries,
        session_id=session_id,
        prompts_config=prompts_config,
        document_ids=document_ids,
        judge_mode=body.judge_mode,
    )

    return {
        "id": session_id,
        "message": "Сессия создана, генерация summary запущена",
        "total_comparisons": total_comparisons,
        "document_count": len(document_ids),
    }


@app.get("/api/sessions/{session_id}")
async def api_get_session(session_id: int) -> Dict[str, Any]:
    """Получить детали сессии."""
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(404, "Сессия не найдена")
    # Конвертируем datetime в str для JSON
    for key in ("created_at", "updated_at"):
        if session.get(key):
            session[key] = str(session[key])
    return session


@app.get("/api/sessions/{session_id}/next")
async def api_get_next_comparison(session_id: int) -> Dict[str, Any]:
    """Получить следующую пару для слепого сравнения."""
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(404, "Сессия не найдена")

    if session["status"] == "generating":
        # Подсчитываем прогресс генерации
        gen_done = db.count_generations(session_id)
        prompt_ids = session.get("prompt_ids_snapshot", [])
        doc_ids = session.get("document_ids", [])
        gen_total = len(prompt_ids) * len(doc_ids) if isinstance(prompt_ids, list) and isinstance(doc_ids, list) else 0
        raise HTTPException(409, detail={
            "message": "Генерация summary ещё не завершена",
            "generated": gen_done,
            "total": gen_total,
            "phase": "generating",
        })

    if session["status"] == "judging":
        # LLM-as-Judge ещё работает — показываем прогресс оценки
        raise HTTPException(409, detail={
            "message": "LLM\u2011as\u2011Judge оценивает summary",
            "generated": session["completed_comparisons"],
            "total": session["total_comparisons"],
            "phase": "judging",
        })

    if session["status"] in ("completed", "abandoned"):
        return {"has_more": False, "progress": {
            "completed": session["completed_comparisons"],
            "total": session["total_comparisons"],
        }}

    next_pair = db.get_next_comparison(session_id)
    if not next_pair:
        # Все пары оценены
        db.update_session_status(session_id, "completed")
        return {"has_more": False, "progress": {
            "completed": session["completed_comparisons"],
            "total": session["total_comparisons"],
        }}

    # Рандомизируем порядок A/B
    gen_a = next_pair["generation_a"]
    gen_b = next_pair["generation_b"]
    if random.random() < 0.5:
        gen_a, gen_b = gen_b, gen_a

    doc_content = db.get_document_content(next_pair["document_id"])
    doc_name = doc_content["filename"] if doc_content else f"document_{next_pair['document_id']}"

    return {
        "document_id": next_pair["document_id"],
        "document_name": doc_name,
        "generation_a": {"id": gen_a["id"], "summary_text": gen_a["summary_text"]},
        "generation_b": {"id": gen_b["id"], "summary_text": gen_b["summary_text"]},
        "progress": {
            "completed": session["completed_comparisons"],
            "total": session["total_comparisons"],
        },
        "has_more": True,
    }


@app.get("/api/sessions/{session_id}/document/{document_id}")
async def api_get_document_content(session_id: int, document_id: int) -> Dict[str, Any]:
    """Получить содержимое документа для просмотра при оценке."""
    # Проверяем что документ относится к сессии
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(404, "Сессия не найдена")

    doc_ids = session.get("document_ids", [])
    if document_id not in doc_ids:
        raise HTTPException(403, "Документ не относится к этой сессии")

    content = db.get_document_content(document_id)
    if not content:
        raise HTTPException(404, "Документ не найден")
    return content


@app.post("/api/sessions/{session_id}/vote")
async def api_vote(session_id: int, body: VoteRequest) -> Dict[str, Any]:
    """Записать голос человеческого оценщика."""
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(404, "Сессия не найдена")

    if session["status"] not in ("in_progress",):
        raise HTTPException(
            409,
            f"Голосование недоступно: статус сессии = {session['status']}",
        )

    # Определяем document_id из генерации
    generations = db.get_generations_for_session(session_id)
    gen_map = {g["id"]: g for g in generations}

    gen_a = gen_map.get(body.generation_a_id)
    gen_b = gen_map.get(body.generation_b_id)
    if not gen_a or not gen_b:
        raise HTTPException(400, "Генерации не найдены в данной сессии")

    if gen_a["document_id"] != gen_b["document_id"]:
        raise HTTPException(400, "Генерации относятся к разным документам")

    vote_id = db.insert_vote(
        session_id=session_id,
        document_id=gen_a["document_id"],
        generation_a_id=body.generation_a_id,
        generation_b_id=body.generation_b_id,
        winner=body.winner,
        judge_type="human",
    )

    db.increment_completed_comparisons(session_id)

    # Проверяем, не завершена ли сессия
    updated_session = db.get_session(session_id)
    if updated_session and updated_session["completed_comparisons"] >= updated_session["total_comparisons"]:
        db.update_session_status(session_id, "completed")

    return {"vote_id": vote_id, "message": "Голос записан"}


# ---------------------------------------------------------------------------
# API: Результаты
# ---------------------------------------------------------------------------


@app.get("/api/sessions/{session_id}/results")
async def api_get_results(session_id: int) -> Dict[str, Any]:
    """Получить результаты тестовой сессии."""
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(404, "Сессия не найдена")

    prompts_config = session.get("prompts_config_snapshot", [])

    # Human votes
    human_votes = db.get_votes_for_session(session_id, judge_type="human")
    human_results = scoring.compute_results(human_votes, prompts_config)

    # LLM votes
    llm_votes = db.get_votes_for_session(session_id, judge_type="llm")
    llm_results = scoring.compute_results(llm_votes, prompts_config) if llm_votes else []

    # Разбивка по документам (только human)
    all_votes = human_votes + llm_votes
    doc_breakdown = scoring.compute_document_breakdown(human_votes, prompts_config)

    return {
        "session_id": session_id,
        "session_name": session["name"],
        "status": session["status"],
        "human_results": human_results,
        "llm_results": llm_results,
        "document_breakdown": doc_breakdown,
    }


@app.get("/api/results/aggregate")
async def api_get_aggregate_results() -> Dict[str, Any]:
    """Агрегированные результаты по всем сессиям."""
    sessions = db.list_sessions()
    if not sessions:
        return {"prompt_results": [], "sessions_count": 0, "total_votes": 0}

    all_votes: List[Dict[str, Any]] = []
    all_configs: List[List[Dict[str, Any]]] = []

    for sess in sessions:
        full_session = db.get_session(sess["id"])
        if not full_session:
            continue
        votes = db.get_votes_for_session(sess["id"])
        all_votes.extend(votes)
        config = full_session.get("prompts_config_snapshot", [])
        if config:
            all_configs.append(config)

    return scoring.compute_aggregate_results(all_votes, all_configs)


# ---------------------------------------------------------------------------
# Фоновая генерация summary
# ---------------------------------------------------------------------------


async def _generate_all_summaries(
    *,
    session_id: int,
    prompts_config: List[Dict[str, Any]],
    document_ids: List[int],
    judge_mode: str,
) -> None:
    """Сгенерировать summary для всех документов × промптов (фоновая задача)."""
    logger.info(
        "Начинаем генерацию summary: session_id=%s documents=%d prompts=%d",
        session_id, len(document_ids), len(prompts_config),
    )

    generations_map: Dict[int, Dict[int, Dict[str, Any]]] = {}  # doc_id -> prompt_id -> generation

    for doc_id in document_ids:
        content = db.get_document_content(doc_id)
        if not content:
            logger.warning("Документ %d не найден, пропускаем", doc_id)
            continue

        chunks = content.get("chunks", [])
        doc_name = content.get("filename", f"document_{doc_id}")
        generations_map[doc_id] = {}

        for prompt_cfg in prompts_config:
            prompt_id = prompt_cfg["id"]
            try:
                result = await summary_generator.generate_summary(
                    system_prompt_template=prompt_cfg["system_prompt_template"],
                    user_message=prompt_cfg["user_message"],
                    document_name=doc_name,
                    chunks=chunks,
                    model_name=prompt_cfg.get("model_name"),
                    temperature=prompt_cfg.get("temperature"),
                )

                gen_id = db.insert_generation(
                    session_id=session_id,
                    document_id=doc_id,
                    prompt_id=prompt_id,
                    prompt_label=prompt_cfg["label"],
                    system_prompt_used=result["system_prompt_used"],
                    user_message_used=result["user_message_used"],
                    model_name=result.get("model_name"),
                    temperature_used=result.get("temperature_used"),
                    summary_text=result.get("summary_text"),
                    generation_time_ms=result.get("generation_time_ms", 0),
                    error_message=result.get("error_message"),
                )

                generations_map[doc_id][prompt_id] = {
                    "id": gen_id,
                    "summary_text": result.get("summary_text"),
                    "prompt_label": prompt_cfg["label"],
                }

                logger.info(
                    "Summary сгенерирован: session=%d doc=%d prompt=%s time=%dms",
                    session_id, doc_id, prompt_cfg["label"],
                    result.get("generation_time_ms", 0),
                )

            except Exception as exc:
                logger.error(
                    "Ошибка генерации: session=%d doc=%d prompt=%s error=%s",
                    session_id, doc_id, prompt_cfg["label"], exc,
                    exc_info=True,
                )
                db.insert_generation(
                    session_id=session_id,
                    document_id=doc_id,
                    prompt_id=prompt_id,
                    prompt_label=prompt_cfg["label"],
                    system_prompt_used="",
                    user_message_used=prompt_cfg["user_message"],
                    error_message=str(exc),
                )

    # Обновляем статус сессии
    logger.info("Генерация summary завершена: session_id=%s", session_id)

    # LLM-as-Judge если включён
    if judge_mode in ("llm", "both"):
        db.update_session_status(session_id, "judging")
        logger.info("Запуск LLM-as-Judge: session_id=%s", session_id)
        await _run_llm_judge(session_id, generations_map, document_ids)

        if judge_mode == "llm":
            # Только LLM — сессия завершена, человеческая оценка не нужна
            db.update_session_status(session_id, "completed")
            logger.info("LLM-only режим: сессия автоматически завершена: session_id=%s", session_id)
        else:
            # Режим 'both' — переходим к человеческой оценке
            db.update_session_status(session_id, "in_progress")
            logger.info("LLM-as-Judge завершён, переходим к человеческой оценке: session_id=%s", session_id)
    else:
        # Только человеческая оценка
        db.update_session_status(session_id, "in_progress")
        logger.info("Сессия готова к человеческой оценке: session_id=%s", session_id)


async def _run_llm_judge(
    session_id: int,
    generations_map: Dict[int, Dict[int, Dict[str, Any]]],
    document_ids: List[int],
) -> None:
    """Запустить LLM-as-Judge для всех пар в сессии."""
    logger.info("Запускаем LLM-as-Judge: session_id=%s", session_id)

    for doc_id in document_ids:
        doc_gens = generations_map.get(doc_id, {})
        if len(doc_gens) < 2:
            continue

        content = db.get_document_content(doc_id)
        if not content:
            continue

        excerpt = summary_generator.build_summary_excerpt(content.get("chunks", []))
        doc_name = content.get("filename", f"document_{doc_id}")

        gen_items = list(doc_gens.values())
        for gen_a, gen_b in combinations(gen_items, 2):
            if not gen_a.get("summary_text") or not gen_b.get("summary_text"):
                continue

            try:
                judge_result = await llm_judge.judge_pair(
                    document_name=doc_name,
                    document_excerpt=excerpt,
                    summary_a=gen_a["summary_text"],
                    summary_b=gen_b["summary_text"],
                    prompt_a_label=gen_a.get("prompt_label", "A"),
                    prompt_b_label=gen_b.get("prompt_label", "B"),
                )

                db.insert_vote(
                    session_id=session_id,
                    document_id=doc_id,
                    generation_a_id=gen_a["id"],
                    generation_b_id=gen_b["id"],
                    winner=judge_result["winner"],
                    judge_type="llm",
                    llm_judge_reasoning=judge_result.get("reasoning"),
                )
                db.increment_completed_comparisons(session_id)

            except Exception as exc:
                logger.warning(
                    "LLM Judge ошибка: session=%d doc=%d error=%s",
                    session_id, doc_id, exc,
                )

    logger.info("LLM-as-Judge завершён: session_id=%s", session_id)


# ---------------------------------------------------------------------------
# Catch-all для React SPA (все неизвестные пути → index.html)
# ---------------------------------------------------------------------------


@app.get("/{full_path:path}")
async def serve_spa(full_path: str) -> FileResponse:
    """Serve React SPA для клиентского роутинга."""
    if full_path.startswith("api/"):
        raise HTTPException(404, "API endpoint не найден")

    # Проверяем файл в dist
    file_path = _FRONTEND_DIST / full_path
    if file_path.is_file():
        return FileResponse(str(file_path))

    # Fallback на index.html для SPA routing
    index_file = _FRONTEND_DIST / "index.html"
    if index_file.is_file():
        return FileResponse(str(index_file))
    raise HTTPException(404, "React build не найден")


# ---------------------------------------------------------------------------
# Точка входа
# ---------------------------------------------------------------------------


def main() -> None:
    """Запустить сервер."""
    import uvicorn

    # Настраиваем формат логов с timestamp
    log_format = "%(asctime)s %(levelname)s %(name)s: %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"
    logging.basicConfig(level=logging.INFO, format=log_format, datefmt=date_format)

    port = int(os.getenv("PROMPT_TESTER_PORT", "8080"))
    host = os.getenv("PROMPT_TESTER_HOST", "127.0.0.1")

    logger.info("Запуск Prompt Tester: http://%s:%d", host, port)
    uvicorn.run(
        "prompt_tester.backend.app:app",
        host=host,
        port=port,
        reload=False,
        log_level="info",
        access_log=True,
        log_config={
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": log_format,
                    "datefmt": date_format,
                },
                "access": {
                    "()": "uvicorn.logging.AccessFormatter",
                    "fmt": '%(asctime)s %(levelname)s %(name)s: %(client_addr)s - "%(request_line)s" %(status_code)s',
                    "datefmt": date_format,
                },
            },
            "handlers": {
                "default": {"formatter": "default", "class": "logging.StreamHandler", "stream": "ext://sys.stderr"},
                "access": {"formatter": "access", "class": "logging.StreamHandler", "stream": "ext://sys.stdout"},
            },
            "loggers": {
                "uvicorn": {"handlers": ["default"], "level": "INFO"},
                "uvicorn.error": {"level": "INFO"},
                "uvicorn.access": {"handlers": ["access"], "level": "INFO", "propagate": False},
            },
        },
    )


if __name__ == "__main__":
    main()
