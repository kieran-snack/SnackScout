"""SnackScout's version number (one source of truth: the VERSION file at the project root).

Small updates: 1.5 -> 1.5.1 -> 1.5.2.  Bigger releases: 1.5 -> 1.6.  (Stored as MAJOR.MINOR.PATCH, e.g. 1.5.0.)
"""
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = Path(os.getenv("SNACKSCOUT_VERSION_FILE") or ROOT / "VERSION")  # override only for tests
CHANGELOG = ROOT / "CHANGELOG.md"


def read() -> str:
    """The version currently installed on disk (re-read every time, so updates are noticed)."""
    try:
        v = VERSION_FILE.read_text(encoding="utf-8").strip()
        return v if re.fullmatch(r"\d+\.\d+\.\d+", v) else "0.0.0"
    except OSError:
        return "0.0.0"


def display(v: str) -> str:
    """1.5.0 -> 1.5,  1.5.2 -> 1.5.2"""
    parts = (v or "0.0.0").split(".")
    return ".".join(parts[:2]) if len(parts) == 3 and parts[2] == "0" else v


def parse(v: str):
    try:
        return tuple(int(x) for x in v.split("."))
    except ValueError:
        return (0, 0, 0)


def bump(v: str, kind: str) -> str:
    major, minor, patch = parse(v)
    if kind == "patch":
        return f"{major}.{minor}.{patch + 1}"
    if kind == "minor":
        return f"{major}.{minor + 1}.0"
    if kind == "major":
        return f"{major + 1}.0.0"
    raise ValueError("kind must be patch, minor or major")


def changelog():
    """[{version, date, items}] from CHANGELOG.md, newest first."""
    out, cur = [], None
    try:
        lines = CHANGELOG.read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    for line in lines:
        m = re.match(r"^## (\d+(?:\.\d+){1,2})(?: \((.+?)\))?", line)
        if m:
            cur = {"version": m.group(1), "date": m.group(2) or "", "items": []}
            out.append(cur)
        elif cur and line.startswith("- "):
            cur["items"].append(line[2:].strip())
    return out


# The version this process started with (the running app keeps it; the launcher compares it to the file).
RUNNING = read()
