"""
Gamification Module

Achievement system, user profiles, rankings and score tracking.
"""

from .gamification_bot_part import get_gamification_user_handler
from .admin_panel_bot_part import get_gamification_admin_handler
from .events import emit_event, register_event, register_custom_handler
from .gamification_logic import add_score_points
from . import settings

__all__ = [
    'get_gamification_user_handler',
    'get_gamification_admin_handler',
    'emit_event',
    'register_event',
    'register_custom_handler',
    'add_score_points',
    'settings',
]
