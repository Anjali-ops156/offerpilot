"""Points the Telegram bot at a deployed Vercel URL (webhook mode) — run
this once after each deploy. The opposite of bot/main.py's long-polling,
which is for local development only.

Usage: python scripts/set_webhook.py https://your-project.vercel.app
"""
import sys

import httpx

sys.path.insert(0, "src")
from offerpilot.config import TELEGRAM_BOT_TOKEN  # noqa: E402


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts/set_webhook.py https://your-project.vercel.app")
    base_url = sys.argv[1].rstrip("/")
    webhook_url = f"{base_url}/api/webhook"

    resp = httpx.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setWebhook",
        json={"url": webhook_url, "allowed_updates": ["message", "callback_query"]},
        timeout=15,
    )
    resp.raise_for_status()
    print(resp.json())

    info = httpx.get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getWebhookInfo", timeout=15)
    print(info.json())


if __name__ == "__main__":
    main()
