"""흑백 선화 웹툰 숏폼 1편을 만든다(데모).

장면 그림은 assets/scenes/ 에서 가져오고, 서술문과 말풍선은 아래 CUTS에 적는다.
음성은 edge-tts가 막힌 환경을 위해 무음으로 대체할 수 있다.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from shorts import webtoon_bw as BW  # noqa: E402

FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"

# 서술과 두 인물의 목소리를 나눈다 — 웹툰은 누가 말하는지가 드러나야 읽힌다
VOICE_NARRATOR = "ko-KR-SunHiNeural"
VOICE_LEFT = "ko-KR-InJoonNeural"        # 방앗간 주인
VOICE_RIGHT = "ko-KR-HyunsuMultilingualNeural"  # 일꾼 돌쇠
PAUSE = 0.35                              # 대사 사이 숨
SCENES = ROOT / "assets" / "scenes"
OUT = ROOT / "output" / "webtoon_demo"

from webtoon_scripts import SCRIPTS  # noqa: E402


def load_case(case_id: str) -> dict:
    """판례 원문 정보는 cases.json 그대로 쓴다 — 지어내면 안 되는 값이다."""
    data = json.loads((ROOT / "data" / "cases.json").read_text(encoding="utf-8"))
    cases = data if isinstance(data, list) else data.get("cases", [])
    for c in cases:
        if c.get("id") == case_id:
            return c
    raise SystemExit(f"cases.json 에 '{case_id}' 가 없습니다.")


def tts(text: str, voice: str, out: Path) -> Path:
    import edge_tts

    async def go() -> None:
        await edge_tts.Communicate(text.replace("\n", " "), voice, rate="+6%").save(str(out))

    asyncio.run(go())
    return out


def dur_of(path: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    return float(r.stdout.strip() or 0)


def silence(seconds: float, out: Path) -> Path:
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
         "-i", "anullsrc=r=24000:cl=mono", "-t", f"{seconds:.2f}", str(out)])
    return out


def cut_audio(i: int, nar: str, left: str, right: str, work: Path,
              silent: bool) -> tuple[Path, float]:
    """컷 하나의 음성을 만든다. 서술 → (왼쪽 대사) → (오른쪽 대사) 순."""
    if silent:
        a = silence(4.5, work / f"a{i:02d}.mp3")
        return a, dur_of(a)
    parts = []
    for n, (text, voice) in enumerate([(nar, VOICE_NARRATOR), (left, VOICE_LEFT),
                                       (right, VOICE_RIGHT)]):
        if not text.strip():
            continue
        if parts:
            parts.append(silence(PAUSE, work / f"a{i:02d}_{n}_gap.mp3"))
        parts.append(tts(text, voice, work / f"a{i:02d}_{n}.mp3"))
    lst = work / f"a{i:02d}.txt"
    lst.write_text("".join(f"file '{x.name}'\n" for x in parts), encoding="utf-8")
    out = work / f"a{i:02d}.mp3"
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
         "-i", str(lst), "-c", "copy", str(out)])
    return out, dur_of(out)


def run(cmd: list[str]) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"ffmpeg 실패: {r.stderr[-800:]}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--silent", action="store_true",
                    help="edge-tts를 쓸 수 없는 환경에서 무음으로 만든다")
    ap.add_argument("--case", default="severance-installment-2010", help="판례 id")
    args = ap.parse_args()

    cuts = SCRIPTS.get(args.case)
    if not cuts:
        raise SystemExit(f"'{args.case}' 대본이 webtoon_scripts.py 에 없습니다. "
                         f"있는 것: {', '.join(SCRIPTS)}")
    case = load_case(args.case)
    out_dir = OUT / args.case
    out_dir.mkdir(parents=True, exist_ok=True)
    segs = []
    for i, (nar, left, right, scene, callout) in enumerate(cuts):
        png = out_dir / f"cut{i:02d}.png"
        BW.render_cut(FONT, nar, (left, right) if (left or right) else None,
                      SCENES / scene, png, callout=callout)
        spoken = nar + ((" " + callout.replace("\n", " ")) if callout else "")
        audio, dur = cut_audio(i, spoken, left, right, out_dir, args.silent)
        dur += 0.5  # 끝에 여백 — 자막을 다 읽을 시간
        seg = out_dir / f"seg{i:02d}.mp4"

        # 컷마다 다른 Ken Burns — 같은 그림을 써도 지루하지 않게
        frames = int(dur * 30)
        z = (f"min(1+0.09*on/{frames},1.09)" if i % 2 == 0
             else f"max(1.09-0.09*on/{frames},1)")
        cx = "iw/2-(iw/zoom/2)"
        drift = f"iw*0.05*on/{frames}"
        x_expr = {0: cx, 1: f"{cx}+{drift}", 2: f"{cx}-{drift}"}[i % 3]
        vf = (f"scale=2160:3840,zoompan=z='{z}':x='{x_expr}'"
              f":y='ih/2-(ih/zoom/2)':d={frames}:s=1080x1920:fps=30,setsar=1")
        run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", str(png),
             "-i", str(audio), "-af", "apad=pad_dur=0.5", "-t", f"{dur:.2f}",
             "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-r", "30",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
             "-ar", "44100", "-ac", "2", str(seg)])
        segs.append(seg)
        print(f"  컷 {i + 1}/{len(cuts)} — {dur:.1f}초")

    # 마지막 컷 — 판례 원문 정보
    card = out_dir / "cut_case.png"
    BW.render_case_card(FONT, case, card)
    card_text = (f"이 이야기의 판례는 {case['court']} {case['date']} 선고 "
                 f"{case['case_no']} 판결입니다.")
    card_audio, card_dur = cut_audio(99, card_text, "", "", out_dir, args.silent)
    card_dur += 1.2
    seg = out_dir / "seg_case.mp4"
    run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", str(card),
         "-i", str(card_audio), "-af", "apad=pad_dur=1.2", "-t", f"{card_dur:.2f}",
         "-vf", "scale=1080:1920,setsar=1", "-c:v", "libx264", "-preset", "veryfast",
         "-r", "30", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
         "-ar", "44100", "-ac", "2", str(seg)])
    segs.append(seg)
    print(f"  판례 카드 — {card_dur:.1f}초")

    lst = out_dir / "list.txt"
    lst.write_text("".join(f"file '{s.name}'\n" for s in segs), encoding="utf-8")
    final = out_dir / "webtoon_short.mp4"
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
         "-i", str(lst), "-c", "copy", str(final)])
    print(f"완성: {final} ({dur_of(final):.1f}초)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
