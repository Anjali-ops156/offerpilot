"""Loads configuration from environment variables / .env."""
from pathlib import Path

from dotenv import load_dotenv
import os

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{REPO_ROOT / 'data' / 'offerpilot.db'}")
KILL_SWITCH = os.environ.get("OFFERPILOT_KILL_SWITCH", "false").lower() == "true"

RULES_DIR = REPO_ROOT / "rules"
DATA_DIR = REPO_ROOT / "data"
