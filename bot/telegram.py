"""Minimal Telegram Bot API client. Errors never include the token (it's part of the URL)."""
import requests

API = "https://api.telegram.org/bot{token}/{method}"


class TelegramError(RuntimeError):
    pass


def _call(token, method, http=None, **payload):
    try:
        r = (http or requests).post(API.format(token=token, method=method), json=payload, timeout=15)
        data = r.json()
    except (requests.RequestException, ValueError) as e:
        raise TelegramError(f"Telegram {method} failed: {type(e).__name__}") from None
    if not data.get("ok"):
        raise TelegramError(f"Telegram {method}: {data.get('description', 'unknown error')}")
    return data["result"]


def send(token: str, chat_id: str, text: str, http=None):
    if not token or not chat_id:
        raise TelegramError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must both be set")
    return _call(token, "sendMessage", http, chat_id=chat_id, text=text, disable_web_page_preview=True)


def chat_ids(token: str, http=None) -> list:
    """(chat id, name) of everyone who has messaged the bot recently. Send the bot a message first."""
    seen = {}
    for u in _call(token, "getUpdates", http):
        chat = (u.get("message") or u.get("channel_post") or {}).get("chat")
        if chat:
            seen[chat["id"]] = chat.get("username") or chat.get("title") or chat.get("first_name", "")
    return list(seen.items())
