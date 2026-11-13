#!/usr/bin/env bash
# Pull the newest SnackScout from GitHub and restart it. Notes, clips and settings are kept.
set -euo pipefail
cd "$HOME/SnackScout"
git pull --ff-only
.venv/bin/pip install -r requirements.txt -q
sudo systemctl restart snackscout
echo "Updated to $(git log --oneline -1)"
