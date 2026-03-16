#!/usr/bin/env bash
# Generates a self-signed TLS certificate for local development.
# Uses mkcert if available (trusted by the OS); falls back to openssl (browser will warn).
#
# Usage: bash scripts/gen-certs.sh [domain]
#   domain defaults to "rbac.local"
set -euo pipefail

DOMAIN="${1:-rbac.local}"
CERTS_DIR="$(cd "$(dirname "$0")/.." && pwd)/certs"

mkdir -p "$CERTS_DIR"

if command -v mkcert &>/dev/null; then
  echo "Using mkcert to generate trusted local certificates..."
  mkcert -install
  mkcert \
    -cert-file "$CERTS_DIR/cert.pem" \
    -key-file  "$CERTS_DIR/key.pem" \
    "$DOMAIN" "*.$DOMAIN"
else
  echo "mkcert not found — falling back to openssl (browser will show a warning)."
  echo "Install mkcert for trusted certs: https://github.com/FiloSottile/mkcert"
  openssl req -x509 -nodes -newkey rsa:4096 \
    -keyout "$CERTS_DIR/key.pem" \
    -out    "$CERTS_DIR/cert.pem" \
    -days   825 \
    -subj   "/CN=$DOMAIN" \
    -addext "subjectAltName=DNS:$DOMAIN,DNS:*.$DOMAIN"
fi

echo ""
echo "Certificates written to $CERTS_DIR"
echo "  cert.pem  — certificate"
echo "  key.pem   — private key"
echo ""
echo "Add these lines to /etc/hosts if not already present:"
echo "  127.0.0.1  $DOMAIN *.$DOMAIN"
