"""음성(edge-tts)과 9:16 영상(Pillow + FFmpeg) 생성."""
from __future__ import annotations

import asyncio
import shutil
import subprocess
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .config import DISCLAIMER, Settings

W, H = 1080, 1920
FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
]
PALETTES = [  # (배경 위, 배경 아래, 강조색)
    ((34, 40, 49), (57, 62, 70), (255, 211, 105)),
    ((40, 54, 24), (96, 108, 56), (254, 250, 224)),
    ((27, 38, 59), (65, 90, 119), (224, 225, 221)),
    ((61, 52, 139), (118, 120, 237), (247, 184, 1)),
]


class MediaError(RuntimeError):
    pass


def _run(cmd: list[str]) -> str:
    # 리스트 인자로 실행(shell=False) → 셸 인젝션 불가
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise MediaError(f"{cmd[0]} 실패: {p.stderr[-800:]}")
    return p.stdout


def find_font(settings: Settings) -> str:
    for c in [settings.font_path, *FONT_CANDIDATES]:
        if c and Path(c).exists():
            return c
    raise MediaError("한글 폰트를 찾지 못했습니다. fonts-noto-cjk 설치 또는 FONT_PATH 지정 필요")


def audio_duration(path: Path) -> float:
    out = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(path)])
    return float(out.strip())


# ---------- TTS ----------
async def _tts_all(items: list[tuple[str, Path]], voice: str, rate: str) -> None:
    import edge_tts
    for text, path in items:
        for attempt in range(3):
            try:
                await edge_tts.Communicate(text, voice, rate=rate).save(str(path))
                break
            except Exception:  # 네트워크 일시 오류 재시도
                if attempt == 2:
                    raise
                await asyncio.sleep(3 * (attempt + 1))


def synthesize(settings: Settings, texts: list[str], workdir: Path, *, offline: bool = False) -> list[Path]:
    paths = [workdir / f"a{i:02d}.mp3" for i in range(len(texts))]
    if offline:
        # 개발용: 네트워크 없이 글자 수 비례 무음 생성
        for t, p in zip(texts, paths):
            dur = max(2.0, len(t) * 0.11)
            _run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                  "anullsrc=r=24000:cl=mono", "-t", f"{dur:.2f}", "-q:a", "9", str(p)])
        return paths
    asyncio.run(_tts_all(list(zip(texts, paths)), settings.tts_voice, settings.tts_rate))
    return paths


# ---------- 프레임 ----------
def _gradient(top, bottom) -> Image.Image:
    img = Image.new("RGB", (W, H), top)
    d = ImageDraw.Draw(img)
    for y in range(H):
        r = y / H
        d.line([(0, y), (W, y)], fill=tuple(int(top[i] + (bottom[i] - top[i]) * r) for i in range(3)))
    return img


def _wrap(text: str, font, max_w: int, draw: ImageDraw.ImageDraw) -> list[str]:
    lines: list[str] = []
    for para in text.split("\n"):
        cur = ""
        for ch in para:
            if draw.textlength(cur + ch, font=font) > max_w and cur:
                # 단어 중간 줄바꿈을 줄이기 위해 마지막 공백에서 자름
                cut = cur.rfind(" ")
                if cut > len(cur) * 0.5:
                    lines.append(cur[:cut])
                    cur = cur[cut + 1:] + ch
                else:
                    lines.append(cur)
                    cur = ch
            else:
                cur += ch
        lines.append(cur)
    return [l for l in lines if l.strip()] or [""]


def _draw_block(d, lines, font, y, fill, line_gap=1.35, center=True, x=90):
    size = font.size
    for line in lines:
        if center:
            w = d.textlength(line, font=font)
            d.text(((W - w) / 2, y), line, font=font, fill=fill)
        else:
            d.text((x, y), line, font=font, fill=fill)
        y += int(size * line_gap)
    return y


FOOTER_Y = H - 470  # 릴스/쇼츠 하단 UI(좋아요·캡션)에 가리지 않는 위치


def _footer(d, fpath):
    f = ImageFont.truetype(fpath, 36)
    w = d.textlength(DISCLAIMER, font=f)
    pad = 28
    d.rounded_rectangle([(W - w) / 2 - pad, FOOTER_Y - 18, (W + w) / 2 + pad, FOOTER_Y + 58],
                        radius=20, fill=(0, 0, 0))
    d.text(((W - w) / 2, FOOTER_Y), DISCLAIMER, font=f, fill=(240, 240, 240))


def render_scene(fpath: str, idx: int, total: int, header: str, caption: str, narration: str,
                 out: Path) -> None:
    top, bottom, accent = PALETTES[idx % len(PALETTES)]
    img = _gradient(top, bottom)
    d = ImageDraw.Draw(img)
    f_head = ImageFont.truetype(fpath, 46)
    f_cap = ImageFont.truetype(fpath, 92)
    f_body = ImageFont.truetype(fpath, 56)

    _draw_block(d, _wrap(header, f_head, W - 180, d), f_head, 170, (220, 220, 220))
    d.text((W - 190, 260), f"{idx + 1}/{total}", font=f_head, fill=(200, 200, 200))
    y = 620
    if caption:
        y = _draw_block(d, _wrap(caption, f_cap, W - 160, d), f_cap, y, accent) + 60
    _draw_block(d, _wrap(narration, f_body, W - 180, d), f_body, max(y, 900), (255, 255, 255), 1.45)
    _footer(d, fpath)
    img.save(out, "PNG")


def render_case_card(fpath: str, case: dict, out: Path) -> None:
    """마지막 장면: LLM을 거치지 않은 cases.json 원문 데이터만 표시."""
    img = _gradient((15, 15, 20), (40, 40, 50))
    d = ImageDraw.Draw(img)
    f_t = ImageFont.truetype(fpath, 60)
    f_k = ImageFont.truetype(fpath, 40)
    f_v = ImageFont.truetype(fpath, 44)
    y = _draw_block(d, ["오늘의 판례 원문 정보"], f_t, 200, (255, 211, 105)) + 40
    rows = [
        ("법원", f"{case['court']} {case.get('decision_type', '')}".strip()),
        ("선고일", case["date"]),
        ("사건번호", case["case_no"]),
        ("쟁점", case["title"]),
    ]
    for k, v in rows:
        d.text((90, y), k, font=f_k, fill=(170, 170, 170))
        y = _draw_block(d, _wrap(v, f_v, W - 180, d), f_v, y + 55, (255, 255, 255), center=False) + 25
    d.text((90, y + 10), "판결요지", font=f_k, fill=(170, 170, 170))
    # 판결요지는 원문이므로 자르지 않고, 들어갈 때까지 글자 크기를 줄인다
    top, bottom = y + 70, FOOTER_Y - 130
    for size in range(38, 21, -2):
        f_h = ImageFont.truetype(fpath, size)
        lines = _wrap(case["holding"], f_h, W - 180, d)
        if len(lines) * int(size * 1.4) <= bottom - top:
            break
    else:
        raise MediaError("판결요지가 너무 길어 마지막 장면에 들어가지 않습니다. cases.json의 holding을 줄이세요.")
    _draw_block(d, lines, f_h, top, (235, 235, 235), 1.4, center=False)
    f_w = ImageFont.truetype(fpath, 34)
    note = "정확한 내용은 판결 원문을 확인하세요."
    d.text(((W - d.textlength(note, font=f_w)) / 2, FOOTER_Y - 90), note, font=f_w, fill=(200, 200, 200))
    _footer(d, fpath)
    img.save(out, "PNG")


# ---------- 영상 ----------
def make_segment(image: Path, audio: Path, out: Path, pad: float = 0.35) -> None:
    dur = audio_duration(audio) + pad
    _run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", str(image), "-i", str(audio),
          "-af", f"apad=pad_dur={pad}", "-t", f"{dur:.3f}",
          "-c:v", "libx264", "-tune", "stillimage", "-preset", "veryfast", "-r", "30",
          "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2", str(out)])


def concat(segments: list[Path], out: Path) -> None:
    lst = out.parent / "concat.txt"
    lst.write_text("".join(f"file '{p.resolve().as_posix()}'\n" for p in segments), encoding="utf-8")
    _run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
          "-c", "copy", "-movflags", "+faststart", str(out)])


def check_tools() -> None:
    for t in ("ffmpeg", "ffprobe"):
        if not shutil.which(t):
            raise MediaError(f"{t}가 설치되어 있지 않습니다")


def build_video(settings: Settings, case: dict, script: dict, workdir: Path, out: Path,
                *, offline: bool = False) -> Path:
    from .config import DISCLAIMER_NARRATION
    check_tools()
    workdir.mkdir(parents=True, exist_ok=True)
    fpath = find_font(settings)
    scenes = script["scenes"]
    texts = [s["narration"] for s in scenes] + [DISCLAIMER_NARRATION]
    audios = synthesize(settings, texts, workdir, offline=offline)

    segs = []
    header = script.get("hook") or case["title"]
    for i, s in enumerate(scenes):
        img = workdir / f"f{i:02d}.png"
        render_scene(fpath, i, len(scenes), header, s.get("caption", ""), s["narration"], img)
        seg = workdir / f"s{i:02d}.mp4"
        make_segment(img, audios[i], seg)
        segs.append(seg)
    card = workdir / "f_case.png"
    render_case_card(fpath, case, card)
    seg = workdir / "s_case.mp4"
    make_segment(card, audios[-1], seg, pad=2.5)  # 원문 정보를 읽을 시간 확보
    segs.append(seg)
    concat(segs, out)
    return out
