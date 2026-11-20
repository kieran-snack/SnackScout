#!/usr/bin/env bash
# One-time setup of SnackScout on an Oracle Cloud "Always Free" Ubuntu VM.
#
# On the VM, run:
#   curl -fsSL https://raw.githubusercontent.com/kieran-snack/SnackScout/main/deploy/setup-oracle.sh -o setup.sh
#   bash setup.sh
#
# It installs Python, ffmpeg and the Caddy web server (automatic https), downloads SnackScout,
# asks for your FTC Events key and a team password, and starts SnackScout as a service that
# restarts by itself and starts on boot.
set -euo pipefail

REPO="${REPO:-https://github.com/kieran-snack/SnackScout.git}"
APP_DIR="$HOME/SnackScout"
USER_NAME="$(whoami)"

echo "== 1/6 Installing system packages (a few minutes)"
sudo apt-get update -y
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y python3 python3-venv python3-pip ffmpeg git curl unzip \
  debian-keyring debian-archive-keyring apt-transport-https iptables-persistent
if ! command -v caddy >/dev/null; then
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
  sudo apt-get update -y
  sudo apt-get install -y caddy
fi
# yt-dlp uses a JavaScript runtime to keep YouTube downloads working.
if ! command -v deno >/dev/null && [ ! -x "$HOME/.deno/bin/deno" ]; then
  curl -fsSL https://deno.land/install.sh | sh -s -- -y || echo "(deno install failed - downloads may still work)"
fi

echo "== 2/6 Downloading SnackScout"
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" pull --ff-only
else
  git clone "$REPO" "$APP_DIR"
fi
cd "$APP_DIR"
python3 -m venv .venv
.venv/bin/pip install --upgrade pip -q
.venv/bin/pip install -r requirements.txt -q

echo "== 3/6 Settings"
if [ ! -f .env ]; then
  read -rp "FTC Events API username: " FTC_USER
  read -rp "FTC Events API token: " FTC_TOKEN
  while true; do
    read -rsp "Choose a team password for the website: " TEAM_PW; echo
    [ ${#TEAM_PW} -ge 6 ] && break
    echo "Use at least 6 characters."
  done
  cat > .env <<EOF
FTC_EVENTS_USERNAME=$FTC_USER
FTC_EVENTS_TOKEN=$FTC_TOKEN
FTC_SEASON=2026
OUR_TEAM_NUMBER=34672
TEAM_PASSWORD=$TEAM_PW
LOCAL_NO_PASSWORD=0
SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
HOST=127.0.0.1
PORT=5000
# YTDLP_COOKIES=/home/$USER_NAME/SnackScout/youtube-cookies.txt
EOF
  chmod 600 .env
else
  echo ".env already exists - keeping it."
fi

echo "== 4/6 Starting SnackScout as a service"
sudo tee /etc/systemd/system/snackscout.service >/dev/null <<EOF
[Unit]
Description=SnackScout
After=network-online.target
Wants=network-online.target

[Service]
User=$USER_NAME
WorkingDirectory=$APP_DIR
Environment=PATH=$HOME/.deno/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=$APP_DIR/.venv/bin/python app.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now snackscout
sudo systemctl restart snackscout

echo "== 5/6 Opening the firewall for web traffic (ports 80 and 443)"
# Oracle's Ubuntu images block everything except SSH in iptables, on top of the cloud "security list".
for p in 80 443; do
  sudo iptables -C INPUT -p tcp --dport $p -j ACCEPT 2>/dev/null || sudo iptables -I INPUT 1 -p tcp --dport $p -j ACCEPT
done
sudo netfilter-persistent save

echo "== 6/6 Setting up https"
if [ -z "${DOMAIN:-}" ]; then
  IP="$(curl -s https://api.ipify.org || true)"
  DOMAIN="${IP//./-}.sslip.io"   # free hostname that points at this IP, so https certificates work
fi
sudo tee /etc/caddy/Caddyfile >/dev/null <<EOF
$DOMAIN {
    encode gzip
    reverse_proxy 127.0.0.1:5000
}
EOF
sudo systemctl reload caddy || sudo systemctl restart caddy

echo
echo "Done! Open:  https://$DOMAIN"
echo "(If it doesn't load, check that ports 80 and 443 are allowed in the Oracle security list - see DEPLOY.md step 3.)"
echo "Logs:    sudo journalctl -u snackscout -f"
echo "Update:  bash ~/SnackScout/deploy/update.sh"
