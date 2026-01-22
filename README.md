# SBS Helper Telegram Bot 🚀

The demo version of the bot is located at this link: [https://t.me/vyezdbyl_bot](https://t.me/vyezdbyl_bot). The demo may not reflect the current state of development. 

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/) [![License: Non-Commercial](https://img.shields.io/badge/license-Non--Commercial-red.svg)](LICENSE) [![For Testing Only](https://img.shields.io/badge/status-testing%20only-yellow.svg)](README.md#disclaimer)

A modular Telegram bot with extensible functionality for ticket validation and image processing tasks. Built with a plugin-based architecture that allows multiple independent modules to coexist and serve different purposes. The bot intelligently handles image processing, ticket validation, and provides a scalable platform for additional features. Built with Python, Pillow, and Telegram Bot API.

**Note:** This project is a proof-of-concept for educational and testing purposes. It's not intended for real-world deployment or any form of misuse.

## 🌟 Features

### Core Architecture
- **Modular Design**: Plugin-based architecture allowing independent modules to handle different functionality.
- **Extensible Platform**: Easy to add new features and modules without modifying core bot logic.
- **Interactive Menu System**: Hierarchical keyboard-based navigation with context-aware menus.
- **Message Routing**: Intelligent message dispatcher that routes user interactions to appropriate modules.

### Available Modules

#### Ticket Validator Module ✅
- **Automatic Ticket Type Detection**: AI-powered (lolwhat? an AI wrote that, sorry, ignore it) keyword matching automatically identifies ticket types.
- **Smart Validation**: Validates tickets against type-specific rules loaded from the database.
- **Rule Engine**: Supports multiple validation types:
  - Regular expressions for pattern matching
  - Required field detection
  - Format validation (INN, phone, email)
  - Length constraints
  - Custom validation logic
- **Validation History**: Tracks all ticket validations per user with detailed results.
- **Template Library**: Pre-defined ticket templates with descriptions for different scenarios.
- **User Feedback**: Clear, formatted error messages showing ticket type and specific validation failures.
- **Database-Driven Configuration**: Ticket types, validation rules, and templates stored in MySQL.

#### Vyezd Byl Module (Image Processing) 📸
- **Image Processing Queue**: Background worker handles jobs asynchronously, preventing overload.
- **Smart Detection**:
  - Light/Dark mode via Yandex Maps logo pixel analysis.
  - Rejects images with existing location markers (circles or triangles).
  - Ensures minimum image size and valid formats.
- **Location Overlay**: Processes images with location markers and UI adjustments.
- **Asynchronous Processing**: Non-blocking queue system for efficient resource usage.
- **Interactive Help**: Visual guide with example images showing how to send screenshots correctly.

### Shared Features
- **Invite-Only Access**: Secure user registration via unique invite codes (alphanumeric, uppercase, no zeros for clarity).
- **Database Integration**: MySQL for managing users, invites, job queues, validation rules, ticket types, and templates.
- **Rich UI/UX**: MarkdownV2-formatted messages with proper escaping for special characters.
- **Context-Aware Navigation**: Menu buttons adapt based on current module (main menu, validator submenu, image menu).
- **Error Handling**: User-friendly messages for validation issues, processing errors, or unrecognized input.
- **Testing Suite**: Comprehensive pytest coverage for core functions.

## 🛠️ Installation

1. **Clone the Repository**:
   ```
   git clone https://github.com/yourusername/sprint-fake-location-bot.git
   cd sprint-fake-location-bot
   ```

2. **Set Up Virtual Environment**:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install Dependencies**:
   ```
   pip install -r requirements.txt
   ```
   *(Assumes a `requirements.txt` with packages like `python-telegram-bot`, `Pillow`, `mysql-connector-python`, `python-dotenv`, `pytest`)*

4. **Configure Environment**:
   - Create a `.env` file in the root:
     ```
     TELEGRAM_TOKEN=your_bot_token_here
     MYSQL_HOST=localhost
     MYSQL_USER=root
     MYSQL_PASSWORD=your_password
     MYSQL_DATABASE=sprint_db
     MYSQL_PORT=3306
     DEBUG=1  # Set to 0 for production-like mode
     ```

5. **Set Up Database**:
   - Create the database and tables:
     ```bash
     mysql -u root -p < schema.sql
     ```
   - Load sample ticket types and validation rules:
     ```bash
     mysql -u root -p sprint_db < scripts/initial_ticket_types.sql
     mysql -u root -p sprint_db < scripts/initial_validation_rules.sql
     mysql -u root -p sprint_db < scripts/map_rules_to_ticket_types.sql
     mysql -u root -p sprint_db < scripts/sample_templates.sql
     ```

6. **Prepare Assets**:
   - Place location icons in `assets/` (e.g., `location.png`, `location_dark14.png`).
   - Add `promo3.jpg` to `assets/` for screenshot help instructions.
   - Ensure `images/` directory exists for processed uploads.

## 🏗️ Project Structure

```
src/
├── common/                          # Shared utilities and database layer
│   ├── database.py                 # Database connection and queries
│   ├── messages.py                 # Message templates, keyboards, and utilities
│   ├── invites.py                  # Invite management
│   ├── telegram_user.py            # User model and management
│   └── constants/                  # Configuration constants
│       ├── database.py             # Database constants
│       ├── errorcodes.py           # Error code enums
│       ├── telegram.py             # Telegram API configuration
│       └── os.py                   # OS paths and assets
├── sbs_helper_telegram_bot/
│   ├── telegram_bot/               # Core bot engine
│   │   └── telegram_bot.py        # Main bot dispatcher and routing
│   ├── ticket_validator/           # Ticket validation module ✅
│   │   ├── validators.py          # Validation logic and rules
│   │   ├── validation_rules.py    # Database operations for rules
│   │   ├── ticket_validator_bot_part.py  # Module integration
│   │   ├── README.md              # Module documentation
│   │   └── TICKET_TYPES.md        # Ticket type system guide
│   └── vyezd_byl/                  # Image processing module
│       ├── processimagequeue.py   # Queue processor
│       └── vyezd_byl_bot_part.py  # Module integration
config/
    └── settings.py                 # Menu buttons and configuration
scripts/                             # Database initialization scripts
    ├── initial_ticket_types.sql    # Sample ticket types
    ├── initial_validation_rules.sql # Sample validation rules
    ├── map_rules_to_ticket_types.sql
    └── sample_templates.sql        # Sample ticket templates
schema.sql                          # Complete database schema
```

## 🚀 Usage

### Running the Bot (Easy Method) ⭐
Start both the Telegram bot and image queue processor with a single command:
```bash
python run_bot.py
```

This will launch both services and display their output. Press `Ctrl+C` to stop all services.

### Running Services Separately (Advanced)
If you need to run components individually:
- Start the Telegram bot:
  ```bash
  python -m src.sbs_helper_telegram_bot.telegram_bot.telegram_bot
  ```
- Start the background image processor:
  ```bash
  python -m src.sbs_helper_telegram_bot.vyezd_byl.processimagequeue
  ```

### Interacting with the Bot

#### Initial Setup
1. **Get an Invite**: Obtain an invite code from an existing user.
2. **/start**: Enter the invite code when prompted to register.
3. **Receive Invites**: Get your own invite codes to share with others.

#### Main Menu Navigation
The bot uses an interactive keyboard menu system:
- **🏠 Главное меню** - Return to main menu
- **✅ Валидация заявок** - Access ticket validation features
- **📸 Обработать скриншот** - Process screenshot images
- **🎫 Мои инвайты** - View your invite codes
- **❓ Помощь** - Show help information

#### Ticket Validation Workflow
1. Click **✅ Валидация заявок** from main menu or use `/validate`
2. From the validator submenu:
   - **📋 Проверить заявку** - Start ticket validation
   - **📜 История проверок** - View your validation history
   - **📄 Шаблоны заявок** - Browse ticket templates
   - **ℹ️ Помощь по валидации** - Get validation help
3. Send ticket text when prompted
4. Bot automatically detects ticket type and validates
5. Receive detailed feedback with errors or success confirmation

#### Available Commands
- **/start** - Welcome message and registration
- **/menu** - Show main menu keyboard
- **/validate** - Start ticket validation (opens conversation)
- **/history** - View your validation history
- **/template** - List available ticket templates
- **/template <name>** - Show specific template
- **/help_validate** - Detailed help for ticket validation
- **/invite** - Show your unused invite codes
- **/cancel** - Cancel ongoing ticket validation

#### Image Processing
1. Click **📸 Обработать скриншот** from main menu
2. Click **❓ Помощь по скриншотам** to see visual guide
3. Send image as a file (not compressed photo)
4. Receive processed image with location overlay

## 🧪 Testing

Run the test suite to verify functionality:
```
pytest
```
- Covers validation logic, image processing, and integration tests.

## 📄 License

This project is licensed under a **Non-Commercial License**. See the [LICENSE](LICENSE) file for details. Commercial use is strictly prohibited.

## ⚠️ Disclaimer

**For Testing Purposes Only.** This bot is a demonstration tool and should not be used in production environments. Actual usage by SberService employees (or any corporate entity) for circumventing corporate policies violates internal corporate codes and may lead to ethical or legal issues. The author assumes no responsibility for misuse.

Contributions are welcome for educational enhancements! If you find bugs or have ideas, open an issue or PR. 😊

---

*Built with ❤️ | Last Updated: January 2026* 