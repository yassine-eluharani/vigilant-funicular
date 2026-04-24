#!/usr/bin/env bash
# setup-ssl.sh — Obtain a Let's Encrypt certificate for ApplyPilot.
#
# Usage:
#   DOMAIN=yourdomain.com EMAIL=you@example.com ./setup-ssl.sh
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

if [[ -z "$DOMAIN" ]]; then
  echo "Error: DOMAIN is required. Run: DOMAIN=yourdomain.com ./setup-ssl.sh"
  exit 1
fi

if [[ -z "$EMAIL" ]]; then
  echo "Error: EMAIL is required. Run: EMAIL=you@example.com DOMAIN=yourdomain.com ./setup-ssl.sh"
  exit 1
fi

echo "Requesting Let's Encrypt certificate for: $DOMAIN"
echo "Contact email: $EMAIL"
echo ""

# Ensure the ACME challenge directory exists
mkdir -p /var/www/certbot

# Run Certbot in standalone mode using the certbot service
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
echo "Certificate obtained. Reloading nginx..."
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec nginx nginx -s reload

echo ""
echo "SSL is active at https://$DOMAIN"
echo ""
echo "Certificate auto-renewal: add this to crontab (crontab -e):"
echo "  0 3 * * * cd $(pwd) && DOMAIN=$DOMAIN docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile ssl run --rm certbot renew --quiet && docker compose -f docker-compose.yml -f docker-compose.prod.yml exec nginx nginx -s reload"
