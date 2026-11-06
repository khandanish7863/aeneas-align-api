#!/usr/bin/env bash
# Aeneas Align API — one-command installer for an Ubuntu 20.04 / 22.04 / 24.04 VM.
#
#   git clone <this repo> ~/aeneas-align-api
#   cd ~/aeneas-align-api
#   sudo bash install.sh
#
# Safe to run again: it updates everything in place and restarts the service.
# Your settings (.env) are kept. The API token is in app/main.py (from GitHub).
set -euo pipefail

APP_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
RUN_USER="${SUDO_USER:-$(stat -c %U "$APP_DIR")}"
RUN_HOME="$(getent passwd "$RUN_USER" | cut -d: -f6)"
SERVICE=aeneas-align-api
ENV_FILE="$APP_DIR/.env"

say() { printf '\n\033[1;33m==> %s\033[0m\n' "$*"; }
as_user() { sudo -u "$RUN_USER" -H env "PATH=$RUN_HOME/.local/bin:$PATH" bash -lc "$*"; }

if [ "$(id -u)" -ne 0 ]; then
  echo "Please run with sudo:  sudo bash install.sh"; exit 1
fi
if [ "$RUN_USER" = "root" ]; then
  echo "Run this as your normal user with sudo (not as root):  sudo bash install.sh"; exit 1
fi

say "1/7 System packages (ffmpeg, espeak for Aeneas, build tools)"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y ffmpeg espeak espeak-data libespeak-dev build-essential python3-dev curl ca-certificates git
apt-get install -y espeak-ng libespeak-ng-dev >/dev/null 2>&1 || true

say "2/7 Python 3.11 environment with Aeneas (via uv)"
if ! as_user "command -v uv" >/dev/null 2>&1; then
  as_user "curl -LsSf https://astral.sh/uv/install.sh | sh"
fi
as_user "cd '$APP_DIR' && uv venv -q --allow-existing -p 3.11 .venv"
as_user "cd '$APP_DIR' && uv pip install -q --python .venv/bin/python -r requirements.txt 'setuptools<60' wheel"
as_user "cd '$APP_DIR' && uv pip install -q --python .venv/bin/python --no-build-isolation aeneas==1.7.3.0"
as_user "cd '$APP_DIR' && PYTHONIOENCODING=UTF-8 .venv/bin/python -m aeneas.diagnostics" | tail -4
as_user "cd '$APP_DIR' && .venv/bin/python -c 'import aeneas.cdtw, aeneas.cmfcc, aeneas.cew'" \
  || { echo "Aeneas fast C extensions are missing — the install did not work. See the messages above."; exit 1; }

say "3/7 Settings file (.env)"
# The API token is NOT in .env: it is hard-coded in app/main.py and comes from GitHub with every update.
if [ ! -f "$ENV_FILE" ]; then
  cat > "$ENV_FILE" <<EOF
# The API token is set in app/main.py (comes from GitHub), not here.
# Port the API listens on (open it in the cloud firewall too)
PORT=${PORT:-3100}
# Number of requests processed at the same time (default: number of CPUs, at least 2)
# WORKERS=2
# Largest audio file accepted, in MB
MAX_AUDIO_MB=1024
# Stop an alignment that runs longer than this many seconds
ALIGN_TIMEOUT=1800
# Stop a download that runs longer than this many seconds
DOWNLOAD_TIMEOUT=300
EOF
  echo "Created $ENV_FILE"
else
  echo "Keeping existing $ENV_FILE"
  # Older installs kept a token here; it is no longer used, so remove that line (other settings stay).
  if grep -q '^API_TOKEN=' "$ENV_FILE"; then
    sed -i '/^# Secret token(s) for POST \/align/d; /^API_TOKEN=/d' "$ENV_FILE"
    sed -i '1i # The API token is set in app/main.py (comes from GitHub), not here.' "$ENV_FILE"
    echo "Removed the old token line from .env (the token now comes from GitHub)."
  fi
fi
chown "$RUN_USER" "$ENV_FILE"
chmod 600 "$ENV_FILE"
PORT="$(grep -oP '^PORT=\K[0-9]+' "$ENV_FILE" || echo 3100)"
TOKEN="$(grep -oP '^API_TOKEN = "\K[^"]+' "$APP_DIR/app/main.py" || true)"

say "4/7 Retire the old hand-made service (if there is one)"
if [ -f /etc/systemd/system/aeneas-api.service ]; then
  systemctl stop aeneas-api.service 2>/dev/null || true
  systemctl disable aeneas-api.service >/dev/null 2>&1 || true
  mv /etc/systemd/system/aeneas-api.service /etc/systemd/system/aeneas-api.service.old
  echo "Stopped the old 'aeneas-api' service (its file is kept as aeneas-api.service.old)."
else
  echo "None found."
fi

say "5/7 Background service (systemd, starts on every boot)"
CPUS="$(nproc)"; [ "$CPUS" -lt 2 ] && CPUS=2
cat > /etc/systemd/system/$SERVICE.service <<EOF
[Unit]
Description=Aeneas Align API (word timestamps)
After=network-online.target
Wants=network-online.target

[Service]
User=$RUN_USER
WorkingDirectory=$APP_DIR
Environment=PORT=3100
Environment=WORKERS=$CPUS
EnvironmentFile=$ENV_FILE
Environment=PYTHONIOENCODING=UTF-8
ExecStart=$APP_DIR/.venv/bin/gunicorn app.main:app --bind 0.0.0.0:\${PORT} --workers \${WORKERS} --timeout 2400 --access-logfile -
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable $SERVICE >/dev/null
systemctl restart $SERVICE

say "6/7 Firewall"
if command -v ufw >/dev/null && ufw status | grep -q "Status: active"; then
  ufw allow "$PORT/tcp" >/dev/null && echo "Opened port $PORT in ufw."
else
  echo "ufw is not active — nothing to do on the VM."
fi
echo "Remember: port $PORT must also be allowed in your cloud firewall (GCP: VPC network > Firewall)."

say "7/7 Update command"
cat > /usr/local/bin/aeneas-update <<EOF
#!/usr/bin/env bash
exec sudo bash "$APP_DIR/update.sh" "\$@"
EOF
chmod 755 /usr/local/bin/aeneas-update
echo "Installed: aeneas-update"

for _ in $(seq 1 20); do
  curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 && break
  sleep 1
done
if curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
  IP="$(curl -fsS -4 --max-time 5 https://ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')"
  say "Done! The API is running."
  echo "  Health : http://$IP:$PORT/health"
  echo "  Align  : http://$IP:$PORT/align"
  echo "  Token  : $TOKEN"
  echo "  (the token is set in $APP_DIR/app/main.py and comes from GitHub)"
  echo "Logs:  sudo journalctl -u $SERVICE -f"
else
  echo "The service did not start. Check:  sudo journalctl -u $SERVICE -n 80"
  exit 1
fi
