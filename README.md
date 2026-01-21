# SBS Helper Telegram Bot 🚀

The demo version of the bot is located at this link: [https://t.me/vyezdbyl_bot](https://t.me/vyezdbyl_bot). The demo may not reflect the current state of development. 

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/) [![License: Non-Commercial](https://img.shields.io/badge/license-Non--Commercial-red.svg)](LICENSE) [![For Testing Only](https://img.shields.io/badge/status-testing%20only-yellow.svg)](README.md#disclaimer)

A modular Telegram bot with extensible functionality for ticket validation and image processing tasks. Built with a plugin-based architecture that allows multiple independent modules to coexist and serve different purposes. The bot intelligently handles image processing, ticket validation, and provides a scalable platform for additional features. Built with Python, Pillow, and Telegram Bot API.

**Note:** This project is a proof-of-concept for educational and testing purposes. It's not intended for real-world deployment or any form of misuse.

## 🌟 Features

### Core Architecture
- **Modular Design**: Plugin-based architecture allowing independent modules to handle different functionality.
- **Extensible Platform**: Easy to add new features and modules without modifying core bot logic.
- **Message Routing**: Intelligent message dispatcher that routes user interactions to appropriate modules.

### Available Modules

#### Ticket Validator Module
- **Smart Ticket Validation**: Validates tickets against customizable rules and validation logic.
- **Rule Engine**: Supports complex validation rules mapped to different ticket types.
- **Template Support**: Pre-defined ticket templates for common scenarios.
- **Database-Driven Configuration**: Ticket types and validation rules stored in MySQL for easy updates.

#### Vyezd Byl Module (Image Processing)
- **Image Processing Queue**: Background worker handles jobs asynchronously, preventing overload.
- **Smart Detection**:
  - Light/Dark mode via Yandex Maps logo pixel analysis.
  - Rejects images with existing location markers (circles or triangles).
  - Ensures minimum image size and valid formats.
- **Location Overlay**: Processes images with location markers and UI adjustments.
- **Asynchronous Processing**: Non-blocking queue system for efficient resource usage.

### Shared Features
- **Invite-Only Access**: Secure user registration via unique invite codes (alphanumeric, uppercase, no zeros for clarity).
- **Database Integration**: MySQL for managing users, invites, job queues, and validation rules.
- **Error Handling**: User-friendly messages for validation issues or processing errors.
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
   - Set up MySQL database with tables for `users`, `invites`, and `imagequeue` (schema inferred from code).

5. **Prepare Assets**:
   - Place location icons in `assets/` (e.g., `location.png`, `location_dark14.png`).
   - Ensure `images/` and `test_samples/` directories exist for uploads and tests.

## 🏗️ Project Structure

```
src/
├── common/                          # Shared utilities and database layer
│   ├── database.py                 # Database connection and queries
│   ├── messages.py                 # Message templates and utilities
│   ├── invites.py                  # Invite management
│   ├── telegram_user.py            # User model and management
│   └── constants/                  # Configuration constants
├── sbs_helper_telegram_bot/
│   ├── telegram_bot/               # Core bot engine
│   │   └── telegram_bot.py        # Main bot dispatcher and routing
│   ├── ticket_validator/           # Ticket validation module
│   │   ├── validation_rules.py    # Rule definitions
│   │   ├── validators.py          # Validation logic
│   │   └── ticket_validator_bot_part.py  # Module integration
│   └── vyezd_byl/                  # Image processing module
│       ├── processimagequeue.py   # Queue processor
│       └── vyezd_byl_bot_part.py  # Module integration
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
- **/start**: Welcome message (requires invite).
- **/invite**: View your unused invite codes.
- Send files for processing (specific functionality depends on enabled modules).
- Enter invite codes via text to register.

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