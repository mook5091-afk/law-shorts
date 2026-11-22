"""HuggingFace ZeroGPU Space로 '말하는 캐릭터'를 만들 수 있는지 실측한다.

쓰는 것: 캐릭터 시트의 얼굴 패널 + edge-tts 음성 1개 → Space API 1회 호출.
재는 것: 호출 성공 여부, 걸린 시간, 남은 GPU 할당량(오류 메시지에 들어 있다).

  python scripts/test_hf_avatar.py                      # 기본 Space로 1회
  python scripts/test_hf_avatar.py --space <id> --character lawyer
  HF_TOKEN=hf_xxx python scripts/test_hf_avatar.py      # 토큰이 있으면 할당량이 늘어난다

토큰은 인자로 받지 않는다(명령 기록에 남는다). 환경변수나 Secrets로만 넘길 것.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 후보 Space. 앞에서부터 시도하고, 살아 있는 첫 번째를 쓴다.
DEFAULT_SPACES = [
    "fffiloni/tts-hallo-talking-portrait",
    "vinthony/SadTalker",
    "KwaiVGI/LivePortrait",
]
SAMPLE_TEXT = "월급에 퇴직금을 나눠 넣기로 한 약속은, 원칙적으로 무효입니다."


def make_audio(out: Path, voice: str = "ko-KR-SunHiNeural") -> Path:
    import edge_tts

    async def go() -> None:
        await edge_tts.Communicate(SAMPLE_TEXT, voice, rate="+8%").save(str(out))

    asyncio.run(go())
    return out


def make_face(character: str, out: Path, size: int = 512) -> Path:
    from shorts import characters as CH

    img = CH.panel(character, CH.PANEL_FACE, size)
    if img is None:
        raise SystemExit(f"캐릭터 '{character}'의 시트 PNG가 assets/characters/ 에 없습니다.")
    # 토킹헤드 모델은 대부분 알파 채널을 못 받는다 → 흰 배경에 합성
    from PIL import Image

    bg = Image.new("RGB", img.size, (245, 245, 245))
    bg.paste(img, (0, 0), img)
    bg.save(out, "PNG")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--space", action="append", default=None, help="시도할 Space id(여러 번 가능)")
    ap.add_argument("--character", default="lawyer")
    args = ap.parse_args()

    from gradio_client import Client, handle_file

    work = ROOT / "output" / "hf_test"
    work.mkdir(parents=True, exist_ok=True)
    audio = make_audio(work / "sample.mp3")
    face = make_face(args.character, work / "face.png")
    print(f"[입력] 얼굴 {face.name} / 음성 {audio.name} ({audio.stat().st_size // 1024} KB)")

    token = os.environ.get("HF_TOKEN") or None
    print(f"[토큰] {'있음 — 계정 할당량 적용 시도' if token else '없음 — 비로그인 할당량(하루 2분)'}")

    for space in (args.space or DEFAULT_SPACES):
        print(f"\n=== {space} ===")
        t0 = time.time()
        client = None
        # gradio_client는 버전에 따라 token= / hf_token= 을 쓴다
        for kw in ("token", "hf_token"):
            try:
                client = Client(space, **({kw: token} if token else {}))
                break
            except TypeError:
                continue
            except Exception as e:
                print(f"  [접속 실패] {type(e).__name__}: {str(e)[:250]}")
                break
        if client is None:
            continue
        try:
            api = client.view_api(return_format="dict")
            names = list(api.get("named_endpoints", {}))
            print(f"  [엔드포인트] {names[:5]}")
        except Exception as e:
            print(f"  [API 조회 실패] {type(e).__name__}: {str(e)[:150]}")
            names = []
        if not names:
            continue
        try:
            result = client.predict(handle_file(str(face)), handle_file(str(audio)),
                                    api_name=names[0])
            print(f"  [성공] {time.time() - t0:.1f}초 — {str(result)[:300]}")
            return 0
        except Exception as e:
            msg = str(e)
            print(f"  [생성 실패] {type(e).__name__}: {msg[:400]}")
            if "quota" in msg.lower():
                print("  >> 할당량 메시지입니다. 남은 초가 적혀 있으면 그게 실제 한도입니다.")

    print("\n모든 후보 Space에서 실패했습니다. --space 로 다른 Space를 지정해 보세요.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
