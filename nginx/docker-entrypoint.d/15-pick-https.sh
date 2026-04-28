#!/bin/sh
# 15-pick-https.sh — runs before the official envsubst entrypoint (20-).
#
# If a Let's Encrypt cert exists for $DOMAIN, copy the bundled HTTPS template
# into /etc/nginx/templates/ so envsubst renders it into /etc/nginx/conf.d/.
# Otherwise leave it absent — nginx then runs HTTP-only (avoiding the
# first-boot redirect loop, INF-003, and avoiding nginx failing to start
# because the cert files are missing, INF-001).
#
# The HTTP server template detects the rendered HTTPS conf at
# /etc/nginx/conf.d/10-https.conf and 301-redirects everything (except ACME
# challenges) to HTTPS once it's present.

set -eu

DOMAIN="${DOMAIN:-}"
TEMPLATE_SRC="/etc/nginx/extra-templates/10-https.conf.template"
TEMPLATE_DST="/etc/nginx/templates/10-https.conf.template"

if [ -z "$DOMAIN" ]; then
    echo "[15-pick-https] DOMAIN env var not set — staying HTTP-only."
    rm -f "$TEMPLATE_DST"
    exit 0
fi

CERT_PATH="/etc/letsencrypt/live/${DOMAIN}/fullchain.pem"

if [ -f "$CERT_PATH" ]; then
    echo "[15-pick-https] cert found at $CERT_PATH — enabling HTTPS server."
    cp "$TEMPLATE_SRC" "$TEMPLATE_DST"
else
    echo "[15-pick-https] no cert at $CERT_PATH — HTTP-only mode."
    echo "[15-pick-https] run setup-ssl.sh to obtain a cert, then restart nginx."
    rm -f "$TEMPLATE_DST"
fi
