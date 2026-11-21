"""Gemini 호출: 1) 이야기 대본 생성  2) 판결요지 대조 검증."""
from __future__ import annotations

import json
import time

import requests

from .config import Settings

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class LLMError(RuntimeError):
    pass


def _call_gemini(settings: Settings, prompt: str, *, temperature: float) -> dict:
    if not settings.gemini_api_key:
        raise LLMError("GEMINI_API_KEY가 설정되지 않았습니다 (GitHub Secrets 확인).")
    url = API.format(model=settings.gemini_model)
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature, "responseMimeType": "application/json"},
    }
    last = None
    for attempt in range(3):
        try:
            # 키는 URL 쿼리 대신 헤더로 전달(로그에 URL이 찍혀도 키가 노출되지 않게)
            r = requests.post(url, json=body, timeout=90,
                              headers={"x-goog-api-key": settings.gemini_api_key})
            if r.status_code in (429, 500, 502, 503, 504):
                last = f"HTTP {r.status_code}"
                time.sleep(5 * (attempt + 1))
                continue
            if r.status_code != 200:
                raise LLMError(f"Gemini HTTP {r.status_code}: {r.text[:300]}")
            data = r.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text)
        except (requests.RequestException, KeyError, IndexError, json.JSONDecodeError) as e:
            last = f"{type(e).__name__}: {e}"
            time.sleep(3 * (attempt + 1))
    raise LLMError(f"Gemini 호출 실패: {last}")


SCRIPT_PROMPT = """너는 한국 노동법 판례를 '옛날이야기' 또는 '일상 비유'로 풀어내는 숏폼 작가다.
아래 판례를 바탕으로 45~60초 분량의 세로 숏폼 대본을 만들어라.

[판례 쟁점]
{issue}

[판결요지 — 이야기의 결론은 반드시 이것과 같아야 한다]
{holding}

[절대 규칙]
1. 연도, 날짜, 사건번호, 법 조문 번호(예: 제N조, N항)를 쓰지 마라. 숫자로 된 연도도, 한글 연도도 금지.
   '사건번호', '선고', '전원합의체' 같은 단어도 쓰지 마라. 판례 정보는 영상 끝에 따로 표시된다.
2. 판결요지에 없는 법리·예외·수치를 지어내지 마라. 결론을 과장하거나 반대로 말하지 마라.
3. 실존 인물·회사 이름을 쓰지 마라. 등장인물은 '김 서방', '마을 방앗간 주인'처럼 가상 인물로.
4. 쉬운 말로, 중학생도 이해하게. 한 장면 내레이션은 70자 이내.
5. 첫 장면은 시청자가 멈추게 하는 질문형 훅.
6. 마지막 장면은 판결요지의 결론을 한두 문장으로 정리.

[출력: JSON만]
{{
  "style": "옛날이야기" 또는 "일상비유",
  "hook": "첫 화면 큰 제목(20자 이내)",
  "scenes": [{{"narration": "읽어줄 문장", "caption": "화면 강조 문구(15자 이내)"}}],   // 6~8개
  "conclusion": "이야기가 내린 법적 결론(판결요지와 같은 의미, 한 문장)",
  "youtube_title": "유튜브 제목(40자 이내, #Shorts 제외)",
  "caption": "인스타 캡션 본문(200자 이내)",
  "hashtags": ["#노동법", "..."]   // 5~8개
}}
{feedback}"""

VERIFY_PROMPT = """너는 법률 콘텐츠 검수자다. 아래 '판결요지'와 AI가 쓴 '이야기 대본'을 대조하라.

[판결요지(원문)]
{holding}

[대본의 결론]
{conclusion}

[대본 전체 내레이션]
{narration}

[판정 기준]
- PASS: 대본의 결론이 판결요지의 결론과 같은 방향이고, 판결요지에 없는 법리·예외·수치를 사실처럼 단정하지 않으며,
        시청자가 판결 결과를 반대로 오해할 여지가 없다.
- FAIL: 결론이 다르거나 반대, 핵심 요건 누락으로 결론이 왜곡됨, 지어낸 법리·수치를 단정, 판결 대상이 바뀜.
- 애매하면 FAIL.

[출력: JSON만]
{{"verdict": "PASS" 또는 "FAIL", "reason": "판정 이유 한두 문장"}}"""


def generate_script(settings: Settings, case: dict, feedback: str = "") -> dict:
    prompt = SCRIPT_PROMPT.format(issue=case["issue"], holding=case["holding"],
                                  feedback=f"\n[이전 시도의 문제 — 반드시 고칠 것]\n{feedback}" if feedback else "")
    return validate_script_shape(_call_gemini(settings, prompt, temperature=0.9))


def validate_script_shape(script: dict) -> dict:
    if not isinstance(script, dict):
        raise LLMError("대본이 JSON 객체가 아닙니다")
    scenes = script.get("scenes")
    if not isinstance(scenes, list) or not (3 <= len(scenes) <= 10):
        raise LLMError("scenes는 3~10개여야 합니다")
    for s in scenes:
        if not isinstance(s, dict) or not str(s.get("narration", "")).strip():
            raise LLMError("빈 narration이 있는 장면이 있습니다")
        s["narration"] = str(s["narration"]).strip()[:150]
        s["caption"] = str(s.get("caption", "")).strip()[:30]
    for k in ("hook", "conclusion", "youtube_title", "caption"):
        script[k] = str(script.get(k, "")).strip()
    if not script["conclusion"]:
        raise LLMError("conclusion이 비어 있습니다")
    tags = script.get("hashtags") or []
    script["hashtags"] = [str(t).strip() for t in tags if str(t).strip()][:8]
    return script


def parse_verdict(result: dict) -> tuple[bool, str]:
    """정확히 'PASS'일 때만 통과. 형식이 이상하면 FAIL로 간주(보수적)."""
    if not isinstance(result, dict):
        return False, "검증 응답 형식 오류"
    verdict = str(result.get("verdict", "")).strip().upper()
    reason = str(result.get("reason", "")).strip()[:500]
    return verdict == "PASS", reason or "(사유 없음)"


def verify_script(settings: Settings, case: dict, script: dict) -> tuple[bool, str]:
    narration = "\n".join(s["narration"] for s in script["scenes"])
    prompt = VERIFY_PROMPT.format(holding=case["holding"], conclusion=script["conclusion"], narration=narration)
    return parse_verdict(_call_gemini(settings, prompt, temperature=0.0))
