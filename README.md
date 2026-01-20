# SPRINT Fake Location Overlay Bot 🚀

The demo version of the bot is located at this link: [https://t.me/vyezdbyl_bot](https://t.me/vyezdbyl_bot)  

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/) [![License: Non-Commercial](https://img.shields.io/badge/license-Non--Commercial-red.svg)](LICENSE) [![For Testing Only](https://img.shields.io/badge/status-testing%20only-yellow.svg)](README.md#disclaimer)

A clever Telegram bot designed to overlay fake location markers on Yandex Maps screenshots. It intelligently detects light/dark modes, validates images, and processes them via a queue system. Built with Python, Pillow, and Telegram Bot API for seamless image manipulation.

**Note:** This project is a proof-of-concept for educational and testing purposes. It's not intended for real-world deployment or any form of misuse.

## 🌟 Features

- **Invite-Only Access**: Secure user registration via unique invite codes (alphanumeric, uppercase, no zeros for clarity).
- **Image Processing Queue**: Background worker handles jobs asynchronously, preventing overload.
- **Smart Detection**:
  - Light/Dark mode via Yandex Maps logo pixel analysis.
  - Rejects images with existing location markers (circles or triangles).
  - Ensures minimum image size and valid formats.
- **Fake Location Overlay**: Randomly places a fake icon near the center, adjusted for UI borders in dark mode.
- **Database Integration**: MySQL for managing users, invites, and job queues.
- **Error Handling**: User-friendly messages for issues like small images or existing markers.
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

## 🚀 Usage

### Running the Bot
- Start the Telegram bot:
  ```
  python imagebot.py
  ```
- Start the background image processor:
  ```
  python processimagequeue.py
  ```

### Interacting with the Bot
- **/start**: Welcome message (requires invite).
- **/invite**: View your unused invite codes.
- Send a Yandex Maps screenshot as a **file** (not photo) for processing.
- Enter invite codes via text to register.

**Example Flow**:
1. User sends invite code → Registers and gets their own invites.
2. User uploads screenshot → Bot queues it → Processed image returned with fake marker.

## 🧪 Testing

Run the test suite to verify image processing logic:
```
pytest test_generate_image.py
```
- Covers detection of existing markers, mode switching, error cases, and full cycles.

## 📄 License

This project is licensed under a **Non-Commercial License**. See the [LICENSE](LICENSE) file for details. Commercial use is strictly prohibited.

## ⚠️ Disclaimer

**For Testing Purposes Only.** This bot is a demonstration tool and should not be used in production environments. Actual usage by SberService employees (or any corporate entity) violates internal corporate codes and may lead to ethical or legal issues. The author assumes no responsibility for misuse.

Contributions are welcome for educational enhancements! If you find bugs or have ideas, open an issue or PR. 😊

---

*Built with ❤️ by <redacted> | Last Updated: December 2025* 