# SPDX-License-Identifier: GPL-3.0-only
"""Render a bounded native automation briefing image from model JSON."""
from __future__ import annotations

import hashlib
import json
import textwrap
from pathlib import Path
import sys

from PIL import Image, ImageDraw, ImageFont


def main() -> None:
    from soyo.platform import load_private_json
    config = load_private_json(Path(sys.argv[1]))
    payload = json.loads(sys.stdin.buffer.read(128 * 1024))
    if not isinstance(payload, dict):
        raise ValueError("briefing payload must be an object")
    title = str(payload.get("title") or "AI & Tech 简报")[:80]
    date = str(payload.get("date") or "")[:80]
    headline = str(payload.get("headline") or "")[:500]
    deep = payload.get("deep") or []
    quick = payload.get("quick") or []
    if not headline or not isinstance(deep, list) or not isinstance(quick, list) or len(deep) > 5 or len(quick) > 8:
        raise ValueError("briefing sections are invalid")
    root = Path(str(config.get("media_root") or ""))
    if not root.is_absolute():
        raise ValueError("media root required")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:32]
    out = root / ("briefing-" + digest + ".png")
    if out.exists():
        print(json.dumps({"ok": True, "path": str(out), "sha256": digest}, ensure_ascii=False)); return
    fonts = config.get("briefing_fonts", {})
    bold, regular = fonts.get("bold"), fonts.get("regular")
    if not all(value and Path(value).is_absolute() and Path(value).is_file() for value in (bold, regular)):
        raise ValueError("Configure explicit installed CJK briefing_fonts.bold/regular paths")
    fb, fr = ImageFont.truetype(bold, 46), ImageFont.truetype(regular, 24)
    fs, ft, ftb = ImageFont.truetype(bold, 30), ImageFont.truetype(bold, 25), ImageFont.truetype(regular, 21)
    image = Image.new("RGB", (1080, 1920), "#0b0e1a"); draw = ImageDraw.Draw(image)
    draw.text((40, 35), title, font=fb, fill="#ffffff"); draw.text((40, 92), date, font=fr, fill="#a8b3cf")
    y = 150
    def wrap(value, width=40): return textwrap.wrap(str(value), width=width, break_long_words=True, break_on_hyphens=False)
    draw.text((40, y), "头条焦点", font=fs, fill="#e85850"); y += 52
    draw.rounded_rectangle((40, y, 1040, y + 310), radius=16, fill="#171b36")
    draw.text((68, y + 25), headline[:70], font=ft, fill="#ff6b64")
    yy = y + 75
    for line in wrap(headline[70:], 46)[:8]: draw.text((68, yy), line, font=ftb, fill="#e8ecf4"); yy += 31
    y += 340
    for label, items, color in (("重要深度", deep, "#4a9be8"), ("快讯速览", quick, "#50c878")):
        draw.text((40, y), label, font=fs, fill=color); y += 48
        for item in items:
            if not isinstance(item, dict): continue
            heading = str(item.get("title") or "")[:80]; body = str(item.get("body") or "")[:500]
            height = 105 + min(5, len(wrap(body, 47))) * 27
            if y + height > 1810: break
            draw.rounded_rectangle((40, y, 1040, y + height), radius=12, fill="#131730")
            draw.rectangle((40, y, 47, y + height), fill=color)
            draw.text((66, y + 16), heading, font=ft, fill=color)
            yy = y + 53
            for line in wrap(body, 47)[:5]: draw.text((66, yy), line, font=ftb, fill="#e8ecf4"); yy += 27
            y += height + 16
    draw.line((40, 1845, 1040, 1845), fill="#2a3152")
    draw.text((540, 1870), "数据来源由 " + str(config.get("character_name") or "Agent") + " 自动化任务整理", font=fr, fill="#667799", anchor="ma")
    image.save(out, "PNG"); out.chmod(0o600)
    print(json.dumps({"ok": True, "path": str(out), "sha256": digest}, ensure_ascii=False))


if __name__ == "__main__":
    main()
