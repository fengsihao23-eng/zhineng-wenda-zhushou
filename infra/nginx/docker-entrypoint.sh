#!/bin/sh
set -eu

# nginx.conf includes this file inside the public server block. Keeping it
# empty is a valid HTTP-only configuration; enabling TLS requires mounted
# certificates and fails fast when they are missing.
: > /etc/nginx/tls-listen.conf
if [ "${TLS_ENABLED:-false}" = "true" ]; then
  test -s /etc/nginx/certs/fullchain.pem || {
    echo "TLS_ENABLED=true but /etc/nginx/certs/fullchain.pem is missing" >&2
    exit 1
  }
  test -s /etc/nginx/certs/privkey.pem || {
    echo "TLS_ENABLED=true but /etc/nginx/certs/privkey.pem is missing" >&2
    exit 1
  }
  cat > /etc/nginx/tls-listen.conf <<'EOF'
listen 443 ssl;
ssl_certificate /etc/nginx/certs/fullchain.pem;
ssl_certificate_key /etc/nginx/certs/privkey.pem;
ssl_protocols TLSv1.2 TLSv1.3;
ssl_session_cache shared:SSL:10m;
ssl_session_timeout 10m;
if ($scheme = http) { return 301 https://$host$request_uri; }
EOF
fi

exec nginx -g 'daemon off;'
