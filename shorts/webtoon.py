"""웹툰 컷 렌더러.

한 장면 = 한 컷. 말풍선·효과음·집중선으로 숏폼에서도 읽히게 그린다.
정지 이미지라 영상 생성 비용이 들지 않는다.
"""
from __future__ import annotations

import math
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import characters as CH
from .config import DISCLAIMER

W, H = 1080, 1920

# 컷마다 바뀌는 배경 톤 (종이 느낌의 밝은 색 + 강조색)
TONES = [
    ((255, 246, 230), (255, 214, 165), (40, 36, 34)),
    ((232, 244, 255), (168, 208, 255), (26, 38, 58)),
    ((255, 235, 238), (255, 173, 186), (58, 26, 34)),
    ((236, 252, 238), (166, 226, 180), (26, 50, 34)),
    ((245, 240, 255), (198, 180, 255), (40, 30, 60)),
]
PANEL_M = 36          # 컷 바깥 여백
BUBBLE_PAD = 34
INK = (24, 22, 20)


def _tone(idx: int):
    return TONES[idx % len(TONES)]


def _speed_lines(img: Image.Image, cx: int, cy: int, color, n: int = 90) -> None:
    """집중선 — 극적인 컷에 쓴다."""
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    rnd = random.Random(cx * 7919 + cy)
    for _ in range(n):
        a = rnd.uniform(0, math.tau)
        r0 = rnd.uniform(380, 560)
        r1 = r0 + rnd.uniform(500, 1100)
        wdt = rnd.choice([2, 3, 4, 6])
        d.line([(cx + math.cos(a) * r0, cy + math.sin(a) * r0),
                (cx + math.cos(a) * r1, cy + math.sin(a) * r1)],
               fill=color + (rnd.randint(40, 110),), width=wdt)
    img.alpha_composite(layer.filter(ImageFilter.GaussianBlur(0.6)))


def _halftone(img: Image.Image, color, step: int = 18, r: int = 3) -> None:
    """망점 톤 — 배경에 깔아 종이 느낌을 낸다."""
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for y in range(0, H, step):
        off = (y // step % 2) * step // 2
        for x in range(-step, W + step, step):
            d.ellipse([x + off - r, y - r, x + off + r, y + r], fill=color + (26,))
    img.alpha_composite(layer)


def _wrap(d, text, font, max_w) -> list[str]:
    lines, cur = [], ""
    for ch in text:
        if ch == "\n" or (d.textlength(cur + ch, font=font) > max_w and cur):
            cut = cur.rfind(" ")
            if ch != "\n" and cut > len(cur) * 0.55:
                lines.append(cur[:cut]); cur = cur[cut + 1:] + ch
            else:
                lines.append(cur); cur = "" if ch == "\n" else ch
        else:
            cur += ch
    if cur.strip():
        lines.append(cur)
    return lines or [""]


def _bubble(img: Image.Image, d: ImageDraw.ImageDraw, text: str, font,
            box: tuple[int, int, int, int], tail_x: int, tail_down: bool) -> None:
    """말풍선 + 꼬리. box는 (x0, y0, x1, y1)."""
    x0, y0, x1, y1 = box
    # 그림자
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle([x0 + 8, y0 + 10, x1 + 8, y1 + 10],
                                         radius=46, fill=(0, 0, 0, 70))
    img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(9)))

    d.rounded_rectangle([x0, y0, x1, y1], radius=46, fill=(255, 255, 255), outline=INK, width=7)
    ty = y1 if tail_down else y0
    dy = 54 if tail_down else -54
    d.polygon([(tail_x - 40, ty), (tail_x + 40, ty), (tail_x + 6, ty + dy)],
              fill=(255, 255, 255), outline=INK)
    # 꼬리가 테두리를 덮도록 선 한 번 더
    d.line([(tail_x - 40, ty), (tail_x + 40, ty)], fill=(255, 255, 255), width=7)

    lines = _wrap(d, text, font, x1 - x0 - BUBBLE_PAD * 2)
    gap = int(font.size * 1.38)
    y = (y0 + y1) // 2 - gap * len(lines) // 2 + 4
    for ln in lines:
        d.text(((x0 + x1 - d.textlength(ln, font=font)) / 2, y), ln, font=font, fill=INK)
        y += gap


def _sfx(img: Image.Image, text: str, font, xy, accent) -> None:
    """효과음 — 기울인 테두리 글자."""
    pad = 60
    tmp = Image.new("RGBA", (int(font.size * len(text) * 1.5) + pad * 2, font.size * 2 + pad * 2),
                    (0, 0, 0, 0))
    td = ImageDraw.Draw(tmp)
    td.text((pad, pad), text, font=font, fill=accent, stroke_width=11, stroke_fill=(255, 255, 255))
    td.text((pad, pad), text, font=font, fill=accent, stroke_width=4, stroke_fill=INK)
    tmp = tmp.rotate(-7, resample=Image.BICUBIC, expand=True)
    img.alpha_composite(tmp, (max(0, xy[0]), max(0, xy[1])))


def render_cut(fpath: str, idx: int, total: int, header: str, caption: str, narration: str,
               out, character: str | None = None, dramatic: bool = False) -> None:
    bg, accent, ink = _tone(idx)
    img = Image.new("RGBA", (W, H), bg)
    d = ImageDraw.Draw(img)

    # 배경: 위에서 아래로 강조색이 옅게 깔리게
    grad = Image.new("RGBA", (W, H))
    gd = ImageDraw.Draw(grad)
    for y in range(H):
        t = (y / H) ** 1.4
        gd.line([(0, y), (W, y)],
                fill=tuple(int(bg[i] + (accent[i] - bg[i]) * t) for i in range(3)) + (255,))
    img = grad.convert("RGBA")
    _halftone(img, ink)
    if dramatic:
        _speed_lines(img, W // 2, int(H * 0.55), ink)

    d = ImageDraw.Draw(img)
    f_head = ImageFont.truetype(fpath, 42)
    f_sfx = ImageFont.truetype(fpath, 104)
    f_body = ImageFont.truetype(fpath, 52)
    f_foot = ImageFont.truetype(fpath, 32)

    # 컷 테두리
    d.rounded_rectangle([PANEL_M, PANEL_M, W - PANEL_M, H - PANEL_M],
                        radius=28, outline=INK, width=9)

    # 머리말 + 컷 번호
    d.text((PANEL_M + 40, PANEL_M + 34), header[:28], font=f_head, fill=ink)
    num = f"{idx + 1}/{total}"
    d.text((W - PANEL_M - 40 - d.textlength(num, font=f_head), PANEL_M + 34),
           num, font=f_head, fill=ink)

    # 세로 배치: 효과음 → 말풍선 → 캐릭터 → 고지. 서로 겹치지 않게 띄운다.
    left = idx % 2 == 1
    SFX_Y, BUB_Y0, BUB_Y1, CHAR_TOP, CHAR_H = 128, 440, 830, 860, 730

    if caption:
        _sfx(img, caption, f_sfx, (110 if not left else W - 640, SFX_Y), accent)
        d = ImageDraw.Draw(img)

    # 말풍선 — 캐릭터 머리 위에서 꼬리가 아래를 향한다
    bx0 = 80 if not left else W - 80 - 700
    tail = bx0 + (600 if not left else 100)
    _bubble(img, d, narration, f_body, (bx0, BUB_Y0, bx0 + 700, BUB_Y1),
            tail_x=min(W - 130, max(130, tail)), tail_down=True)

    # 캐릭터 — 말풍선 아래, 고지 문구 위
    if character:
        CH.paste_top(img, character, CH.PANEL_BUST, CHAR_H,
                     anchor="left" if left else "right", top=CHAR_TOP)
        d = ImageDraw.Draw(img)

    # 고지 문구
    w = d.textlength(DISCLAIMER, font=f_foot)
    fy = H - 300
    d.rounded_rectangle([(W - w) / 2 - 24, fy - 14, (W + w) / 2 + 24, fy + 48],
                        radius=18, fill=(255, 255, 255, 230), outline=INK, width=3)
    d.text(((W - w) / 2, fy), DISCLAIMER, font=f_foot, fill=INK)

    img.convert("RGB").save(out, "PNG")
