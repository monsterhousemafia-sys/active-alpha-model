#!/usr/bin/env python3
"""Generate Marktanalyse.exe icon with readable R3 label (Windows 11 accent)."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "marktanalyse_r3.ico"
OUT_PNG = ROOT / "assets" / "marktanalyse_r3.png"
SIZES = (256, 128, 64, 48, 32, 24, 16)
ACCENT = "#0067c0"
WHITE = "#ffffff"


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        Path(r"C:\Windows\Fonts\SegoeUI-Bold.ttf"),
        Path(r"C:\Windows\Fonts\segoeuib.ttf"),
        Path(r"C:\Windows\Fonts\arialbd.ttf"),
    )
    for path in candidates:
        if path.is_file():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def _render(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pad = max(1, size // 12)
    radius = max(3, size // 5)
    draw.rounded_rectangle(
        (pad, pad, size - pad - 1, size - pad - 1),
        radius=radius,
        fill=ACCENT,
    )
    if size <= 20:
        text = "R3"
        font = _load_font(max(7, int(size * 0.62)))
    else:
        text = "R3"
        font = _load_font(max(10, int(size * 0.46)))
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x = (size - tw) // 2 - bbox[0]
    y = (size - th) // 2 - bbox[1] - max(0, size // 48)
    draw.text((x, y), text, fill=WHITE, font=font)
    return img


def main() -> Path:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    master = _render(256)
    master.save(OUT_PNG, format="PNG")
    # Let Pillow derive all standard sizes — more reliable for Windows .exe embedding.
    master.save(
        OUT,
        format="ICO",
        sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)],
    )
    return OUT


if __name__ == "__main__":
    path = main()
    print(f"[OK] Icon erstellt: {path}")
