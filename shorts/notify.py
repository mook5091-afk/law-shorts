"""실패 시에만 텔레그램 알림."""
from __future__ import annotations

import requests

from .config import Settings, redact


def notify_failure(settings: Settings, title: str, detail: str) -> None:
    if not (settings.telegram_bot_token and settings.telegram_chat_id):
        print("[notify] 텔레그램 미설정 — 알림 생략")
        return
    # parse_mode를 쓰지 않음 → 메시지 내 특수문자가 마크업으로 해석되지 않음(인젝션 방지)
    text = redact(f"⚠️ [law-shorts] {title}\n\n{detail}", settings)[:3500]
    try:
        requests.post(f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
                      json={"chat_id": settings.telegram_chat_id, "text": text,
                            "disable_web_page_preview": True}, timeout=20)
    except requests.RequestException as e:
        print(f"[notify] 텔레그램 전송 실패: {type(e).__name__}")
