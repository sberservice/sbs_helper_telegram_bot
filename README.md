# SBS Helper Telegram Bot 🚀

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/) [![License: Non-Commercial](https://img.shields.io/badge/license-Non--Commercial-red.svg)](LICENSE) [![For Testing Only](https://img.shields.io/badge/status-testing%20only-yellow.svg)](README.md#disclaimer)

A modular Telegram bot designed to assist engineers at **SberService** with various workflow tasks. Built with a plugin-based architecture that allows multiple independent modules to coexist and serve different purposes. The bot features ticket validation, image processing, and provides a scalable platform for additional functionality.

The demo version of the bot is available at [https://t.me/vyezdbyl_bot](https://t.me/vyezdbyl_bot) (may not reflect the current state of development).

**Note:** This project is for educational and testing purposes to help SberService engineers streamline their workflows. It should not be used to circumvent corporate policies or for any form of misuse.

## 🌟 Features

### Core Architecture
- **Modular Design**: Plugin-based architecture allowing independent modules to handle different functionality
- **Extensible Platform**: Easy to add new features and modules without modifying core bot logic (see [Module Development Guide](docs/MODULE_GUIDE.md))
- **Interactive Menu System**: Hierarchical keyboard-based navigation with context-aware menus
- **Message Routing**: Intelligent message dispatcher that routes user interactions to appropriate modules
- **Database-Driven**: MySQL backend for managing users, invites, validation rules, ticket types, templates, and processing queues

### Available Modules

#### Ticket Validator Module ✅
A comprehensive ticket validation system that helps SberService engineers verify tickets against predefined rules and formats.

- **Automatic Ticket Type Detection**: Keyword-based matching automatically identifies ticket types from text
- **Smart Validation Engine**: Validates tickets against type-specific rules loaded from the database
- **Multiple Validation Types**:
  - Regular expressions for pattern matching
  - Required field detection
  - Format validation (INN, phone numbers, email addresses)
  - Length constraints
  - Custom validation logic
- **Negative Keywords**: Automatically rejects tickets containing forbidden terms or patterns
- **Test Templates**: Debug mode for testing validation rules without sending actual tickets
- **Admin Panel**: Manage ticket types, validation rules, templates, and negative keywords via bot commands
- **Validation History**: Tracks all ticket validations per user with detailed results and timestamps
- **Template Library**: Pre-defined ticket templates with descriptions for different scenarios
- **User Feedback**: Clear, formatted error messages showing ticket type and specific validation failures
- **Database-Driven Configuration**: All ticket types, validation rules, templates, and keywords stored in MySQL

See [TICKET_TYPES.md](src/sbs_helper_telegram_bot/ticket_validator/TICKET_TYPES.md), [NEGATIVE_KEYWORDS.md](src/sbs_helper_telegram_bot/ticket_validator/NEGATIVE_KEYWORDS.md), and [TEST_TEMPLATES.md](src/sbs_helper_telegram_bot/ticket_validator/TEST_TEMPLATES.md) for detailed documentation.

#### Vyezd Byl Module (Image Processing) 📸
An image processing module designed to overlay location markers on Yandex Maps screenshots.

- **Image Processing Queue**: Background worker handles jobs asynchronously, preventing bot overload
- **Smart Detection**:
  - Automatic light/dark mode detection via Yandex Maps logo pixel analysis
  - Rejects images with existing location markers (circles or triangles)
  - Validates minimum image size and format requirements
- **Location Overlay**: Processes images with location markers and UI adjustments
- **Asynchronous Processing**: Non-blocking queue system for efficient resource usage
- **Interactive Help**: Visual guide with example images showing correct screenshot format

### Shared Features
- **Invite-Only Access**: Secure user registration via unique invite codes (alphanumeric, uppercase, no zeros for clarity)
- **Database Integration**: MySQL for managing users, invites, job queues, validation rules, ticket types, templates, and keywords
- **Rich UI/UX**: MarkdownV2-formatted messages with proper escaping for special characters
- **Context-Aware Navigation**: Menu buttons adapt based on current module (main menu, validator submenu, image menu)
- **Error Handling**: User-friendly error messages for validation issues, processing errors, or unrecognized input
- **Testing Suite**: Comprehensive pytest coverage for core bot functions and module features

## 🛠️ Installation

### Prerequisites
- Python 3.10 or higher
- MySQL 8.0 or higher
- A Telegram bot token from [@BotFather](https://t.me/botfather)

1. **Clone the Repository**:
   ```bash
   git clone https://github.com/sberservice/sbs_helper_telegram_bot.git
   cd sbs_helper_telegram_bot
   ```

2. **Set Up Virtual Environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

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
   - Load initial data (ticket types, validation rules, templates):
     ```bash
     mysql -u root -p sprint_db < scripts/initial_ticket_types.sql
     mysql -u root -p sprint_db < scripts/initial_validation_rules.sql
     mysql -u root -p sprint_db < scripts/map_rules_to_ticket_types.sql
     mysql -u root -p sprint_db < scripts/sample_templates.sql
     ```
   - (Optional) Set up admin user and test templates:
     ```bash
     mysql -u root -p sprint_db < scripts/migration_add_admin.sql
     mysql -u root -p sprint_db < scripts/migration_test_templates.sql
     ```

6. **Prepare Assets**:
   - Place location icons in `assets/` directory (e.g., `location.png`, `location_dark14.png`)
   - Add `promo3.jpg` to `assets/` for screenshot help instructions
   - Ensure `images/` directory exists for processed image uploads

## 🏗️ Project Structure

```
src/
├── common/                          # Shared utilities and database layer
│   ├── database.py                 # Database connection and queries
│   ├── messages.py                 # Message templates, keyboards, and utilities
│   ├── invites.py                  # Invite code management
│   ├── telegram_user.py            # User model and management
│   └── constants/                  # Configuration constants
│       ├── database.py             # Database constants
│       ├── errorcodes.py           # Error code enums
│       ├── telegram.py             # Telegram API configuration
│       └── os.py                   # OS paths and assets
├── sbs_helper_telegram_bot/
│   ├── base_module.py              # Base class for modules
│   ├── telegram_bot/               # Core bot engine
│   │   └── telegram_bot.py        # Main bot dispatcher and routing
│   ├── ticket_validator/           # Ticket validation module ✅
│   │   ├── validators.py          # Validation logic and rules engine
│   │   ├── validation_rules.py    # Database operations for rules
│   │   ├── ticket_validator_bot_part.py  # Bot handlers and conversation
│   │   ├── admin_panel_bot_part.py # Admin commands for managing rules
│   │   ├── keyboards.py           # Keyboard builders
│   │   ├── messages.py            # User-facing messages
│   │   ├── settings.py            # Module configuration
│   │   ├── README.md              # Module documentation
│   │   ├── TICKET_TYPES.md        # Ticket type system guide
│   │   ├── NEGATIVE_KEYWORDS.md   # Negative keywords documentation
│   │   └── TEST_TEMPLATES.md      # Test templates documentation
│   └── vyezd_byl/                  # Image processing module
│       ├── processimagequeue.py   # Background queue processor
│       ├── vyezd_byl_bot_part.py  # Bot handlers and integration
│       ├── keyboards.py           # Keyboard builders
│       ├── messages.py            # User-facing messages
│       └── settings.py            # Module configuration
config/
│   └── settings.py                 # Global menu buttons and configuration
scripts/                             # Database initialization scripts
│   ├── initial_ticket_types.sql    # Sample ticket types
│   ├── initial_validation_rules.sql # Sample validation rules
│   ├── map_rules_to_ticket_types.sql # Rule-to-type mappings
│   ├── sample_templates.sql        # Sample ticket templates
│   ├── migration_add_admin.sql     # Admin user setup
│   └── example_negative_keywords.sql # Negative keywords examples
tests/                               # Test suite
│   ├── test_ticket_validator.py    # Ticket validator tests
│   ├── test_admin_panel_bot.py     # Admin panel tests
│   ├── test_telegram_bot.py        # Main bot tests
│   └── ...                         # Other test files
docs/
│   └── MODULE_GUIDE.md             # Guide for creating new modules
schema.sql                          # Complete database schema
run_bot.py                          # Main entry point (starts all services)
requirements.txt                    # Python dependencies
```

## 🚀 Usage

### Running the Bot

**Recommended: Start all services with a single command:**
```bash
python run_bot.py
```

This launches both the Telegram bot and the background image queue processor. Press `Ctrl+C` to stop all services.

**Advanced: Run services separately:**
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
1. Obtain an invite code from an existing user or administrator
2. Send `/start` to the bot and enter the invite code when prompted
3. After registration, receive your own invite codes to share with colleagues

#### Main Menu Navigation
The bot provides an interactive keyboard menu system:
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

**General Commands:**
- `/start` - Welcome message and registration
- `/menu` - Show main menu keyboard
- `/invite` - Show your unused invite codes

**Ticket Validation Commands:**
- `/validate` - Start ticket validation conversation
- `/history` - View your validation history
- `/template` - List available ticket templates
- `/template <name>` - Show specific template
- `/help_validate` - Detailed help for ticket validation
- `/cancel` - Cancel ongoing ticket validation

**Admin Commands** (requires admin privileges):
- `/admin` - Access admin panel
- Various admin commands for managing ticket types, validation rules, templates, and negative keywords (see admin documentation)

#### Image Processing
1. Click **📸 Обработать скриншот** from main menu
2. Click **❓ Помощь по скриншотам** to see visual guide
3. Send image as a file (not compressed photo)
4. Receive processed image with location overlay

## 🧪 Testing

Run the test suite to verify functionality:
```bash
pytest
```

The test suite includes:
- Ticket validation logic tests
- Admin panel CRUD operations tests
- Image processing tests
- Telegram bot integration tests
- Message formatting tests

## 🤝 Contributing

Contributions are welcome! This project is designed to help SberService engineers, and community improvements are encouraged.

### How to Contribute

1. **Fork the repository** and create a new branch for your feature or bugfix
2. **For bug fixes or improvements**: Submit a pull request with a clear description of the changes
3. **For new modules**: Please open an issue first to discuss your proposed module before starting development
   - This helps ensure alignment with project goals and prevents duplicate efforts
   - See the [Module Development Guide](docs/MODULE_GUIDE.md) for technical details on creating modules

### Guidelines

- Follow existing code style and conventions
- Add tests for new functionality
- Update documentation as needed
- Keep commits focused and write clear commit messages
- Ensure all tests pass before submitting a PR

## 📚 Documentation

- [Module Development Guide](docs/MODULE_GUIDE.md) - How to create custom modules
- [Ticket Validator Module](src/sbs_helper_telegram_bot/ticket_validator/README.md) - Detailed validator documentation
- [Ticket Types System](src/sbs_helper_telegram_bot/ticket_validator/TICKET_TYPES.md) - Ticket type configuration
- [Negative Keywords](src/sbs_helper_telegram_bot/ticket_validator/NEGATIVE_KEYWORDS.md) - Forbidden terms system
- [Test Templates](src/sbs_helper_telegram_bot/ticket_validator/TEST_TEMPLATES.md) - Debug template system

## 📄 License

This project is licensed under a **Non-Commercial License**. See the [LICENSE](LICENSE) file for details. Commercial use is strictly prohibited.

## ⚠️ Disclaimer

**For Testing and Educational Purposes Only.** This bot is designed to assist SberService engineers with workflow tasks in a testing environment. It should not be used in production environments or to circumvent corporate policies. Misuse of this tool may violate internal corporate codes and could lead to ethical or legal consequences. The author assumes no responsibility for misuse.

---

**Built to help SberService engineers** | *Last Updated: January 2026* 