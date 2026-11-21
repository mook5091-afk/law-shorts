import pytest

from shorts.safety import check_script, find_violations


@pytest.mark.parametrize("text", [
    "2024년 겨울, 일꾼이 말했다",
    "그해는 ２０２３년이었다",          # 전각 숫자 우회
    "'98년 봄이었어요",
    "이천이십사년에 생긴 일",
    "2010. 5. 20. 판결",
    "사건 2020다247190 에서",
    "2007다 90760",
    "근로기준법 제2조에 따르면",
    "제 34 조",
    "34조의2에 따라",
    "3항을 보면",
    "사건번호를 보면",
    "전원합의체가 결정했다",
])
def test_blocked(text):
    assert find_violations(text), text


@pytest.mark.parametrize("text", [
    "돌쇠는 3년 동안 일했어요",
    "월급 200만 원을 받았지요",
    "2000만 원짜리 집",
    "일꾼 1200명이 있었어요",
    "퇴직금의 절반을 넘는 부분",
    "두 사람이 한 조로 일했어요",
    "지하철 2호선을 타고",
])
def test_allowed(text):
    assert not find_violations(text), find_violations(text)


def test_check_script_scans_all_fields():
    s = {"hook": "ok", "conclusion": "ok", "scenes": [{"narration": "ok", "caption": "제5조"}],
         "hashtags": ["#2024판례"]}
    names = [n for n, _ in check_script(s)]
    assert len(names) >= 2
