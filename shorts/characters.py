"""캐릭터 시트에서 패널을 잘라 배경을 지우고 장면에 합성한다.

시트는 가로 3등분이다: 0=전신, 1=상반신, 2=얼굴.
배경은 균일한 회색이므로 테두리에서 flood fill로 지운다.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from .config import ROOT

ASSET_DIR = ROOT / "assets" / "characters"
MANIFEST = ASSET_DIR / "characters.json"
PANEL_FULL, PANEL_BUST, PANEL_FACE = 0, 1, 2
_CUT = (255, 0, 255)  # flood fill 표식 — 캐릭터에 없는 색

# 장면 내레이션에 이 단어가 있으면 그 캐릭터를 쓴다(대본에 character가 없을 때의 대비책)
KEYWORDS = {
    "worker": ("돌쇠", "일꾼", "근로자", "직원", "노동자"),
    "boss": ("주인", "사장", "사업주", "회사"),
    "lawyer": ("원님", "법원", "대법원", "판단", "판결", "변호"),
}


@lru_cache(maxsize=1)
def load_manifest() -> dict:
    if not MANIFEST.exists():
        return {"characters": []}
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def available() -> frozenset[str]:
    """시트 PNG가 실제로 있는 캐릭터 id."""
    return frozenset(
        c["id"] for c in load_manifest().get("characters", [])
        if (ASSET_DIR / c["file"]).exists()
    )


def pick(narration: str, explicit: str | None = None) -> str | None:
    have = available()
    if not have:
        return None
    if explicit and explicit in have:
        return explicit
    best, best_at = None, len(narration) + 1
    for cid, words in KEYWORDS.items():
        if cid not in have:
            continue
        for w in words:
            at = narration.find(w)
            if at != -1 and at < best_at:
                best, best_at = cid, at
    return best


def _sheet_path(cid: str) -> Path | None:
    for c in load_manifest().get("characters", []):
        if c["id"] == cid:
            return ASSET_DIR / c["file"]
    return None


def _strip_background(panel: Image.Image, thresh: int = 42) -> Image.Image:
    """테두리에서 flood fill로 배경을 지우고 RGBA로 돌려준다.

    씨앗은 '배경색과 비슷한 테두리 픽셀'만 쓴다. 인물은 보통 아래 테두리에
    걸쳐 있어서, 테두리를 무조건 훑으면 몸통 안에서 fill이 시작돼 구멍이 난다.
    """
    rgb = panel.convert("RGB")
    w, h = rgb.size
    px = rgb.load()
    bg = px[1, 1]  # 좌상단은 언제나 배경

    def near_bg(c, tol=26):
        return all(abs(c[i] - bg[i]) <= tol for i in range(3))

    step = max(6, min(w, h) // 60)
    border = ([(x, 1) for x in range(1, w - 1, step)]
              + [(x, h - 2) for x in range(1, w - 1, step)]
              + [(1, y) for y in range(1, h - 1, step)]
              + [(w - 2, y) for y in range(1, h - 1, step)])
    for xy in border:
        if not near_bg(px[xy]):
            continue
        try:
            ImageDraw.floodfill(rgb, xy, _CUT, thresh=thresh)
        except ValueError:
            pass

    out = rgb.convert("RGBA")
    o = out.load()
    for y in range(h):
        for x in range(w):
            if o[x, y][:3] == _CUT:
                o[x, y] = (0, 0, 0, 0)
    a = out.getchannel("A").filter(ImageFilter.GaussianBlur(1.2))
    out.putalpha(a)
    return out


@lru_cache(maxsize=16)
def panel(cid: str, which: int, target_h: int) -> Image.Image | None:
    """캐릭터 패널을 배경 없는 RGBA로, 높이 target_h에 맞춰 돌려준다."""
    p = _sheet_path(cid)
    if p is None or not p.exists():
        return None
    sheet = Image.open(p)
    w, h = sheet.size
    third = w // 3
    # 옆 패널이 몇 픽셀 딸려 들어오면 배경 제거 후 얼룩으로 남는다 → 좌우를 조금 안쪽으로
    inset = int(third * 0.06)
    cut = sheet.crop((third * which + inset, 0, third * (which + 1) - inset, h))
    cut = _strip_background(cut)
    cut = cut.crop(cut.getbbox() or (0, 0, cut.width, cut.height))
    ratio = target_h / cut.height
    return cut.resize((max(1, int(cut.width * ratio)), target_h), Image.LANCZOS)


def paste(base: Image.Image, cid: str, which: int, target_h: int,
          anchor: str = "right", bottom: int = 0) -> None:
    """base(RGB) 위에 캐릭터를 합성한다. bottom은 화면 아래에서 띄울 픽셀."""
    img = panel(cid, which, target_h)
    if img is None:
        return
    bw, bh = base.size
    x = bw - img.width - 40 if anchor == "right" else 40
    if anchor == "center":
        x = (bw - img.width) // 2
    y = bh - bottom - img.height
    base.paste(img, (x, y), img)


def paste_top(base: Image.Image, cid: str, which: int, target_h: int,
              anchor: str = "right", top: int = 0) -> None:
    """base(RGB) 위에 캐릭터를 합성한다. top은 화면 위에서 머리까지의 픽셀."""
    img = panel(cid, which, target_h)
    if img is None:
        return
    bw = base.size[0]
    if anchor == "center":
        x = (bw - img.width) // 2
    elif anchor == "left":
        x = 70
    else:
        x = bw - img.width - 70
    base.paste(img, (x, top), img)
