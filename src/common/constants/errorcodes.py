from enum import StrEnum

ERR_UNKNOWN_FORMAT = 100
ERR_TOO_SMALL = 101
ERR_NO_TRIGGER_PIXEL = 102
ERR_ALREADY_HAS_CIRCLE = 103
ERR_ALREADY_HAS_DARK_CIRCLE = 106
ERR_ALREADY_HAS_TRIANGLE = 104
ERR_ALREADY_HAS_DARK_TRIANGLE = 107
ERR_UNSUPPORTED_SCREEN = 105
ERR_FILE_NOT_FOUND = 108
ERR_TELEGRAM_UPLOAD_FAILED = 109


ERROR_MESSAGES = {
    ERR_UNKNOWN_FORMAT: "ВНИМАНИЕ! Формат файла не поддерживается.",
    ERR_FILE_NOT_FOUND: "ВНИМАНИЕ! Формат файла не поддерживается.",
    ERR_TOO_SMALL: "ВНИМАНИЕ! Плохое изображение.",
    ERR_NO_TRIGGER_PIXEL: "ВНИМАНИЕ! Обработка этого экрана временно не поддерживается. Загрузите скрин с карты где есть кнопка Отметиться.",
    ERR_ALREADY_HAS_CIRCLE: "ВНИМАНИЕ!\n\nВозможно на скрине уже присутствует кружочек с местоположением (светлый режим)!\n\nЗагрузите другой файл.",
    ERR_ALREADY_HAS_DARK_CIRCLE: "ВНИМАНИЕ!\n\nВозможно на скрине уже присутствует кружочек с местоположением (темный режим)!\n\nЗагрузите другой файл.",
    ERR_ALREADY_HAS_TRIANGLE: "ВНИМАНИЕ!\n\nВозможно на скрине уже присутствует треугольник с местоположением!\n\nЗагрузите другой файл.",
    ERR_UNSUPPORTED_SCREEN: "ВНИМАНИЕ! Этот тип экрана пока не поддерживается.",
    ERR_TELEGRAM_UPLOAD_FAILED: "ВНИМАНИЕ! Медленное или нестабильное соединение с Telegram. Попробуйте отправить скриншот ещё раз через пару минут.",
}



class InviteStatus(StrEnum):
    SUCCESS = "success"
    NOT_EXISTS = "not_exists"
    ALREADY_CONSUMED = "already_consumed"