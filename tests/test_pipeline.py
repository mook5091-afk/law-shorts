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
