"""SnackScout Launcher window (pywebview + Edge WebView2)."""
import threading
from pathlib import Path

import webview

from . import core

HERE = Path(__file__).resolve().parent


class Api:
    """Everything the launcher page can call through window.pywebview.api."""

    def __init__(self, launcher: core.Launcher):
        self._l = launcher

    def state(self):
        return self._l.state()

    def start_local(self):
        self._l.start_server()
        return True

    def go_online(self):
        self._l.go_online()
        return True

    def go_offline(self):
        self._l.go_offline()
        return True

    def stop_all(self):
        self._l.stop_all()
        return True

    def restart(self):
        threading.Thread(target=self._l.restart_server, daemon=True).start()
        return True

    def set_setting(self, key, value):
        return self._l.set_setting(key, value)

    def set_password(self, pw):
        return self._l.set_password(pw)

    def copy(self, text):
        core.copy_to_clipboard(text or "")
        return True

    def open(self, url):
        if url and url.startswith(("http://", "https://")):
            core.open_url(url)
        return True

    def open_folder(self, name):
        if name in ("", "clips"):
            core.open_folder(name)
        return True


def main():
    try:  # show SnackScout's own icon in the taskbar instead of Python's
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("SnackTime.SnackScout.Launcher")
    except Exception:  # noqa: BLE001
        pass
    launcher = core.Launcher()
    api = Api(launcher)
    window = webview.create_window(
        "SnackScout", url=str(HERE / "index.html"), js_api=api,
        width=480, height=860, min_size=(420, 640), background_color="#17120d")

    def on_closing():
        threading.Thread(target=launcher.stop_all, daemon=True).start()

    window.events.closing += on_closing
    if launcher.settings.get("auto_online"):
        threading.Thread(target=launcher.go_online, daemon=True).start()
    webview.start(private_mode=False, storage_path=str(core.ROOT / ".launcher_webview"), icon=str(HERE / "icon.ico"))
    launcher.stop_all()


if __name__ == "__main__":
    main()
