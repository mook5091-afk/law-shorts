"""대본 안전 필터.

대본(이야기)에는 연도·날짜·사건번호·조문번호가 절대 들어가면 안 된다.
판례 정보는 마지막 장면에서 cases.json 원문 데이터로만 보여준다.
LLM이 지어낸 번호가 섞이는 것을 막기 위한 '코드 레벨' 탈락 규칙이다.
"""
from __future__ import annotations

import re
import unicodedata

_CASE_CODES = (
    "가합|가단|가소|구합|구단|고합|고단|헌마|헌바|헌가|헌라|"
    "다|나|누|두|도|노|마|카|그|허|후|재|스|므|르|브|아|라|자"
)
_KOR_DIGIT = "[일이삼사오육칠팔구]"

PATTERNS: list[tuple[str, re.Pattern]] = [
    # 금액·인원 등 단위가 붙은 숫자(2000만 원, 1900명)는 연도로 보지 않는다
    ("연도(4자리)", re.compile(r"(?<![\d,])(?:1[89]|20)\d{2}(?![\d,])(?!\s*(?:만|천|억|원|명|개|%|시간|분|초|살|세|일|번|장|km|m\b))")),
    ("연도(약식 'NN년)", re.compile(r"['’]\d{2}\s*년")),
    ("연도(한글)", re.compile(rf"[일이]천\s*(?:{_KOR_DIGIT}?백)?\s*(?:{_KOR_DIGIT}?십)?\s*{_KOR_DIGIT}?\s*년")),
    ("날짜(N.N.N)", re.compile(r"\d{1,4}\s*[./]\s*\d{1,2}\s*[./]\s*\d{1,2}")),
    ("사건번호", re.compile(rf"\d{{2,4}}\s?(?:{_CASE_CODES})\s?\d{{2,}}")),
    ("조문번호(제N조/항/호)", re.compile(r"제\s*\d+\s*(?:조|항|호)")),
    # 안전 우선(false positive 허용): 'N조'는 금액(조 원)·조각 외엔 모두 탈락, 'N항'은 항상 탈락,
    # 'N호'는 호선·호실·호점 등 일상 표현만 허용
    ("조문번호(N조)", re.compile(r"\d+\s*조(?!\s*(?:원|달러|각))")),
    ("조문번호(N항)", re.compile(r"\d+\s*항")),
    ("조문번호(N호)", re.compile(r"\d+\s*호(?!\s*(?:선|실|점|기|차|관|봉))")),
    ("판례 식별어", re.compile(r"사건번호|선고\s*된?|전원합의체|판례번호")),
]


def normalize(text: str) -> str:
    # 전각 숫자(２０２４) 등 우회 표기를 일반 문자로 통일
    return unicodedata.normalize("NFKC", text)


def find_violations(text: str) -> list[tuple[str, str]]:
    """(규칙명, 매칭문자열) 목록을 반환. 빈 목록이면 통과."""
    t = normalize(text)
    hits = []
    for name, pat in PATTERNS:
        for m in pat.finditer(t):
            hits.append((name, m.group(0)))
    return hits


def check_script(script: dict) -> list[tuple[str, str]]:
    """대본 전체(제목·장면·결론·해시태그)를 검사한다."""
    parts = [script.get("hook", ""), script.get("conclusion", ""), script.get("youtube_title", ""),
             script.get("caption", "")]
    for s in script.get("scenes", []):
        parts.append(s.get("narration", ""))
        parts.append(s.get("caption", ""))
    parts.extend(script.get("hashtags", []))
    return find_violations("\n".join(str(p) for p in parts))
