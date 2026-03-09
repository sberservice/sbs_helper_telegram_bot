"""Pydantic-модели для модуля управления процессами.

Определяет структуры данных для API, реестра процессов и истории запусков.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Перечисления
# ---------------------------------------------------------------------------


class ProcessType(str, Enum):
    """Тип процесса."""
    DAEMON = "daemon"
    ONE_SHOT = "one_shot"


class ProcessStatus(str, Enum):
    """Текущий статус процесса."""
    RUNNING = "running"
    STOPPED = "stopped"
    CRASHED = "crashed"
    STARTING = "starting"
    STOPPING = "stopping"
    UNKNOWN = "unknown"


class FlagType(str, Enum):
    """Тип CLI-флага."""
    BOOL = "bool"
    INT = "int"
    STRING = "string"
    CHOICE = "choice"


class StopReason(str, Enum):
    """Причина остановки процесса."""
    MANUAL = "manual"
    AUTO_RESTART = "auto_restart"
    CRASH = "crash"
    SHUTDOWN = "shutdown"
    SYSTEM_RESTART = "system_restart"


# ---------------------------------------------------------------------------
# Реестр: описание флагов, пресетов, процессов
# ---------------------------------------------------------------------------


class FlagDefinition(BaseModel):
    """Определение одного CLI-флага процесса."""
    name: str = Field(..., description="Имя флага (например, '--live')")
    flag_type: FlagType = Field(FlagType.BOOL, description="Тип значения")
    description: str = Field("", description="Описание для UI")
    default: Any = Field(None, description="Значение по умолчанию")
    choices: Optional[List[str]] = Field(None, description="Допустимые значения для CHOICE")
    mutually_exclusive_group: Optional[str] = Field(
        None, description="Группа взаимоисключающих флагов",
    )
    required: bool = Field(False, description="Обязательный ли флаг")


class PresetDefinition(BaseModel):
    """Определение пресета запуска — именованный набор флагов."""
    name: str = Field(..., description="Название пресета")
    description: str = Field("", description="Описание для UI")
    flags: List[str] = Field(default_factory=list, description="Список флагов в формате CLI")
    icon: str = Field("▶️", description="Иконка для UI")
    requires_form: bool = Field(
        False,
        description="Требует ли пресет заполнения формы перед запуском",
    )
    form_type: Optional[str] = Field(
        None,
        description="Тип формы для UI (например, 'gk_test_mode', 'gk_redirect_test', 'gk_delete_group')",
    )
    hidden: bool = Field(
        False,
        description="Скрыть пресет из UI (используется для --manage-groups и подобных CLI-only режимов)",
    )


class ProcessDefinition(BaseModel):
    """Полное определение процесса в реестре."""
    key: str = Field(..., description="Уникальный ключ процесса")
    name: str = Field(..., description="Человекочитаемое название")
    description: str = Field("", description="Описание процесса")
    icon: str = Field("📦", description="Иконка")
    category: str = Field("other", description="Категория для группировки")
    process_type: ProcessType = Field(ProcessType.DAEMON, description="Тип: daemon или one_shot")
    command: List[str] = Field(..., description="Команда запуска (sys.executable + аргументы)")
    singleton: bool = Field(True, description="Только один экземпляр одновременно")
    auto_restart: bool = Field(False, description="Авто-рестарт при падении (для daemon)")
    max_restart_attempts: int = Field(3, description="Максимум перезапусков подряд")
    restart_delay_seconds: int = Field(5, description="Пауза перед перезапуском")
    flags: List[FlagDefinition] = Field(default_factory=list, description="Доступные CLI-флаги")
    presets: List[PresetDefinition] = Field(default_factory=list, description="Предустановки запуска")


# ---------------------------------------------------------------------------
# API: запросы и ответы
# ---------------------------------------------------------------------------


class ProcessStartRequest(BaseModel):
    """Запрос на запуск процесса."""
    preset: Optional[str] = Field(None, description="Имя пресета")
    flags: Optional[List[str]] = Field(None, description="Список CLI-флагов")
    form_data: Optional[Dict[str, Any]] = Field(
        None,
        description="Данные из формы запуска (конвертируются в CLI-флаги)",
    )
    persist: Optional[bool] = Field(
        None,
        description=(
            "Сохранять ли процесс для авто-восстановления при перезагрузке сервера. "
            "None = авто (True для daemon, False для one_shot)."
        ),
    )


class ProcessStatusResponse(BaseModel):
    """Статус одного процесса."""
    key: str
    name: str
    icon: str
    category: str
    process_type: ProcessType
    status: ProcessStatus
    pid: Optional[int] = None
    uptime_seconds: Optional[float] = None
    current_flags: Optional[List[str]] = None
    current_preset: Optional[str] = None
    started_at: Optional[str] = None
    started_by: Optional[int] = None
    exit_code: Optional[int] = None
    auto_restart: bool = False
    singleton: bool = True
    description: str = ""


class ProcessRegistryResponse(BaseModel):
    """Описание процесса из реестра: флаги, пресеты."""
    key: str
    name: str
    icon: str
    category: str
    process_type: ProcessType
    description: str
    singleton: bool
    auto_restart: bool
    flags: List[FlagDefinition]
    presets: List[PresetDefinition]


class ProcessesByCategoryResponse(BaseModel):
    """Все процессы, сгруппированные по категориям."""
    categories: Dict[str, List[ProcessStatusResponse]]


class ProcessRunRecord(BaseModel):
    """Одна запись из истории запусков."""
    id: int
    process_key: str
    pid: Optional[int] = None
    flags: Optional[List[str]] = None
    preset_name: Optional[str] = None
    started_by: Optional[int] = None
    started_at: Optional[str] = None
    stopped_at: Optional[str] = None
    exit_code: Optional[int] = None
    status: str = "stopped"
    stop_reason: Optional[str] = None


class ProcessHistoryResponse(BaseModel):
    """Список записей истории запусков (с пагинацией)."""
    runs: List[ProcessRunRecord]
    total: int
    page: int
    page_size: int


class ProcessOutputResponse(BaseModel):
    """Выходные строки процесса из кольцевого буфера."""
    lines: List[Dict[str, str]]
    total_lines: int
