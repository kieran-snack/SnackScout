"""Reads the official FIRST BIOBUZZ scoreboard overlay from match video with OpenCV.

The overlay at the bottom of every FTC livestream has a fixed layout, so each field is cropped at a
known position (scaled to the video size), turned into black/white, split into digits with connected
components, and each digit is matched against templates in data/digits.npz (nearest neighbour).
"""
from pathlib import Path

import cv2
import numpy as np

REF_W, REF_H = 854, 480
# (x0, y0, x1, y1) in 854x480 reference coordinates, text polarity
FIELDS = {
    "timer": ((385, 424, 472, 466), "dark"),
    "red": ((285, 432, 380, 476), "light"),
    "blue": ((478, 432, 572, 476), "light"),
    "red_hive": ((102, 433, 131, 453), "dark"),
    "blue_hive": ((712, 433, 741, 453), "dark"),
}
GLYPH = (16, 24)
_T = np.load(Path(__file__).parent / "data" / "digits.npz")
TEMPLATES = _T["glyphs"].astype(np.float32) / 255
LABELS = _T["labels"]
MAX_DIST = 0.22


def _binarize(crop, polarity):
    if polarity == "dark":
        g = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        _, b = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        return b
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    return (((hsv[..., 2] > 160) & (hsv[..., 1] < 90)) * 255).astype(np.uint8)


def _crop(img, rect):
    h, w = img.shape[:2]
    x0, y0, x1, y1 = rect
    return img[round(y0 / REF_H * h):round(y1 / REF_H * h), round(x0 / REF_W * w):round(x1 / REF_W * w)]


def read_digits(img, field):
    """Return the digit string in a field, or None if anything in it isn't a confident digit."""
    rect, pol = FIELDS[field]
    b = _binarize(_crop(img, rect), pol)
    if b.size == 0:
        return None
    n, lab, st, _ = cv2.connectedComponentsWithStats(b, 8)
    H, W = b.shape
    parts = []
    for i in range(1, n):
        x, y, ww, hh, a = st[i]
        if hh < 0.45 * H or a < 8:
            continue  # colon dots, specks
        if x == 0 or x + ww >= W or y == 0 or y + hh >= H:
            continue  # touches the crop edge = background/border, not a digit
        g = (lab[y:y + hh, x:x + ww] == i).astype(np.uint8) * 255
        g = cv2.resize(g, GLYPH, interpolation=cv2.INTER_AREA).astype(np.float32) / 255
        d = np.abs(TEMPLATES - g).mean(axis=(1, 2))
        k = int(d.argmin())
        if d[k] > MAX_DIST:
            return None
        parts.append((x, str(LABELS[k])))
    if not parts or len(parts) > 3:
        return None
    return "".join(s for _, s in sorted(parts))


def read_frame(img):
    out = {}
    for f in FIELDS:
        s = read_digits(img, f)
        out[f] = int(s) if s else None
    t = out.pop("timer")
    out["timer"] = (t // 100) * 60 + t % 100 if t is not None and t >= 100 and t % 100 < 60 else (
        t if t is not None and t < 60 else None)
    return out
