"""Double-click to open the SnackScout Launcher (no console window)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from launcher.main import main  # noqa: E402

main()
