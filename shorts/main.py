"""파이프라인 진입점.

  python -m shorts.main --test            # 발행 없이 영상만 생성(output/)
  python -m shorts.main                   # 생성 + 인스타/유튜브 발행 + state.json 갱신
  python -m shorts.main --test --offline  # 개발용: Gemini·TTS 없이 고정 대본 + 무음으로 렌더링 확인
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import traceback
from pathlib import Path

from . import cases as C
from .config import DISCLAIMER_NARRATION, OUTPUT_DIR, ROOT, Settings, redact
from .llm import LLMError, generate_script, validate_script_shape, verify_script
from .media import build_video
from .notify import notify_failure
from .publish import upload_instagram_reel, upload_youtube
from .safety import check_script

MAX_SCRIPT_ATTEMPTS = 3
KST = dt.timezone(dt.timedelta(hours=9))


class Skip(Exception):
    """오늘은 발행하지 않고 건너뜀(검증 FAIL 등)."""


def _gh_output(**kv: str) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            for k, v in kv.items():
                f.write(f"{k}={v}\n")


def make_script(settings: Settings, case: dict, use_fixture: bool) -> dict:
    if use_fixture:
        fx = ROOT / "tests" / "fixtures" / f"script_{case['id']}.json"
        if not fx.exists():
            fx = ROOT / "tests" / "fixtures" / "script_sample.json"
        script = validate_script_shape(json.loads(fx.read_text(encoding="utf-8")))
        if v := check_script(script):
            raise Skip(f"오프라인 고정 대본이 안전 필터에 걸림: {v}")
        return script

    feedback = ""
    for attempt in range(1, MAX_SCRIPT_ATTEMPTS + 1):
        script = generate_script(settings, case, feedback)
        violations = check_script(script)
        if violations:
            found = ", ".join(f"{n}:'{m}'" for n, m in violations[:10])
            print(f"[safety] 시도 {attempt} 탈락 — {found}")
            feedback = f"금지 표현이 들어갔다: {found}. 연도·날짜·사건번호·조문번호를 모두 빼고 다시 써라."
            continue
        return script
    raise Skip(f"대본이 {MAX_SCRIPT_ATTEMPTS}회 연속 안전 필터(연도·사건번호·조문번호)에 걸림")


def build_texts(case: dict, script: dict) -> tuple[str, str, str]:
    tags = " ".join(dict.fromkeys(script["hashtags"] + ["#노동법", "#판례", "#Shorts"]))
    source = f"{case['court']} {case['date']} {case['case_no']} ({case['title']})"
    disclaimer = f"※ {DISCLAIMER_NARRATION}\n※ 개별 사안은 노무사·변호사와 상담하세요."
    ig_caption = f"{script['caption']}\n\n📌 판례: {source}\n{disclaimer}\n\n{tags}"
    yt_title = f"{script['youtube_title'] or case['title']} #Shorts"
    yt_desc = f"{script['caption']}\n\n판례: {source}\n판결요지: {case['holding']}\n\n{disclaimer}\n\n{tags}"
    return ig_caption, yt_title, yt_desc


class NotConfigured(Exception):
    """아직 키가 없어 자동 실행을 조용히 건너뜀(알림 없음)."""


def run(args: argparse.Namespace, settings: Settings) -> int:
    if not args.test:
        # 자동 실행: 필요한 키가 다 들어오기 전에는 아무것도 하지 않음 → 매일 실패 알림 방지
        missing = []
        if not settings.gemini_api_key:
            missing.append("GEMINI_API_KEY")
        if not (settings.enable_instagram or settings.enable_youtube):
            missing.append("인스타(IG_*) 또는 유튜브(YT_*) 토큰")
        if missing:
            raise NotConfigured("설정 대기 중 — 없음: " + ", ".join(missing))
    cases = C.load_cases()
    state = C.load_state()
    case = C.select_case(cases, state, require_verified=not args.test, case_id=args.case_id)
    if case is None:
        raise Skip("발행 가능한 판례가 없습니다. data/cases.json에 판례를 추가하세요.")
    print(f"[case] {case['id']} — {case['title']}")
    _gh_output(case_id=case["id"])

    today = dt.datetime.now(KST).date().isoformat()
    workdir = OUTPUT_DIR / f"{today}_{case['id']}"
    workdir.mkdir(parents=True, exist_ok=True)

    # 1) 대본 생성 + 코드 안전 필터
    # 테스트 모드에서 Gemini 키가 없으면 고정 샘플 대본으로 대체(음성·영상은 실제로 생성)
    use_fixture = args.offline or (args.test and not settings.gemini_api_key)
    if use_fixture and not args.offline:
        print("[warn] GEMINI_API_KEY 없음 — 테스트 모드이므로 고정 샘플 대본으로 진행합니다")
    script = make_script(settings, case, use_fixture)
    (workdir / "script.json").write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")

    # 2) 2차 검증: 판결요지와 결론 대조 (FAIL이면 오늘은 건너뜀)
    if use_fixture:
        ok, reason = True, "고정 샘플 대본: 검증 생략"
    else:
        ok, reason = verify_script(settings, case, script)
    (workdir / "verify.json").write_text(json.dumps({"pass": ok, "reason": reason}, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    print(f"[verify] {'PASS' if ok else 'FAIL'} — {reason}")
    if not ok:
        if not args.test:
            n = C.mark_failure(state, case)
            C.save_state(state)
            _gh_output(state_changed="true")
            reason += f" (누적 FAIL {n}/{C.MAX_FAILURES})"
        raise Skip(f"2차 검증 FAIL: {reason}")

    # 3) 음성 + 영상
    video = build_video(settings, case, script, workdir / "build", workdir / "short.mp4", offline=args.offline)
    ig_caption, yt_title, yt_desc = build_texts(case, script)
    (workdir / "post.txt").write_text(f"[Instagram]\n{ig_caption}\n\n[YouTube]\n{yt_title}\n\n{yt_desc}\n",
                                      encoding="utf-8")
    print(f"[video] {video}")

    if args.test:
        print("[test] 테스트 모드 — 발행하지 않음")
        return 0

    # 4) 발행
    urls, errors = {}, []
    if settings.enable_instagram:
        try:
            urls["instagram"] = upload_instagram_reel(settings, video, ig_caption)
        except Exception as e:  # 한 플랫폼 실패가 다른 플랫폼을 막지 않게
            errors.append(f"Instagram: {type(e).__name__}: {e}")
    if settings.enable_youtube:
        try:
            urls["youtube"] = upload_youtube(settings, video, yt_title, yt_desc, script["hashtags"])
        except Exception as e:
            errors.append(f"YouTube: {type(e).__name__}: {e}")
    print(f"[publish] {urls}")

    if urls:  # 한 곳이라도 성공하면 '발행됨'으로 기록 → 중복 발행 방지
        C.mark_published(state, case, today, urls)
        C.save_state(state)
        _gh_output(state_changed="true")
    if errors:
        notify_failure(settings, "업로드 일부/전체 실패", f"판례: {case['id']}\n" + "\n".join(errors))
        return 1
    if not urls:
        notify_failure(settings, "발행 대상 플랫폼 없음", "ENABLE_INSTAGRAM / ENABLE_YOUTUBE 설정을 확인하세요.")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="노동 판례 숏폼 생성기")
    ap.add_argument("--test", action="store_true", help="발행 없이 영상만 생성")
    ap.add_argument("--offline", action="store_true", help="개발용: Gemini/TTS 없이 렌더링만 확인 (--test 필요)")
    ap.add_argument("--case-id", default=None, help="특정 판례 id 지정")
    args = ap.parse_args(argv)
    if args.offline and not args.test:
        ap.error("--offline은 --test와 함께만 쓸 수 있습니다")
    if args.case_id is not None and not args.case_id.strip():
        args.case_id = None

    settings = Settings()
    try:
        return run(args, settings)
    except NotConfigured as e:
        print(f"[idle] {e}")
        return 0
    except Skip as e:
        msg = str(e)
        print(f"[skip] {msg}")
        notify_failure(settings, "오늘 발행 건너뜀" + (" (테스트)" if args.test else ""), msg)
        # 테스트 모드에서는 Skip도 실패로 처리해 결과를 바로 알 수 있게 함
        return 1 if args.test else 0
    except (LLMError, C.CaseError, Exception) as e:
        tb = redact(traceback.format_exc(limit=5), settings)
        print(tb, file=sys.stderr)
        notify_failure(settings, "파이프라인 오류", f"{type(e).__name__}: {e}\n\n{tb[-1500:]}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
