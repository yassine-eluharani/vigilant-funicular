#!/usr/bin/env bash
# setup-ssl.sh — Obtain a Let's Encrypt certificate for ApplyPilot.
#
# Usage:
#   DOMAIN=yourdomain.com EMAIL=you@example.com ./setup-ssl.sh
#   DOMAIN=yourdomain.com EMAIL=you@example.com ./setup-ssl.sh --install-cron
#
# Flags:
#   --install-cron   Write /etc/cron.d/applypilot-certbot for automatic
#                    renewal. Idempotent: overwrites any existing entry.
#                    Requires root (uses sudo).
#
# Prerequisites:
#   - Docker + Docker Compose installed
#   - Ports 80 and 443 open on this machine
#   - DNS A record for $DOMAIN pointing to this machine's IP
#   - The production stack is running: docker compose -f docker-compose.yml \
#       -f docker-compose.prod.yml up -d

set -euo pipefail

DOMAIN="${DOMAIN:-}"
EMAIL="${EMAIL:-}"
INSTALL_CRON=0

for arg in "$@"; do
  case "$arg" in
    --install-cron) INSTALL_CRON=1 ;;
    -h|--help)
      sed -n '2,18p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      exit 2
      ;;
  esac
done

if [[ -z "$DOMAIN" ]]; then
  echo "Error: DOMAIN is required. Run: DOMAIN=yourdomain.com ./setup-ssl.sh"
  exit 1
fi

if [[ -z "$EMAIL" ]]; then
  echo "Error: EMAIL is required. Run: EMAIL=you@example.com DOMAIN=yourdomain.com ./setup-ssl.sh"
  exit 1
fi

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Requesting Let's Encrypt certificate for: $DOMAIN"
echo "Contact email: $EMAIL"
echo ""

# Ensure the certbot config + ACME challenge directories exist (INF-016).
# These are project-local bind-mounts referenced by docker-compose.prod.yml's
# nginx and certbot services. On a fresh host they may not exist yet, so we
# create them up front — `mkdir -p` is idempotent.
mkdir -p "$REPO_DIR/certbot/conf" "$REPO_DIR/certbot/www"

# Run Certbot in webroot mode using the certbot service
docker compose \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  --profile ssl \
  run --rm certbot certonly \
    --webroot \
    --webroot-path /var/www/certbot \
    --email "$EMAIL" \
    --agree-tos \
    --no-eff-email \
    -d "$DOMAIN"

echo ""
echo "Certificate obtained. Restarting nginx to enable HTTPS..."
# A full restart (not just reload) is required so the entrypoint script
# /docker-entrypoint.d/15-pick-https.sh re-detects the cert and enables the
# HTTPS server block. Subsequent renewals only need a `nginx -s reload`
# because the HTTPS config is already in place.
if ! docker compose -f docker-compose.yml -f docker-compose.prod.yml restart nginx; then
  echo "Error: nginx restart failed. Check 'docker compose ps' and logs." >&2
  exit 1
fi

echo ""
echo "SSL is active at https://$DOMAIN"
echo ""

# ── Cron installation ────────────────────────────────────────────────────────
RENEW_CMD="cd $REPO_DIR && DOMAIN=$DOMAIN docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile ssl run --rm certbot renew --quiet && docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T nginx nginx -s reload"

if [[ "$INSTALL_CRON" -eq 1 ]]; then
  CRON_FILE="/etc/cron.d/applypilot-certbot"
  echo "Installing renewal cron at $CRON_FILE ..."

  SUDO=""
  if [[ "$(id -u)" -ne 0 ]]; then
    SUDO="sudo"
  fi

  TMP_CRON="$(mktemp)"
  cat > "$TMP_CRON" <<EOF
# ApplyPilot certbot renewal — managed by setup-ssl.sh, edits will be overwritten.
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

0 3 * * * root $RENEW_CMD >> /var/log/applypilot-certbot.log 2>&1
EOF

  $SUDO install -o root -g root -m 0644 "$TMP_CRON" "$CRON_FILE"
  rm -f "$TMP_CRON"

  # cron.d on Debian-family hosts requires the daemon to re-read the
  # directory. Most distros do this automatically on file mtime change,
  # but a SIGHUP / reload is harmless if cron is running.
  if command -v systemctl >/dev/null 2>&1; then
    $SUDO systemctl reload cron 2>/dev/null || $SUDO systemctl reload crond 2>/dev/null || true
  fi

  echo "Renewal cron installed. Logs: /var/log/applypilot-certbot.log"
else
  echo "Certificate auto-renewal:"
  echo "  - Re-run with --install-cron to install /etc/cron.d/applypilot-certbot, OR"
  echo "  - Add this line to crontab manually (crontab -e):"
  echo "      0 3 * * * $RENEW_CMD"
fi
