#!/bin/bash
# Run this ONCE on the Proxmox LXC to bootstrap everything.
# Assumes: Debian/Ubuntu, Python 3.11+, git already installed.
set -euo pipefail

REPO_URL="https://github.com/YOUR_USERNAME/YOUR_REPO.git"   # ← change this
INSTALL_DIR="/opt/applypilot"
SERVICE_USER="applypilot"

echo "=== Creating service user ==="
id -u "$SERVICE_USER" &>/dev/null || useradd -r -m -d "$INSTALL_DIR" -s /bin/bash "$SERVICE_USER"

echo "=== Cloning repo ==="
if [ ! -d "$INSTALL_DIR/.git" ]; then
    git clone "$REPO_URL" "$INSTALL_DIR"
else
    echo "Repo already cloned, skipping"
fi
chown -R "$SERVICE_USER":"$SERVICE_USER" "$INSTALL_DIR"

echo "=== Installing Python deps ==="
pip3 install -r "$INSTALL_DIR/discovery-service/requirements.txt"
pip3 install -e "$INSTALL_DIR/backend"

echo "=== Installing systemd service ==="
cp "$INSTALL_DIR/discovery-service/applypilot-discovery.service" /etc/systemd/system/
# Allow the service user to restart the service without a password
echo "$SERVICE_USER ALL=(ALL) NOPASSWD: /bin/systemctl restart applypilot-discovery" \
    >> /etc/sudoers.d/applypilot
systemctl daemon-reload
systemctl enable applypilot-discovery

echo ""
echo "=== NEXT STEPS ==="
echo "1. Copy your .env to $INSTALL_DIR/discovery-service/.env"
echo "   (DATABASE_URL, DATABASE_TOKEN, INTERVAL_HOURS, etc.)"
echo ""
echo "2. Install the GitHub Actions self-hosted runner:"
echo "   → Go to: https://github.com/YOUR_USERNAME/YOUR_REPO/settings/actions/runners/new"
echo "   → Select Linux / ARM64 (or x64 depending on your LXC)"
echo "   → Follow the 'Download' and 'Configure' steps shown on that page"
echo "   → When prompted for labels, add: self-hosted"
echo "   → Install as a service: sudo ./svc.sh install && sudo ./svc.sh start"
echo ""
echo "3. Start the discovery service:"
echo "   sudo systemctl start applypilot-discovery"
echo "   journalctl -u applypilot-discovery -f"
