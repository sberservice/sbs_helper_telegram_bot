"""
Модуль логики валидации.

Содержит правила, валидаторы и классы результатов для проверки заявок.
"""

import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum


class RuleType(Enum):
    """Типы правил валидации."""
    REGEX = "regex"
    REGEX_NOT_MATCH = "regex_not_match"
    REGEX_FULLMATCH = "regex_fullmatch"
    REGEX_NOT_FULLMATCH = "regex_not_fullmatch"
    FIAS_CHECK = "fias_check"
    CUSTOM = "custom"


@dataclass
class TicketType:
    """Описывает тип/шаблон заявки."""
    id: int
    type_name: str
    description: str
    detection_keywords: List[str]
    active: bool = True
    keyword_weights: Dict[str, float] = field(default_factory=dict)
    
    def get_keyword_weight(self, keyword: str) -> float:
        """
        Получить вес для ключевого слова.
        
        Args:
            keyword: ключевое слово, для которого нужен вес (без учёта регистра).
            
        Returns:
            Вес ключевого слова, по умолчанию 1.0.
        """
        return self.keyword_weights.get(keyword.lower(), 1.0)


@dataclass
class ValidationRule:
    """Описывает одно правило валидации."""
    id: int
    rule_name: str
    pattern: str
    rule_type: str
    error_message: str
    active: bool = True
    priority: int = 0
    
    def __post_init__(self):
        """Проверить и привести `rule_type` к Enum при необходимости."""
        if isinstance(self.rule_type, str):
            try:
                self.rule_type = RuleType(self.rule_type)
            except ValueError:
                # Оставляем строкой, если значение не является элементом Enum
                pass


@dataclass
class KeywordMatch:
    """Описывает совпадение по ключевому слову и его параметры."""
    keyword: str
    count: int
    weight: float = 1.0
    is_negative: bool = False
    
    @property
    def weighted_score(self) -> float:
        score = self.count * self.weight
        return -score if self.is_negative else score


@dataclass
class TicketTypeScore:
    """Детали оценки для типа заявки при определении."""
    ticket_type: TicketType
    total_score: float
    keyword_matches: List[KeywordMatch] = field(default_factory=list)
    matched_keywords_count: int = 0
    total_keywords_count: int = 0
    
    @property
    def match_percentage(self) -> float:
        """Процент совпавших ключевых слов."""
        if self.total_keywords_count == 0:
            return 0.0
        return (self.matched_keywords_count / self.total_keywords_count) * 100


@dataclass
class DetectionDebugInfo:
    """Отладочная информация по определению типа заявки."""
    detected_type: Optional[TicketType]
    all_scores: List[TicketTypeScore] = field(default_factory=list)
    ticket_text_preview: str = ""
    total_types_evaluated: int = 0
    has_ambiguity: bool = False
    ambiguous_types: List[TicketType] = field(default_factory=list)
    
    def get_summary(self) -> str:
        """Сформировать человекочитаемое резюме процесса определения типа."""
        lines = []
        lines.append("=" * 60)
        lines.append("TICKET TYPE DETECTION DEBUG INFO")
        lines.append("=" * 60)
        lines.append(f"Text preview: {self.ticket_text_preview[:100]}...")
        lines.append(f"Total ticket types evaluated: {self.total_types_evaluated}")
        lines.append("")
        
        if self.detected_type:
            lines.append(f"✅ DETECTED TYPE: {self.detected_type.type_name}")
            lines.append(f"   Description: {self.detected_type.description}")
            if self.has_ambiguity:
                ambiguous_names = ", ".join([tt.type_name for tt in self.ambiguous_types])
                lines.append(f"⚠️ WARNING: Multiple types have the same score: {ambiguous_names}")
        else:
            lines.append("❌ NO TYPE DETECTED")
        
        lines.append("")
        lines.append("-" * 60)
        lines.append("SCORES BY TICKET TYPE (sorted by score):")
        lines.append("-" * 60)
        
        # Сортировка по убыванию общего балла
        sorted_scores = sorted(self.all_scores, key=lambda x: x.total_score, reverse=True)
        
        for score_info in sorted_scores:
            lines.append("")
            lines.append(f"📋 {score_info.ticket_type.type_name}")
            lines.append(f"   Total Score: {score_info.total_score}")
            lines.append(f"   Keywords matched: {score_info.matched_keywords_count}/{score_info.total_keywords_count} ({score_info.match_percentage:.1f}%)")
            
            if score_info.keyword_matches:
                lines.append("   Matched keywords:")
                for match in score_info.keyword_matches:
                    sign = "-" if match.is_negative else "+"
                    lines.append(f"     {sign} '{match.keyword}': found {match.count}x (weight: {match.weight}, score: {match.weighted_score})")
            else:
                lines.append("   No keywords matched")
        
        lines.append("")
        lines.append("=" * 60)
        return "\n".join(lines)


@dataclass
class ValidationResult:
    """Результат проверки заявки."""
    is_valid: bool
    failed_rules: List[str] = field(default_factory=list)
    passed_rules: List[str] = field(default_factory=list)
    error_messages: List[str] = field(default_factory=list)
    validation_details: Dict[str, Any] = field(default_factory=dict)
    detected_ticket_type: Optional[TicketType] = None


def validate_regex(ticket_text: str, pattern: str) -> bool:
    """
    Проверить текст заявки по регулярному выражению.
    
    Args:
        ticket_text: текст заявки для проверки.
        pattern: регулярное выражение для поиска.
        
    Returns:
        True, если совпадение найдено, иначе False.
    """
    try:
        return bool(re.search(pattern, ticket_text, re.IGNORECASE | re.MULTILINE | re.UNICODE | re.DOTALL))
    except re.error:
        # Некорректное регулярное выражение
        return False


def validate_regex_not_match(ticket_text: str, pattern: str) -> bool:
    """
    Проверить текст заявки по регулярному выражению (инверсия совпадения).
    
    Args:
        ticket_text: текст заявки для проверки.
        pattern: регулярное выражение, которое НЕ должно совпасть.
        
    Returns:
        True, если совпадение НЕ найдено, иначе False.
    """
    try:
        return not bool(re.search(pattern, ticket_text, re.IGNORECASE | re.MULTILINE | re.UNICODE | re.DOTALL))
    except re.error:
        # Некорректное регулярное выражение — считаем, что совпадения нет
        return True


def validate_regex_fullmatch(ticket_text: str, pattern: str) -> bool:
    """
    Проверить текст заявки по регулярному выражению с `fullmatch`.
    
    Args:
        ticket_text: текст заявки для проверки.
        pattern: регулярное выражение, которое должно совпасть со всем текстом.
        
    Returns:
        True, если совпадает весь текст, иначе False.
    """
    try:
        return bool(re.fullmatch(pattern, ticket_text, re.IGNORECASE | re.MULTILINE | re.UNICODE | re.DOTALL))
    except re.error:
        # Некорректное регулярное выражение
        return False


def validate_regex_not_fullmatch(ticket_text: str, pattern: str) -> bool:
    """
    Проверить текст заявки по регулярному выражению с `fullmatch` (инверсия).
    
    Args:
        ticket_text: текст заявки для проверки.
        pattern: регулярное выражение, которое НЕ должно полностью совпасть.
        
    Returns:
        True, если полного совпадения нет, иначе False.
    """
    try:
        return not bool(re.fullmatch(pattern, ticket_text, re.IGNORECASE | re.MULTILINE | re.UNICODE | re.DOTALL))
    except re.error:
        # Некорректное регулярное выражение — считаем, что совпадения нет
        return True


def validate_fias_address(ticket_text: str, pattern: str) -> bool:
    """Проверить адрес из текста заявки по базе ФИАС.

    В *pattern* используется регулярное выражение, где **первая группа**
    содержит адрес. Например::

        Адрес установки POS-терминала:\\s*([\\s\\S]*?)(?=Тип пакета:|$)

    Извлечённый адрес передаётся активному провайдеру ФИАС
    (см. :mod:`fias_providers`). Правило **успешно**, если провайдер
    возвращает хотя бы одну подсказку.

    Если адрес не удаётся извлечь из текста, правило считается
    **проваленным** (возвращает ``False``).

    Args:
        ticket_text: полный текст заявки.
        pattern: регулярное выражение с группой для извлечения адреса.

    Returns:
        ``True``, если адрес найден в ФИАС, иначе ``False``.
    """
    try:
        match = re.search(pattern, ticket_text, re.IGNORECASE | re.MULTILINE | re.UNICODE | re.DOTALL)
        if not match or not match.group(1):
            return False

        address = match.group(1).strip()
        if not address:
            return False

        from .fias_providers import get_fias_provider

        provider = get_fias_provider()
        result = provider.validate_address(address)
        return result.is_valid

    except re.error:
        return False
    except Exception:  # noqa: BLE001 – разрешаем по умолчанию при неожиданных ошибках
        return True


def detect_ticket_type(
    ticket_text: str, 
    ticket_types: List[TicketType],
    debug: bool = False,
    keyword_weights: Optional[Dict[str, float]] = None
) -> tuple[Optional[TicketType], Optional[DetectionDebugInfo]]:
    """
    Определить тип заявки по ключевым словам.
    
    Args:
        ticket_text: текст заявки для анализа.
        ticket_types: список доступных типов заявок.
        debug: если True, вернуть подробную отладочную информацию.
        keyword_weights: словарь пользовательских весов ключевых слов (по умолчанию 1.0).
        
    Returns:
        Кортеж: (лучше всего подходящий тип заявки или None, DetectionDebugInfo при debug=True).
    """
    if not ticket_types:
        if debug:
            return None, DetectionDebugInfo(
                detected_type=None,
                ticket_text_preview=ticket_text[:200] if ticket_text else "",
                total_types_evaluated=0
            )
        return None, None
    
    # Нормализуем ключи keyword_weights к нижнему регистру для поиска без учёта регистра
    keyword_weights = {k.lower(): v for k, v in (keyword_weights or {}).items()}
    
    # Оцениваем каждый тип заявки по совпадениям ключевых слов
    scores = {}
    all_scores_debug: List[TicketTypeScore] = []
    ticket_text_lower = ticket_text.lower()
    active_types_count = 0
    
    for ticket_type in ticket_types:
        if not ticket_type.active:
            continue
        
        active_types_count += 1
        score = 0.0
        keyword_matches: List[KeywordMatch] = []
        matched_count = 0
        total_keywords = len(ticket_type.detection_keywords)
        
        for keyword in ticket_type.detection_keywords:
            # Проверяем, является ли ключевое слово отрицательным (начинается с минуса)
            is_negative = keyword.startswith('-')
            # Убираем минус для поиска
            keyword_to_match = keyword[1:] if is_negative else keyword
            keyword_lower = keyword_to_match.lower()
            
            # Проверяем наличие ключевого слова (1 если найдено, иначе 0)
            count = 1 if keyword_lower in ticket_text_lower else 0
            
            # Получаем вес для ключевого слова (по умолчанию 1.0)
            # Приоритет: 1) параметр keyword_weights, 2) ticket_type.keyword_weights, 3) 1.0
            # Для отрицательных ключевых слов используем исходный ключ (с минусом)
            weight_key = keyword.lower() if is_negative else keyword_lower
            if weight_key in keyword_weights:
                weight = keyword_weights[weight_key]
            else:
                weight = ticket_type.get_keyword_weight(weight_key)
            
            # Считаем балл (отрицательный для отрицательных ключевых слов)
            weighted_score = count * weight
            if is_negative:
                weighted_score = -weighted_score
            score += weighted_score
            
            if count > 0:
                # В счёт совпадений идут только положительные ключевые слова
                if not is_negative:
                    matched_count += 1
                if debug:
                    keyword_matches.append(KeywordMatch(
                        keyword=keyword_to_match,
                        count=count,
                        weight=weight,
                        is_negative=is_negative
                    ))
        
        if score > 0:
            scores[ticket_type.id] = (score, ticket_type)
        
        if debug:
            all_scores_debug.append(TicketTypeScore(
                ticket_type=ticket_type,
                total_score=score,
                keyword_matches=keyword_matches,
                matched_keywords_count=matched_count,
                total_keywords_count=total_keywords
            ))
    
    # Возвращаем тип заявки с максимальным баллом
    detected_type = None
    has_ambiguity = False
    ambiguous_types = []
    
    if scores:
        # Находим максимальный балл
        max_score = max(score for score, _ in scores.values())
        
        # Находим все типы с максимальным баллом
        types_with_max_score = [tt for score, tt in scores.values() if score == max_score]
        
        # Проверяем неоднозначность (несколько типов с одинаковым максимумом)
        if len(types_with_max_score) > 1:
            has_ambiguity = True
            ambiguous_types = types_with_max_score
        
        # Всё равно возвращаем первый (или можно вернуть None при неоднозначности)
        detected_type = types_with_max_score[0]
    
    if debug:
        debug_info = DetectionDebugInfo(
            detected_type=detected_type,
            all_scores=all_scores_debug,
            ticket_text_preview=ticket_text[:200] if ticket_text else "",
            has_ambiguity=has_ambiguity,
            ambiguous_types=ambiguous_types,
            total_types_evaluated=active_types_count
        )
        return detected_type, debug_info
    
    return detected_type, None


def validate_ticket(ticket_text: str, rules: List[ValidationRule], 
                   detected_ticket_type: Optional[TicketType] = None) -> ValidationResult:
    """
    Основная функция валидации, применяющая все правила к заявке.
    
    Args:
        ticket_text: текст заявки для проверки.
        rules: список правил валидации.
        detected_ticket_type: опционально определённый тип заявки.
        
    Returns:
        ValidationResult с результатом проверки и деталями.
    """
    failed_rules = []
    passed_rules = []
    error_messages = []
    validation_details = {}
    
    # Сортируем правила по приоритету (сначала более высокий)
    sorted_rules = sorted(rules, key=lambda r: r.priority, reverse=True)
    
    for rule in sorted_rules:
        if not rule.active:
            continue
            
        is_valid = False
        rule_type_value = rule.rule_type.value if isinstance(rule.rule_type, RuleType) else rule.rule_type
        
        try:
            if rule_type_value == 'regex':
                is_valid = validate_regex(ticket_text, rule.pattern)
            elif rule_type_value == 'regex_not_match':
                is_valid = validate_regex_not_match(ticket_text, rule.pattern)
            elif rule_type_value == 'regex_fullmatch':
                is_valid = validate_regex_fullmatch(ticket_text, rule.pattern)
            elif rule_type_value == 'regex_not_fullmatch':
                is_valid = validate_regex_not_fullmatch(ticket_text, rule.pattern)
            elif rule_type_value == 'fias_check':
                is_valid = validate_fias_address(ticket_text, rule.pattern)
            elif rule_type_value == 'custom':
                # Пользовательскую валидацию можно расширить в будущем
                is_valid = True
            else:
                # Неизвестный тип правила — пропускаем
                continue
                
        except Exception as e:
            # Логируем ошибку, но продолжаем остальные правила
            validation_details[rule.rule_name] = f"Error: {str(e)}"
            continue
        
        validation_details[rule.rule_name] = is_valid
        
        if is_valid:
            passed_rules.append(rule.rule_name)
        else:
            failed_rules.append(rule.rule_name)
            error_messages.append(rule.error_message)
    
    return ValidationResult(
        is_valid=len(failed_rules) == 0,
        failed_rules=failed_rules,
        passed_rules=passed_rules,
        error_messages=error_messages,
        validation_details=validation_details,
        detected_ticket_type=detected_ticket_type
    )
