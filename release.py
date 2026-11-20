"""Bump SnackScout's version and add a changelog entry.

  .venv\\Scripts\\python release.py patch "Fixed the countdown on event pages"     -> 1.5 becomes 1.5.1
  .venv\\Scripts\\python release.py minor "Passkeys" "Faster team pages"         -> 1.5.1 becomes 1.6

Each extra argument becomes one bullet in CHANGELOG.md. Afterwards: commit, then `git tag v<version>`.
Restart SnackScout (launcher → Restart) to run the new version.
"""
import sys
from datetime import date

from snackscout import version


def main(argv):
    if len(argv) < 2 or argv[1] not in ("patch", "minor", "major"):
        print(__doc__)
        return 1
    kind, notes = argv[1], argv[2:] or ["Small fixes and improvements."]
    old = version.read()
    new = version.bump(old, kind)
    version.VERSION_FILE.write_text(new + "\n", encoding="utf-8")

    text = version.CHANGELOG.read_text(encoding="utf-8")
    entry = f"## {version.display(new)} ({date.today().isoformat()})\n" + "".join(f"- {n}\n" for n in notes) + "\n"
    i = text.find("\n## ")
    text = text[: i + 1] + entry + text[i + 1:] if i >= 0 else text + "\n" + entry
    version.CHANGELOG.write_text(text, encoding="utf-8")

    print(f"SnackScout {version.display(old)} -> {version.display(new)}")
    print(f"Next: git commit -am \"Release {version.display(new)}\" && git tag v{version.display(new)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
