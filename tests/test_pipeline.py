import json

import pytest

from shorts import cases as C
from shorts.llm import LLMError, parse_verdict, validate_script_shape
from shorts.safety import check_script
from shorts.config import ROOT


def test_cases_file_valid():
    cases = C.load_cases()
    assert len(cases) >= 2


def test_select_skips_published_and_unverified():
    cases = [{"id": "a", "verified": True}, {"id": "b", "verified": False}, {"id": "c", "verified": True}]
    state = {"published": [{"id": "a"}], "failures": {}}
    assert C.select_case(cases, state, require_verified=True)["id"] == "c"
    assert C.select_case(cases, state, require_verified=False)["id"] == "b"


def test_select_skips_repeated_failures():
    cases = [{"id": "a", "verified": True}, {"id": "b", "verified": True}]
    state = {"published": [], "failures": {"a": C.MAX_FAILURES}}
    assert C.select_case(cases, state, require_verified=True)["id"] == "b"


def test_select_none_when_exhausted():
    state = {"published": [{"id": "a"}], "failures": {}}
    assert C.select_case([{"id": "a", "verified": True}], state, require_verified=True) is None


@pytest.mark.parametrize("raw,ok", [
    ({"verdict": "PASS", "reason": "x"}, True),
    ({"verdict": "pass"}, True),
    ({"verdict": "FAIL"}, False),
    ({"verdict": "PASS?"}, False),
    ({"result": "PASS"}, False),
    ("PASS", False),
])
def test_parse_verdict_is_conservative(raw, ok):
    assert parse_verdict(raw)[0] is ok


def test_fixture_script_is_safe():
    s = validate_script_shape(json.loads((ROOT / "tests/fixtures/script_sample.json").read_text()))
    assert check_script(s) == []


def test_shape_rejects_empty():
    with pytest.raises(LLMError):
        validate_script_shape({"scenes": [], "conclusion": "x"})


def test_empty_env_uses_default(monkeypatch):
    from shorts.config import Settings
    monkeypatch.setenv("TTS_VOICE", "")
    monkeypatch.setenv("GEMINI_MODEL", "  ")
    s = Settings()
    assert s.tts_voice == "ko-KR-SunHiNeural"
    assert s.gemini_model == "gemini-2.5-flash"


def test_platforms_auto_enable_from_tokens(monkeypatch):
    from shorts.config import Settings
    for k in ("ENABLE_INSTAGRAM", "ENABLE_YOUTUBE", "IG_USER_ID", "IG_ACCESS_TOKEN",
              "YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    s = Settings()
    assert not s.enable_instagram and not s.enable_youtube
    monkeypatch.setenv("YT_CLIENT_ID", "a"); monkeypatch.setenv("YT_CLIENT_SECRET", "b")
    monkeypatch.setenv("YT_REFRESH_TOKEN", "c")
    assert Settings().enable_youtube
    monkeypatch.setenv("ENABLE_YOUTUBE", "false")
    assert not Settings().enable_youtube


def test_scheduled_run_idles_without_keys(monkeypatch):
    from shorts import main as M
    for k in ("GEMINI_API_KEY", "IG_USER_ID", "IG_ACCESS_TOKEN", "YT_REFRESH_TOKEN",
              "TELEGRAM_BOT_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    assert M.main([]) == 0   # 키 없으면 조용히 대기(성공 종료, 알림 없음)
