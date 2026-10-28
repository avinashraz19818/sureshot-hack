import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# Telegram Userbot (Pyrogram) for 100% Animated Premium Emojis
API_ID = int(os.getenv("API_ID", "12380656"))
API_HASH = os.getenv("API_HASH", "d927c13beaaf5110f25c505b7c071273").strip()
USERBOT_SESSION = os.getenv("USERBOT_SESSION", "").strip()

# Operating Strategy: "sure_shot_hack" (Dual Bet + 100% Win)
BOT_STRATEGY = os.getenv("BOT_STRATEGY", "sure_shot_hack").lower().strip()

admin_ids_raw = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(x.strip()) for x in admin_ids_raw.split(",") if x.strip().isdigit()]

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "wingo_sureshot_hack")

DEFAULT_REGISTER_LINK = os.getenv("DEFAULT_REGISTER_LINK", "https://bdgwin7.com/#/register")
DEFAULT_PROMO_TEXT = os.getenv("DEFAULT_PROMO_TEXT", "🔥 Maintain 3-5 Level Fund for 100% Daily Profit!")

# Supported WinGo Game Modes
WINGO_GAMES = {
    "wingo_30s": {
        "id": "wingo_30s",
        "name": "WinGo 30s",
        "display_name": "⏱️ WinGo 30 Seconds",
        "duration_sec": 30,
        "api_url": "https://draw.ar-lottery01.com/WinGo/WinGo_30S/GetHistoryIssuePage.json"
    },
    "wingo_1m": {
        "id": "wingo_1m",
        "name": "WinGo 1M",
        "display_name": "⏱️ WinGo 1 Minute",
        "duration_sec": 60,
        "api_url": "https://draw.ar-lottery01.com/WinGo/WinGo_1M/GetHistoryIssuePage.json"
    },
    "wingo_3m": {
        "id": "wingo_3m",
        "name": "WinGo 3M",
        "display_name": "⏱️ WinGo 3 Minutes",
        "duration_sec": 180,
        "api_url": "https://draw.ar-lottery01.com/WinGo/WinGo_3M/GetHistoryIssuePage.json"
    },
    "wingo_5m": {
        "id": "wingo_5m",
        "name": "WinGo 5M",
        "display_name": "⏱️ WinGo 5 Minutes",
        "duration_sec": 300,
        "api_url": "https://draw.ar-lottery01.com/WinGo/WinGo_5M/GetHistoryIssuePage.json"
    }
}

# Real Game Bet & Winning Screenshot Automation (Playwright)
DEMO_AUTO_BET = os.getenv("DEMO_AUTO_BET", "true").lower() in ("true", "1", "yes")
DEMO_LOGIN_URL = os.getenv("DEMO_LOGIN_URL", "https://bdgwina.biz/#/login")
DEMO_USERNAME = os.getenv("DEMO_USERNAME", "6556745550")
DEMO_PASSWORD = os.getenv("DEMO_PASSWORD", "win1222")
DEMO_BET_AMOUNT = int(os.getenv("DEMO_BET_AMOUNT", "1")) # Base bet in INR
HEADLESS = os.getenv("HEADLESS", "true").lower() in ("true", "1", "yes")
BROWSER_PROFILE_DIR = os.getenv("BROWSER_PROFILE_DIR", os.path.join(os.path.dirname(__file__), "browser_profile"))
CHROMIUM_PATH = os.getenv("CHROMIUM_PATH", os.getenv("PLAYWRIGHT_CHROMIUM_PATH", ""))

# Session Scheduler Configuration
TIMEZONE = os.getenv("TIMEZONE", "Asia/Kolkata")
# Operating Mode: "24_7" (Continuous) or "scheduled" (Daily VIP Sessions)
DEFAULT_OPERATING_MODE = os.getenv("OPERATING_MODE", "24_7").lower()
PRE_ALERT_MINUTES = int(os.getenv("PRE_ALERT_MINUTES", "15"))

# Default Daily VIP Sessions (IST)
DEFAULT_SESSIONS = [
    {
        "id": 1,
        "name": "Session 1 (Morning)",
        "start": "11:00",
        "end": "11:30",
        "max_rounds": 15
    },
    {
        "id": 2,
        "name": "Session 2 (Afternoon)",
        "start": "14:00",
        "end": "14:30",
        "max_rounds": 15
    },
    {
        "id": 3,
        "name": "Session 3 (Evening)",
        "start": "17:00",
        "end": "17:30",
        "max_rounds": 15
    },
    {
        "id": 4,
        "name": "Session 4 (Night VIP)",
        "start": "20:30",
        "end": "21:00",
        "max_rounds": 15
    }
]
