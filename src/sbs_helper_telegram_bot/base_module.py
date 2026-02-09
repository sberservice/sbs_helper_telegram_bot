"""
Базовый модуль для Telegram-бота.

Этот модуль содержит базовый класс, от которого должны наследоваться все
модули бота. Он определяет интерфейс для создания модульных и независимых
компонентов.

Как создать свой модуль:
1. Создать каталог под src/sbs_helper_telegram_bot/
2. Создать обязательные файлы: __init__.py, messages.py, settings.py, keyboards.py
3. Создать основной файл обработчиков, наследующийся от BotModule
4. Зарегистрировать модуль в основном telegram_bot.py

Пример структуры модуля:
    my_module/
        __init__.py
        messages.py          # Сообщения модуля
        settings.py          # Настройки модуля
        keyboards.py         # Клавиатуры модуля
        my_module_bot_part.py  # Основные обработчики
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import BaseHandler, ContextTypes


class BotModule(ABC):
    """
    Абстрактный базовый класс для всех модулей бота.
    
    Каждый модуль должен:
    - иметь свои messages, settings и keyboards;
    - реализовать `get_handlers()` для регистрации обработчиков;
    - реализовать `get_menu_button()` для добавления кнопки в главное меню (опционально);
    - быть максимально независимым от других модулей.
    
    Attributes:
        name: человекочитаемое имя модуля.
        description: краткое описание назначения модуля.
        version: строка версии модуля.
        author: автор модуля.
    """
    
    def __init__(self):
        self._enabled = True
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Человекочитаемое имя модуля."""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """Краткое описание назначения модуля."""
        pass
    
    @property
    def version(self) -> str:
        """Строка версии модуля."""
        return "1.0.0"
    
    @property
    def author(self) -> str:
        """Автор модуля."""
        return "Unknown"
    
    @property
    def enabled(self) -> bool:
        """Флаг включения модуля."""
        return self._enabled
    
    @enabled.setter
    def enabled(self, value: bool):
        """Включить или отключить модуль."""
        self._enabled = value
    
    @abstractmethod
    def get_handlers(self) -> List[BaseHandler]:
        """
        Вернуть список обработчиков Telegram для этого модуля.
        
        Эти обработчики будут зарегистрированы в Application.
        Порядок важен — обработчики проверяются в порядке регистрации.
        
        Returns:
            Список обработчиков telegram.ext (CommandHandler, MessageHandler и т. п.).
        """
        pass
    
    @abstractmethod
    def get_menu_button(self) -> Optional[str]:
        """
        Вернуть текст кнопки главного меню или None, если кнопка не нужна.
        
        Текст кнопки должен быть уникальным и содержать эмодзи для наглядности.
        Пример: "✅ Валидация заявок".
        
        Returns:
            Текст кнопки или None.
        """
        pass
    
    @abstractmethod
    async def handle_menu_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """
        Обработать нажатие кнопки меню этого модуля.
        
        Args:
            update: объект Telegram Update.
            context: контекст Telegram.
            
        Returns:
            True, если модуль обработал кнопку, иначе False.
        """
        pass
    
    def get_commands(self) -> Dict[str, str]:
        """
        Вернуть словарь команд и их описаний для меню бота.
        
        Переопределите, чтобы добавить команды в меню Telegram-бота.
        
        Returns:
            Словарь вида: имя команды (без /) -> описание.
            Пример: {"validate": "Проверить заявку"}.
        """
        return {}
    
    def get_submenu_keyboard(self, user_id: int) -> Optional[ReplyKeyboardMarkup]:
        """
        Вернуть клавиатуру подменю для этого модуля, если она есть.
        
        Переопределите, если модуль имеет подменю.
        `user_id` можно использовать для разных наборов кнопок (например, для админов).
        
        Args:
            user_id: идентификатор пользователя Telegram.
            
        Returns:
            ReplyKeyboardMarkup или None.
        """
        return None
    
    async def on_module_loaded(self):
        """
        Вызывается при загрузке модуля.
        
        Переопределите для инициализации, например, загрузки данных из БД.
        """
        pass
    
    async def on_module_unloaded(self):
        """
        Вызывается при выгрузке модуля.
        
        Переопределите для задач очистки.
        """
        pass
    
    def get_admin_handlers(self) -> List[BaseHandler]:
        """
        Вернуть админские обработчики для этого модуля.
        
        Переопределите, если модуль имеет функции администратора.
        
        Returns:
            Список обработчиков telegram.ext для админских функций.
        """
        return []
    
    def __repr__(self) -> str:
        return f"<BotModule: {self.name} v{self.version}>"


class ModuleRegistry:
    """
    Реестр для управления модулями бота.
    
    Предоставляет методы регистрации, удаления и поиска модулей.
    """
    
    def __init__(self):
        self._modules: Dict[str, BotModule] = {}
    
    def register(self, module: BotModule) -> None:
        """
        Зарегистрировать модуль.
        
        Args:
            module: экземпляр BotModule для регистрации.
            
        Raises:
            ValueError: если модуль с таким именем уже зарегистрирован.
        """
        if module.name in self._modules:
            raise ValueError(f"Module '{module.name}' is already registered")
        self._modules[module.name] = module
    
    def unregister(self, name: str) -> Optional[BotModule]:
        """
        Снять модуль с регистрации по имени.
        
        Args:
            name: имя модуля для удаления.
            
        Returns:
            Удалённый модуль или None, если модуль не найден.
        """
        return self._modules.pop(name, None)
    
    def get(self, name: str) -> Optional[BotModule]:
        """Получить модуль по имени."""
        return self._modules.get(name)
    
    def get_all(self) -> List[BotModule]:
        """Получить все зарегистрированные модули."""
        return list(self._modules.values())
    
    def get_enabled(self) -> List[BotModule]:
        """Получить все включённые модули."""
        return [m for m in self._modules.values() if m.enabled]
    
    def get_menu_buttons(self) -> List[str]:
        """Получить кнопки меню из всех включённых модулей."""
        buttons = []
        for module in self.get_enabled():
            button = module.get_menu_button()
            if button:
                buttons.append(button)
        return buttons
    
    def get_all_handlers(self) -> List[BaseHandler]:
        """Получить обработчики из всех включённых модулей."""
        handlers = []
        for module in self.get_enabled():
            handlers.extend(module.get_handlers())
            handlers.extend(module.get_admin_handlers())
        return handlers
    
    def get_all_commands(self) -> Dict[str, str]:
        """Получить команды из всех включённых модулей."""
        commands = {}
        for module in self.get_enabled():
            commands.update(module.get_commands())
        return commands


# Глобальный реестр модулей
module_registry = ModuleRegistry()
