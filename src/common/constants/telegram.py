from typing import Final
import os
from dotenv import load_dotenv
load_dotenv()
TELEGRAM_TOKEN: Final[str] = os.getenv("TELEGRAM_TOKEN", "dev_user")
