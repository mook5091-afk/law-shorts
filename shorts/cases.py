"""판례 데이터 로드·검증·선택(중복 발행 방지)."""
from __future__ import annotations

import json
import re
from pathlib import Path

from .config import DATA_DIR

CASES_FILE = DATA_DIR / "cases.json"
STATE_FILE = DATA_DIR / "state.json"
MAX_FAILURES = 3  # 검증 FAIL이 이 횟수에 도달한 판례는 자동 선택에서 제외

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")  # 파일명에 쓰이므로 엄격히 제한(경로 조작 방지)
REQUIRED = ("id", "title", "court", "date", "case_no", "issue", "holding")


class CaseError(ValueError):
    pass


def load_cases(path: Path = CASES_FILE) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = data["cases"]
    seen = set()
    for c in cases:
        missing = [k for k in REQUIRED if not str(c.get(k, "")).strip()]
        if missing:
            raise CaseError(f"판례 {c.get('id')} 필수 항목 누락: {missing}")
        if not _ID_RE.match(c["id"]):
            raise CaseError(f"잘못된 id 형식: {c['id']!r}")
        if c["id"] in seen:
            raise CaseError(f"중복 id: {c['id']}")
        seen.add(c["id"])
    return cases


def load_state(path: Path = STATE_FILE) -> dict:
    if not path.exists():
        return {"published": [], "failures": {}}
    state = json.loads(path.read_text(encoding="utf-8"))
    state.setdefault("published", [])
    state.setdefault("failures", {})
    return state


def save_state(state: dict, path: Path = STATE_FILE) -> None:
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def published_ids(state: dict) -> set[str]:
    return {p["id"] for p in state["published"]}


def select_case(cases: list[dict], state: dict, *, require_verified: bool,
                case_id: str | None = None) -> dict | None:
    """발행되지 않은 판례 중 파일 순서상 첫 번째를 고른다. 없으면 None."""
    if case_id:
        for c in cases:
            if c["id"] == case_id:
                return c
        raise CaseError(f"case_id {case_id!r} 없음")
    done = published_ids(state)
    for c in cases:
        if c["id"] in done:
            continue
        if require_verified and not c.get("verified"):
            continue
        if state["failures"].get(c["id"], 0) >= MAX_FAILURES:
            continue
        return c
    return None


def mark_published(state: dict, case: dict, date_iso: str, urls: dict) -> None:
    state["published"].append({"id": case["id"], "date": date_iso, "urls": urls})
    state["failures"].pop(case["id"], None)


def mark_failure(state: dict, case: dict) -> int:
    n = state["failures"].get(case["id"], 0) + 1
    state["failures"][case["id"]] = n
    return n
