"""Color palettes and per-person display settings, turned into CSS variables."""
import re

PALETTES = {
    # key: (label, main color, light color, emoji)
    "snack":   ("Snack Time", "#ec6f1e", "#ffae45", "🍿"),
    "honey":   ("Honey", "#d48a00", "#ffc935", "🍯"),
    "berry":   ("Berry", "#d6336c", "#ff7aa8", "🍓"),
    "grape":   ("Grape", "#7c4dff", "#b39bff", "🍇"),
    "ocean":   ("Ocean", "#1f7ae0", "#5fb3ff", "🌊"),
    "mint":    ("Mint", "#0f9d74", "#4fd6a5", "🌿"),
    "lime":    ("Lime", "#5f9e0d", "#a6d83a", "🍋"),
    "slate":   ("Slate", "#4f5d75", "#8d99ae", "🪨"),
}

DEFAULTS = {"palette": "snack", "accent": "", "theme": "system", "radius": "round", "density": "comfy",
            "motion": "full", "font": "normal", "autorefresh": 90, "extra_cols": False}

CHOICES = {"theme": {"system", "light", "dark"}, "radius": {"sharp", "normal", "round"},
           "density": {"comfy", "compact"}, "motion": {"full", "reduced", "off"}, "font": {"small", "normal", "large"}}


def clean(p: dict) -> dict:
    out = dict(DEFAULTS)
    if p.get("palette") in PALETTES:
        out["palette"] = p["palette"]
    if isinstance(p.get("accent"), str) and re.fullmatch(r"#[0-9a-fA-F]{6}", p["accent"]):
        out["accent"] = p["accent"].lower()
    for k, allowed in CHOICES.items():
        if p.get(k) in allowed:
            out[k] = p[k]
    try:
        out["autorefresh"] = int(p.get("autorefresh", 90)) if int(p.get("autorefresh", 90)) in (0, 45, 90, 180) else 90
    except (TypeError, ValueError):
        pass
    out["extra_cols"] = bool(p.get("extra_cols"))
    return out


def _lighten(hex_color, amt=0.35):
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    r, g, b = (round(c + (255 - c) * amt) for c in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


def css(prefs: dict) -> str:
    """CSS custom properties for this person's palette and sizes."""
    p = clean(prefs or {})
    _, brand, brand2, _ = PALETTES[p["palette"]]
    if p["accent"]:
        brand, brand2 = p["accent"], _lighten(p["accent"])
    radius = {"sharp": (6, 4), "normal": (11, 8), "round": (16, 11)}[p["radius"]]
    font = {"small": 14, "normal": 15, "large": 17}[p["font"]]
    return (f":root{{--brand:{brand};--brand2:{brand2};--r:{radius[0]}px;--r-sm:{radius[1]}px;"
            f"--fs:{font}px;}}")
