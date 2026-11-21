"""설정: 모든 키는 환경변수(= GitHub Secrets/Variables)에서만 읽는다. 코드에 키를 넣지 말 것."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"

DISCLAIMER = "AI 각색 교육용 콘텐츠 · 법률자문 아님"
DISCLAIMER_NARRATION = "이 영상은 AI가 각색한 교육용 콘텐츠이며, 법률자문이 아닙니다."


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _flag(name: str, default: bool = False) -> bool:
    v = _env(name)
    if not v:
        return default
    return v.lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    gemini_api_key: str = field(default_factory=lambda: _env("GEMINI_API_KEY"))
    gemini_model: str = field(default_factory=lambda: _env("GEMINI_MODEL", "gemini-2.5-flash"))
    tts_voice: str = field(default_factory=lambda: _env("TTS_VOICE", "ko-KR-SunHiNeural"))
    tts_rate: str = field(default_factory=lambda: _env("TTS_RATE", "+8%"))

    enable_instagram: bool = field(default_factory=lambda: _flag("ENABLE_INSTAGRAM", True))
    ig_user_id: str = field(default_factory=lambda: _env("IG_USER_ID"))
    ig_access_token: str = field(default_factory=lambda: _env("IG_ACCESS_TOKEN"))
    ig_graph_version: str = field(default_factory=lambda: _env("IG_GRAPH_VERSION", "v21.0"))

    enable_youtube: bool = field(default_factory=lambda: _flag("ENABLE_YOUTUBE", False))
    yt_client_id: str = field(default_factory=lambda: _env("YT_CLIENT_ID"))
    yt_client_secret: str = field(default_factory=lambda: _env("YT_CLIENT_SECRET"))
    yt_refresh_token: str = field(default_factory=lambda: _env("YT_REFRESH_TOKEN"))
    yt_privacy: str = field(default_factory=lambda: _env("YT_PRIVACY", "public"))

    telegram_bot_token: str = field(default_factory=lambda: _env("TELEGRAM_BOT_TOKEN"))
    telegram_chat_id: str = field(default_factory=lambda: _env("TELEGRAM_CHAT_ID"))

    font_path: str = field(default_factory=lambda: _env("FONT_PATH"))

    def secret_values(self) -> list[str]:
        """로그/알림에서 가려야 할 비밀값 목록."""
        vals = [
            self.gemini_api_key, self.ig_access_token, self.yt_client_secret,
            self.yt_refresh_token, self.telegram_bot_token,
        ]
        return [v for v in vals if len(v) >= 6]


def redact(text: str, settings: Settings) -> str:
    for s in settings.secret_values():
        text = text.replace(s, "***")
    return text
