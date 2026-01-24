"""
Base Module for Telegram Bot

This module provides the base class that all bot modules should inherit from.
It defines the interface for creating modular, independent bot components.

Users can create their own modules by:
1. Creating a new directory under src/sbs_helper_telegram_bot/
2. Creating required files: __init__.py, messages.py, settings.py, keyboards.py
3. Creating a main bot part file that inherits from BotModule
4. Registering the module in the main telegram_bot.py

Example module structure:
    my_module/
        __init__.py
        messages.py          # Module-specific messages
        settings.py          # Module-specific settings
        keyboards.py         # Module-specific keyboards
        my_module_bot_part.py  # Main bot handlers
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import BaseHandler, ContextTypes


class BotModule(ABC):
    """
    Abstract base class for all bot modules.
    
    Each module should:
    - Have its own messages, settings, and keyboards
    - Implement get_handlers() to register Telegram handlers
    - Implement get_menu_button() to add a button to main menu (optional)
    - Be as independent as possible from other modules
    
    Attributes:
        name: Human-readable module name
        description: Brief description of what the module does
        version: Module version string
        author: Module author
    """
    
    def __init__(self):
        self._enabled = True
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable module name."""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """Brief description of what the module does."""
        pass
    
    @property
    def version(self) -> str:
        """Module version string."""
        return "1.0.0"
    
    @property
    def author(self) -> str:
        """Module author."""
        return "Unknown"
    
    @property
    def enabled(self) -> bool:
        """Whether the module is enabled."""
        return self._enabled
    
    @enabled.setter
    def enabled(self, value: bool):
        """Enable or disable the module."""
        self._enabled = value
    
    @abstractmethod
    def get_handlers(self) -> List[BaseHandler]:
        """
        Return a list of Telegram handlers for this module.
        
        These handlers will be registered with the Application.
        Order matters - handlers are checked in order of registration.
        
        Returns:
            List of telegram.ext handlers (CommandHandler, MessageHandler, etc.)
        """
        pass
    
    @abstractmethod
    def get_menu_button(self) -> Optional[str]:
        """
        Return the text for main menu button, or None if no button needed.
        
        The button text should be unique and include an emoji for visual distinction.
        Example: "✅ Валидация заявок"
        
        Returns:
            Button text string or None
        """
        pass
    
    @abstractmethod
    async def handle_menu_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """
        Handle when user clicks this module's menu button.
        
        Args:
            update: Telegram Update object
            context: Telegram context
            
        Returns:
            True if this module handled the button, False otherwise
        """
        pass
    
    def get_commands(self) -> Dict[str, str]:
        """
        Return a dict of commands and their descriptions for bot menu.
        
        Override this to add commands to the Telegram bot menu.
        
        Returns:
            Dict mapping command name (without /) to description
            Example: {"validate": "Проверить заявку"}
        """
        return {}
    
    def get_submenu_keyboard(self, user_id: int) -> Optional[ReplyKeyboardMarkup]:
        """
        Return submenu keyboard for this module, if applicable.
        
        Override this if your module has a submenu.
        user_id can be used to show different buttons to different users (e.g., admins).
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            ReplyKeyboardMarkup or None
        """
        return None
    
    async def on_module_loaded(self):
        """
        Called when the module is loaded.
        
        Override for initialization tasks like loading data from database.
        """
        pass
    
    async def on_module_unloaded(self):
        """
        Called when the module is unloaded.
        
        Override for cleanup tasks.
        """
        pass
    
    def get_admin_handlers(self) -> List[BaseHandler]:
        """
        Return admin-specific handlers for this module.
        
        Override if your module has admin functionality.
        
        Returns:
            List of telegram.ext handlers for admin features
        """
        return []
    
    def __repr__(self) -> str:
        return f"<BotModule: {self.name} v{self.version}>"


class ModuleRegistry:
    """
    Registry for managing bot modules.
    
    Provides methods to register, unregister, and query modules.
    """
    
    def __init__(self):
        self._modules: Dict[str, BotModule] = {}
    
    def register(self, module: BotModule) -> None:
        """
        Register a module.
        
        Args:
            module: BotModule instance to register
            
        Raises:
            ValueError: If module with same name already registered
        """
        if module.name in self._modules:
            raise ValueError(f"Module '{module.name}' is already registered")
        self._modules[module.name] = module
    
    def unregister(self, name: str) -> Optional[BotModule]:
        """
        Unregister a module by name.
        
        Args:
            name: Module name to unregister
            
        Returns:
            The unregistered module, or None if not found
        """
        return self._modules.pop(name, None)
    
    def get(self, name: str) -> Optional[BotModule]:
        """Get a module by name."""
        return self._modules.get(name)
    
    def get_all(self) -> List[BotModule]:
        """Get all registered modules."""
        return list(self._modules.values())
    
    def get_enabled(self) -> List[BotModule]:
        """Get all enabled modules."""
        return [m for m in self._modules.values() if m.enabled]
    
    def get_menu_buttons(self) -> List[str]:
        """Get menu buttons from all enabled modules."""
        buttons = []
        for module in self.get_enabled():
            button = module.get_menu_button()
            if button:
                buttons.append(button)
        return buttons
    
    def get_all_handlers(self) -> List[BaseHandler]:
        """Get handlers from all enabled modules."""
        handlers = []
        for module in self.get_enabled():
            handlers.extend(module.get_handlers())
            handlers.extend(module.get_admin_handlers())
        return handlers
    
    def get_all_commands(self) -> Dict[str, str]:
        """Get commands from all enabled modules."""
        commands = {}
        for module in self.get_enabled():
            commands.update(module.get_commands())
        return commands


# Global module registry
module_registry = ModuleRegistry()
