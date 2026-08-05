#!/bin/sh
set -e

# Sem projeto no volume ainda? Cria um esqueleto para o preview ter o que servir.
if [ ! -f /workspace/index.html ] && [ -z "$(ls -A /workspace 2>/dev/null)" ]; then
  echo "[hyperframes] /workspace vazio — criando projeto inicial..."
  HYPERFRAMES_SKIP_SKILLS=1 hyperframes init /workspace --example blank --non-interactive || true
fi

cd /workspace
echo "[hyperframes] iniciando preview em 0.0.0.0:${HYPERFRAMES_PORT:-3002}"
exec hyperframes preview --port "${HYPERFRAMES_PORT:-3002}"
