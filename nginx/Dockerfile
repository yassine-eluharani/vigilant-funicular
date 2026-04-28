FROM nginx:1.27-alpine

# The official nginx image runs every /etc/nginx/templates/*.template through
# envsubst at container start (see /docker-entrypoint.d/20-envsubst-on-templates.sh)
# and writes the result into /etc/nginx/conf.d/. The base /etc/nginx/nginx.conf
# already does `include /etc/nginx/conf.d/*.conf;` from inside its `http {}`
# block, so our templates are at http-scope.
#
# The HTTP-globals template is always rendered. The HTTPS template is staged
# in /etc/nginx/extra-templates/ and only copied into /etc/nginx/templates/ by
# our 15-pick-https.sh entrypoint script when a cert for $DOMAIN exists. This
# avoids INF-001 (nginx failing on missing cert) and INF-003 (first-boot
# redirect loop).

# Drop the stock default.conf — we provide our own HTTP server.
RUN rm -f /etc/nginx/conf.d/default.conf

# Always-rendered HTTP template (port 80, ACME, plaintext fallback)
COPY templates/00-http-globals.conf.template /etc/nginx/templates/00-http-globals.conf.template

# Conditionally-enabled HTTPS template — staged, picked up by entrypoint script
COPY templates/10-https.conf.template /etc/nginx/extra-templates/10-https.conf.template

# Entrypoint hook: detect cert, decide whether to enable HTTPS template
COPY docker-entrypoint.d/15-pick-https.sh /docker-entrypoint.d/15-pick-https.sh
RUN chmod +x /docker-entrypoint.d/15-pick-https.sh

# NGINX_ENVSUBST_OUTPUT_DIR defaults to /etc/nginx/conf.d — leave as-is.
# Restrict envsubst to known variables so we don't accidentally expand nginx's
# own $-variables (e.g. $host, $remote_addr) at template-render time.
ENV NGINX_ENVSUBST_TEMPLATE_SUFFIX=.template
ENV NGINX_ENVSUBST_FILTER='^DOMAIN$'

EXPOSE 80 443
