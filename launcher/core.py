"""The launcher's engine: starts/stops SnackScout and the Cloudflare tunnel, updates the permanent link,
makes a QR code, keeps the laptop awake, and edits the team password. No UI code here."""
import ctypes
import io
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import base64
import urllib.request
import webbrowser
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".env"
SETTINGS = ROOT / "launcher_settings.json"
PY = ROOT / ".venv" / "Scripts" / "python.exe"
PORT = 5000
LOCAL_URL = f"http://localhost:{PORT}"
NO_WINDOW = 0x08000000 if os.name == "nt" else 0
TUNNEL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")

DEFAULTS = {"keep_awake": True, "permanent_link": True, "auto_online": False}
# Permanent link: a tiny GitHub Pages site that forwards to the current tunnel link (link.json on the "link" branch).
PERMANENT_REPO = "kieran-snack/kieran-snack.github.io"
PERMANENT_URL = "https://kieran-snack.github.io/scout"


def find_cloudflared():
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"),
                 os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet", "Links")):
        if base:
            p = Path(base) / "cloudflared" / "cloudflared.exe"
            if p.exists():
                return str(p)
            p = Path(base) / "cloudflared.exe"
            if p.exists():
                return str(p)
    return None


def find_gh():
    import shutil
    for c in (shutil.which("gh"), os.path.join(os.environ.get("ProgramFiles", ""), "GitHub CLI", "gh.exe")):
        if c and Path(c).exists():
            return c
    return None


def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))  # no packet is sent; just picks the Wi-Fi interface
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return None


def port_in_use(port=PORT):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def http_ok(url, timeout=2):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status < 500, r.read(4000).decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        return e.code < 500, ""
    except Exception:  # noqa: BLE001
        return False, ""


class Proc:
    """A child process with its output kept in memory."""

    def __init__(self, name, args, on_line=None):
        self.name, self.args, self.on_line = name, args, on_line
        self.p = None
        self.lines = deque(maxlen=300)

    def start(self):
        self.p = subprocess.Popen(self.args, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  stdin=subprocess.DEVNULL, creationflags=NO_WINDOW, text=True,
                                  encoding="utf-8", errors="replace", bufsize=1)
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in self.p.stdout:
            line = line.rstrip()
            self.lines.append(line)
            if self.on_line:
                self.on_line(line)

    def alive(self):
        return self.p is not None and self.p.poll() is None

    def stop(self):
        if self.alive():
            self.p.terminate()
            try:
                self.p.wait(4)
            except subprocess.TimeoutExpired:
                self.p.kill()
        self.p = None


class Launcher:
    def __init__(self):
        self.settings = {**DEFAULTS, **self._load_settings()}
        self.server = None
        self.tunnel = None
        self.external_server = False
        self.server_state = "stopped"     # stopped | starting | running | error
        self.tunnel_state = "off"         # off | connecting | online | error
        self.url = self.short_url = None
        self.qr_svg = None
        self.error = None
        self.online_since = None
        self.perm_state = "off"           # off | updating | live | error
        self.perm_error = None
        self.perm_published = None        # last url we published (None = offline)
        self.public = {}                  # /api/public/status from the running app
        self.lock = threading.Lock()
        threading.Thread(target=self._awake_loop, daemon=True).start()
        threading.Thread(target=self._watch_loop, daemon=True).start()
        if port_in_use():  # SnackScout already started some other way (e.g. SnackScout.bat)
            self.external_server, self.server_state = True, "running"

    # ------------------------------------------------------------ settings / .env
    def _load_settings(self):
        try:
            return json.loads(SETTINGS.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def set_setting(self, key, value):
        if key in DEFAULTS:
            self.settings[key] = bool(value)
            SETTINGS.write_text(json.dumps(self.settings, indent=2), encoding="utf-8")
        return self.settings

    def env_get(self, key):
        if not ENV.exists():
            return ""
        for line in ENV.read_text(encoding="utf-8").splitlines():
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip()
        return ""

    def env_set(self, key, value):
        lines = ENV.read_text(encoding="utf-8").splitlines() if ENV.exists() else []
        out, done = [], False
        for line in lines:
            if line.startswith(key + "="):
                out.append(f"{key}={value}")
                done = True
            else:
                out.append(line)
        if not done:
            out.append(f"{key}={value}")
        ENV.write_text("\n".join(out) + "\n", encoding="utf-8")

    def team_code(self):
        try:
            from snackscout import db
            return db.team_config("team_code") or self.env_get("TEAM_PASSWORD")
        except Exception:  # noqa: BLE001
            return self.env_get("TEAM_PASSWORD")

    def set_password(self, pw):
        """Change the team code (what teammates type once to create an account)."""
        pw = (pw or "").strip()
        if len(pw) < 6 or any(c.isspace() for c in pw):
            return {"ok": False, "error": "Use at least 6 characters, no spaces."}
        self.env_set("TEAM_PASSWORD", pw)
        try:
            from snackscout import db
            db.init()
            db.set_team_config("team_code", pw)  # shared with every laptop through the team cloud
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"Couldn't save: {e}"}
        return {"ok": True}

    # ------------------------------------------------------------ server
    def start_server(self):
        with self.lock:
            if self.server_state in ("running", "starting"):
                return
            if port_in_use():
                self.external_server, self.server_state, self.error = True, "running", None
                return
            if not PY.exists():
                self.server_state, self.error = "error", "Python setup missing: run SnackScout.bat once first."
                return
            self.error = None
            self.server_state = "starting"
            self.server = Proc("server", [str(PY), "app.py"])
            self.server.start()
        threading.Thread(target=self._wait_server, daemon=True).start()

    def password_protected(self):
        """Would a visitor coming through the tunnel be asked for the password?"""
        req = urllib.request.Request(LOCAL_URL + "/api/clip-status", headers={"Cf-Connecting-Ip": "203.0.113.9"})
        try:
            with urllib.request.urlopen(req, timeout=5):
                return False
        except urllib.error.HTTPError as e:
            return e.code == 401
        except Exception:  # noqa: BLE001
            return False

    def _wait_server(self):
        for _ in range(90):
            if not (self.server and self.server.alive()):
                self.server_state = "error"
                tail = " ".join(list(self.server.lines)[-3:]) if self.server else ""
                self.error = "SnackScout stopped while starting. " + tail[-300:]
                return
            if http_ok(LOCAL_URL + "/login")[0]:
                self.server_state = "running"
                return
            time.sleep(1)
        self.server_state, self.error = "error", "SnackScout didn't start within 90 seconds."

    # ------------------------------------------------------------ tunnel
    def go_online(self):
        if self.tunnel_state in ("connecting", "online"):
            return
        if not self.team_code():
            self.error = "Set a team code first, so only teammates can create accounts."
            return
        cf = find_cloudflared()
        if not cf:
            self.tunnel_state = "error"
            self.error = "Cloudflare tunnel isn't installed. Run: winget install --id Cloudflare.cloudflared"
            return
        self.start_server()
        if self.external_server and not self.password_protected():
            self.error = ("SnackScout is already running in another window without the team password. "
                          "Close that window, then click Go online again.")
            return
        self.error = None
        self.url = self.short_url = self.qr_svg = None
        self.tunnel_state = "connecting"
        self.tunnel = Proc("tunnel", [cf, "tunnel", "--no-autoupdate", "--url", LOCAL_URL], self._tunnel_line)
        self.tunnel.start()

    def _tunnel_line(self, line):
        m = TUNNEL_RE.search(line)
        if m and not self.url:
            self.url = m.group(0)
            self.qr_svg = make_qr(self.url)
            if self.settings["permanent_link"]:
                threading.Thread(target=self.publish, args=(self.url,), daemon=True).start()
        if "Registered tunnel connection" in line and self.tunnel_state != "online":
            self.tunnel_state = "online"
            self.online_since = time.time()
        if "failed to request quick Tunnel" in line or "ERR" in line and "Unauthorized" in line:
            self.tunnel_state, self.error = "error", "Cloudflare couldn't create a link. Check the internet and try again."

    def publish(self, url):
        """Point the permanent link at `url` (or mark it offline when url is None)."""
        if url == self.perm_published:
            return
        gh = find_gh()
        if not gh:
            self.perm_state = "error"
            self.perm_error = "GitHub CLI (gh) isn't installed or logged in, so the permanent link can't update."
            return
        if url:
            self.perm_state = "updating"
        body = json.dumps({"online": bool(url), "url": url, "updated": int(time.time())})
        api = f"repos/{PERMANENT_REPO}/contents/link.json"
        try:
            sha = subprocess.run([gh, "api", f"{api}?ref=link", "--jq", ".sha"], capture_output=True, text=True,
                                 timeout=20, creationflags=NO_WINDOW).stdout.strip()
            r = subprocess.run([gh, "api", "-X", "PUT", api, "-f", "message=" + ("online" if url else "offline"),
                                "-f", "content=" + base64.b64encode(body.encode()).decode(), "-f", "branch=link",
                                *(["-f", f"sha={sha}"] if sha else [])],
                               capture_output=True, text=True, timeout=30, creationflags=NO_WINDOW)
            if r.returncode != 0:
                raise RuntimeError((r.stderr or r.stdout).strip()[:200])
            self.perm_published = url
            if url and url == self.url:
                self.perm_state, self.perm_error = "live", None
                self.short_url = PERMANENT_URL
                self.qr_svg = make_qr(PERMANENT_URL)
            elif not url:
                self.perm_state = "off"
        except Exception as e:  # noqa: BLE001 - the long link still works
            self.perm_state, self.perm_error = "error", f"Couldn't update the permanent link: {e}"

    def go_offline(self):
        was_published = self.perm_published
        if self.tunnel:
            self.tunnel.stop()
        self.tunnel = None
        self.tunnel_state = "off"
        self.url = self.short_url = self.qr_svg = None
        self.online_since = None
        if was_published:
            self.publish(None)  # visitors now see "SnackScout is offline" instead of an error

    def stop_all(self):
        self.go_offline()
        if self.server:
            self.server.stop()
        self.server = None
        if not self.external_server:
            self.server_state = "stopped"

    # ------------------------------------------------------------ background
    def _watch_loop(self):
        while True:
            time.sleep(2)
            if self.tunnel_state in ("connecting", "online") and not (self.tunnel and self.tunnel.alive()):
                self.tunnel_state, self.error = "error", "The tunnel stopped. Click Go online to restart it."
            if self.server_state == "running" and self.server and not self.server.alive():
                self.server_state, self.error = "error", "SnackScout stopped unexpectedly. Click Start to restart it."
            if self.server_state == "running":
                try:
                    with urllib.request.urlopen(LOCAL_URL + "/api/public/status", timeout=3) as r:
                        self.public = json.loads(r.read())
                except Exception:  # noqa: BLE001
                    pass
            if self.external_server and self.server_state == "running" and not port_in_use():
                self.external_server, self.server_state = False, "stopped"  # the other window was closed

    def _awake_loop(self):
        ES_SYSTEM_REQUIRED = 0x00000001
        while True:
            if os.name == "nt" and self.settings["keep_awake"] and self.tunnel_state == "online":
                ctypes.windll.kernel32.SetThreadExecutionState(ES_SYSTEM_REQUIRED)  # resets the sleep timer
            time.sleep(30)

    # ------------------------------------------------------------ for the UI
    def state(self):
        ip = lan_ip()
        pw = self.team_code()
        share = self.short_url or self.url
        logs = []
        for p in (self.server, self.tunnel):
            if p:
                logs += [f"[{p.name}] {l}" for l in list(p.lines)[-40:]]
        return dict(
            server=self.server_state, tunnel=self.tunnel_state, external=self.external_server,
            url=self.url, short_url=self.short_url, qr=self.qr_svg, local_url=LOCAL_URL,
            lan_url=f"http://{ip}:{PORT}" if ip else None, password=pw, has_password=bool(pw),
            error=self.error, settings=self.settings, cloudflared=bool(find_cloudflared()),
            online_for=int(time.time() - self.online_since) if self.online_since else None,
            share_text=(f"🍿 SnackScout is live: {share}\nNew? Create your account with team code: {pw}" if share else None),
            public=self.public,
            logs=logs[-80:],
            permanent_url=PERMANENT_URL, permanent_state=self.perm_state,
            permanent_error=self.perm_error if self.perm_state == "error" else None, gh=bool(find_gh()),
        )


def make_qr(text):
    import qrcode
    import qrcode.image.svg
    img = qrcode.make(text, image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=2)
    buf = io.BytesIO()
    img.save(buf)
    return buf.getvalue().decode()


def copy_to_clipboard(text):
    subprocess.run(["clip"], input=text.encode("utf-16-le"), creationflags=NO_WINDOW, check=False)


def open_url(url):
    webbrowser.open(url)


def open_folder(path):
    os.startfile(str(ROOT / path) if path else str(ROOT))  # noqa: S606 - our own folders
