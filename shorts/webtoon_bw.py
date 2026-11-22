"""흑백 선화 웹툰 컷.

레퍼런스 구성: 위에 내레이션 한 줄, 그 아래 말풍선 둘, 맨 아래 장면 그림.
그림은 장면마다 통째로 생성한 일러스트를 쓴다(인물 합성이 아니다).
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .config import DISCLAIMER

W, H = 1080, 1920
INK = (28, 28, 30)
PAPER = (252, 251, 248)
MARGIN = 26
BORDER = 5


def _wrap(d, text, font, max_w) -> list[str]:
    lines, cur = [], ""
    for ch in text:
        if ch == "\n" or (d.textlength(cur + ch, font=font) > max_w and cur):
            cut = cur.rfind(" ")
            if ch != "\n" and cut > len(cur) * 0.5:
                lines.append(cur[:cut]); cur = cur[cut + 1:] + ch
            else:
                lines.append(cur); cur = "" if ch == "\n" else ch
        else:
            cur += ch
    if cur.strip():
        lines.append(cur)
    return lines or [""]


def _fit_font(d, text, path, max_w, max_lines, start, floor=30):
    """글자가 넘치지 않을 때까지 크기를 줄인다."""
    size = start
    while size > floor:
        f = ImageFont.truetype(path, size)
        if len(_wrap(d, text, f, max_w)) <= max_lines:
            return f, _wrap(d, text, f, max_w)
        size -= 3
    f = ImageFont.truetype(path, floor)
    return f, _wrap(d, text, f, max_w)


def _ellipse_bubble(d, text, font, cx, cy, max_w, tail_to) -> None:
    """타원 말풍선 + 인물을 향하는 꼬리."""
    lines = _wrap(d, text, font, max_w - 70)
    tw = max(d.textlength(l, font=font) for l in lines)
    gap = int(font.size * 1.36)
    bw, bh = tw + 92, gap * len(lines) + 70
    box = [cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2]

    tx, ty = tail_to
    d.polygon([(cx - 34, cy + bh / 2 - 16), (cx + 34, cy + bh / 2 - 16), (tx, ty)],
              fill=PAPER, outline=INK)
    d.ellipse(box, fill=PAPER, outline=INK, width=BORDER)
    d.polygon([(cx - 30, cy + bh / 2 - 22), (cx + 30, cy + bh / 2 - 22), (tx, ty)], fill=PAPER)
    d.line([(cx - 30, cy + bh / 2 - 24), (tx, ty)], fill=INK, width=BORDER)
    d.line([(cx + 30, cy + bh / 2 - 24), (tx, ty)], fill=INK, width=BORDER)

    y = cy - gap * len(lines) / 2 + 6
    for l in lines:
        d.text((cx - d.textlength(l, font=font) / 2, y), l, font=font, fill=INK)
        y += gap


def render_cut(fpath: str, narration: str, lines_lr: tuple[str, str] | None,
               scene_image: Path | None, out, callout: str | None = None) -> None:
    """narration: 위쪽 서술. lines_lr: (왼쪽 대사, 오른쪽 대사).
    callout: 숫자처럼 크게 보여야 할 한 줄 — 서술 아래 상자 안에 넣는다."""
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    d.rectangle([MARGIN, MARGIN, W - MARGIN, H - MARGIN], outline=INK, width=BORDER)

    # 1) 서술 — 말풍선 없이 위쪽에
    f_nar, nar_lines = _fit_font(d, narration, fpath, W - 240, 3, 64)
    y = 150
    for l in nar_lines:
        d.text(((W - d.textlength(l, font=f_nar)) / 2, y), l, font=f_nar, fill=INK)
        y += int(f_nar.size * 1.42)

    # 1-2) 강조 상자 — 숫자는 글로 흘리면 안 읽힌다
    if callout:
        f_co, co_lines = _fit_font(d, callout, fpath, W - 300, 2, 76, floor=44)
        gap = int(f_co.size * 1.3)
        bh = gap * len(co_lines) + 54
        y += 30
        d.rounded_rectangle([110, y, W - 110, y + bh], radius=22,
                            fill=(242, 242, 240), outline=INK, width=BORDER)
        ty = y + 27
        for l in co_lines:
            d.text(((W - d.textlength(l, font=f_co)) / 2, ty), l, font=f_co, fill=INK)
            ty += gap
        y += bh

    # 2) 말풍선 둘 — 아래 그림 속 인물을 향해 꼬리가 내려간다
    if lines_lr and any(lines_lr):
        bub_cy = max(y + 170, 540)
        left, right = lines_lr
        f_b = ImageFont.truetype(fpath, 46)
        if left:
            _ellipse_bubble(d, left, f_b, 300, bub_cy, 430, tail_to=(250, bub_cy + 190))
        if right:
            _ellipse_bubble(d, right, f_b, 782, bub_cy, 430, tail_to=(840, bub_cy + 190))
        top = bub_cy + 220
    else:
        # 말풍선이 없으면 그림을 바로 올려 빈 공간을 없앤다
        top = y + 70

    # 3) 장면 그림 — 아래쪽을 채운다
    avail_h = H - MARGIN - 120 - top
    if scene_image and Path(scene_image).exists():
        sc = Image.open(scene_image).convert("L").convert("RGB")
        ratio = min((W - MARGIN * 2 - 20) / sc.width, avail_h / sc.height)
        sc = sc.resize((int(sc.width * ratio), int(sc.height * ratio)), Image.LANCZOS)
        img.paste(sc, ((W - sc.width) // 2, top + (avail_h - sc.height) // 2))

    # 4) 고지 문구
    f_foot = ImageFont.truetype(fpath, 30)
    w = d.textlength(DISCLAIMER, font=f_foot)
    d.text(((W - w) / 2, H - MARGIN - 78), DISCLAIMER, font=f_foot, fill=(120, 120, 120))

    img.save(out, "PNG")
