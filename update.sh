#!/usr/bin/env bash
# Update the Aeneas Align API from GitHub and reinstall:   aeneas-update
# (installed as /usr/local/bin/aeneas-update by install.sh; same as:  sudo bash ~/aeneas-align-api/update.sh)
#
# Your settings (.env) are not in git and are never touched. The API token is in app/main.py (in git).
set -euo pipefail

APP_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
if [ "$(id -u)" -ne 0 ]; then exec sudo bash "$APP_DIR/update.sh" "$@"; fi
RUN_USER="${SUDO_USER:-$(stat -c %U "$APP_DIR")}"
FORCE=0; BRANCH=main
for a in "$@"; do case "$a" in --force) FORCE=1 ;; *) BRANCH="$a" ;; esac; done
g() { sudo -u "$RUN_USER" -H git -C "$APP_DIR" "$@"; }

if [ ! -d "$APP_DIR/.git" ]; then
  echo "This folder is not linked to GitHub. Install it with the one-line command in README.md."; exit 1
fi
OLD="$(g rev-parse --short HEAD 2>/dev/null || echo none)"
echo "==> Downloading the latest version from GitHub ($BRANCH)…"
g fetch --quiet origin "$BRANCH"
NEW="$(g rev-parse --short "origin/$BRANCH")"
if [ "$OLD" = "$NEW" ]; then
  echo "Already up to date ($NEW). Nothing to do."
  [ "$FORCE" = "1" ] || exit 0      # aeneas-update --force reinstalls anyway
fi
echo "==> Changes since your version:"
g log --oneline --no-decorate "$OLD..origin/$BRANCH" 2>/dev/null | head -30 || true
g reset --quiet --hard "origin/$BRANCH"     # tracked files only; .env and .venv stay
echo "==> Installing…"
SUDO_USER="$RUN_USER" bash "$APP_DIR/install.sh"
echo "==> Updated $OLD → $NEW."
