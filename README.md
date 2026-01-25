# SBS Helper Telegram Bot 🚀

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/) [![License: Non-Commercial](https://img.shields.io/badge/license-Non--Commercial-red.svg)](LICENSE) [![For Testing Only](https://img.shields.io/badge/status-testing%20only-yellow.svg)](README.md#disclaimer)

## TL;DR (Краткое описание) 🇷🇺

Модульный Telegram-бот для инженеров **СберСервис**. Основные возможности:

- **✅ Валидация заявок** — проверка заявок на соответствие правилам с автоматическим определением типа заявки по ключевым словам
- **📸 Обработка скриншотов** — наложение маркеров локации на скриншоты Спринта
- **🔐 Инвайт-система** — регистрация только по приглашениям
- **👨‍💼 Админ-панель** — управление правилами валидации, типами заявок и тестовыми шаблонами через бота

Демо-версия: [@vyezdbyl_bot](https://t.me/vyezdbyl_bot)
(демо не отражает текущую стадию разработки)

---

## Overview

A modular Telegram bot designed to assist **SberService** engineers with workflow tasks. Built with a plugin-based architecture allowing multiple independent modules.

**Note:** This project is for educational and testing purposes only. It should not be used to circumvent corporate policies.

## 🌟 Features

### Core Architecture
- **Modular Design**: Plugin-based architecture for independent modules
- **Extensible Platform**: Easy to add new modules (see [Module Guide](docs/MODULE_GUIDE.md))
- **Interactive Menu System**: Hierarchical keyboard-based navigation
- **Database-Driven**: MySQL backend for all data storage

### Ticket Validator Module ✅

A comprehensive ticket validation system:

- **Automatic Type Detection**: Keywords-based matching identifies ticket types
- **Smart Validation**: Type-specific rules from database
- **Multiple Rule Types**: regex, required_field, format, length, custom
- **Negative Keywords**: Keywords with `-` prefix lower detection scores
- **Keyword Weights**: Custom weights for detection keywords (case-insensitive)
- **Admin Panel**: Full CRUD for rules, types, keywords via bot
- **Test Templates**: Admin-only templates to verify validation rules work correctly
- **Validation History**: Tracks all validations per user

See detailed docs:
- [Ticket Types](src/sbs_helper_telegram_bot/ticket_validator/TICKET_TYPES.md)
- [Negative Keywords](src/sbs_helper_telegram_bot/ticket_validator/NEGATIVE_KEYWORDS.md)
- [Test Templates](src/sbs_helper_telegram_bot/ticket_validator/TEST_TEMPLATES.md)

### Vyezd Byl Module (Image Processing) 📸

- **Image Queue**: Async background processing
- **Smart Detection**: Light/dark mode detection, rejects images with existing markers
- **Location Overlay**: Adds location markers to Yandex Maps screenshots

### Shared Features
- **Invite-Only Access**: Registration via unique invite codes
- **Rich UI**: MarkdownV2 formatted messages
- **Testing Suite**: Comprehensive pytest coverage

## 🛠️ Installation

### Prerequisites
- Python 3.10+
- MySQL 8.0+
- Telegram bot token from [@BotFather](https://t.me/botfather)

### Setup

1. **Clone & Setup Environment**:
   ```bash
   git clone https://github.com/sberservice/sbs_helper_telegram_bot.git
   cd sbs_helper_telegram_bot
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Configure Environment** (create `.env` file):
   ```
   TELEGRAM_TOKEN=your_bot_token_here
   MYSQL_HOST=localhost
   MYSQL_USER=root
   MYSQL_PASSWORD=your_password
   MYSQL_DATABASE=sprint_db
   MYSQL_PORT=3306
   DEBUG=1
   ```

3. **Setup Database**:
   ```bash
   mysql -u root -p < schema.sql
   mysql -u root -p sprint_db < scripts/initial_ticket_types.sql
   mysql -u root -p sprint_db < scripts/initial_validation_rules.sql
   mysql -u root -p sprint_db < scripts/map_rules_to_ticket_types.sql
   mysql -u root -p sprint_db < scripts/sample_templates.sql
   ```

4. **Prepare Assets**:
   - Place location icons in `assets/` (e.g., `location.png`, `location_dark14.png`)
   - Add `promo3.jpg` to `assets/` for help screenshots
   - Ensure `images/` directory exists

## 🏗️ Project Structure

```
src/
├── common/                     # Shared utilities
│   ├── database.py            # DB connection
│   ├── messages.py            # Message templates
│   ├── invites.py             # Invite management
│   ├── telegram_user.py       # User model
│   └── constants/             # Configuration constants
├── sbs_helper_telegram_bot/
│   ├── base_module.py         # Base module class
│   ├── telegram_bot/          # Core bot
│   │   └── telegram_bot.py
│   ├── ticket_validator/      # Validation module
│   │   ├── validators.py      # Validation logic
│   │   ├── validation_rules.py # DB operations
│   │   ├── ticket_validator_bot_part.py
│   │   ├── admin_panel_bot_part.py
│   │   └── *.md               # Documentation
│   └── vyezd_byl/             # Image processing module
│       ├── processimagequeue.py
│       └── vyezd_byl_bot_part.py
config/
│   └── settings.py            # Global config
scripts/                       # SQL init scripts
tests/                         # Test suite
docs/
│   └── MODULE_GUIDE.md        # Module development guide
schema.sql                     # Database schema
run_bot.py                     # Entry point
```

## 🚀 Usage

### Running

**Recommended** (starts all services):
```bash
python run_bot.py
```

Press `Ctrl+C` to stop.

### User Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome & registration |
| `/menu` | Show main menu |
| `/validate` | Start ticket validation |
| `/help_validate` | Validation help |
| `/cancel` | Cancel current operation |
| `/invite` | Show your invite codes |

### Admin Commands

| Command | Description |
|---------|-------------|
| `/admin` | Open admin panel |

Admin panel provides:
- 📋 **Правила** — Manage validation rules
- 📁 **Типы заявок** — Manage ticket types and keywords
- 🧪 **Тест шаблоны** — Manage test templates
- 🔬 **Тест regex** — Test regex patterns

### Making a User Admin

```sql
UPDATE users SET is_admin = 1 WHERE userid = <telegram_user_id>;
```

## 🧪 Testing

```bash
pytest
```

## 📚 Documentation

- [Module Development Guide](docs/MODULE_GUIDE.md)
- [Ticket Validator](src/sbs_helper_telegram_bot/ticket_validator/README.md)
- [Ticket Types](src/sbs_helper_telegram_bot/ticket_validator/TICKET_TYPES.md)
- [Negative Keywords](src/sbs_helper_telegram_bot/ticket_validator/NEGATIVE_KEYWORDS.md)
- [Test Templates](src/sbs_helper_telegram_bot/ticket_validator/TEST_TEMPLATES.md)

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. For new modules, open an issue first
4. Submit a pull request

## 📄 License

**Non-Commercial License**. See [LICENSE](LICENSE).

## ⚠️ Disclaimer

**For Testing and Educational Purposes Only.** This bot is designed to assist SberService engineers in a testing environment. Misuse may violate internal corporate codes. The author assumes no responsibility for misuse.

---

**Built for SberService engineers** | *Last Updated: January 2026*
