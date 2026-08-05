#!/usr/bin/env bash
# Renderiza um lote de vídeos de campanha do OmniPrompt.
#
#   ./renderizar-lote.sh                          # usa lote-teste.json
#   ./renderizar-lote.sh lote-primeira-onda.json  # a onda inteira
#
# Feito para a Nix chamar num cron. Sai com código != 0 se qualquer gate
# falhar, para o alerta do Telegram pegar — nada renderiza a partir de uma
# composição quebrada.

set -euo pipefail

cd "$(dirname "$0")"

LOTE="${1:-lote-teste.json}"
# Sem valor padrão dentro de ${...}: o bash fecharia a expansão na primeira
# chave do template e o placeholder viraria "{slug.mp4}".
SAIDA="${SAIDA:-}"
[ -n "$SAIDA" ] || SAIDA='renders/{slug}.mp4'

log() { printf '\033[1;34m[lote]\033[0m %s\n' "$1"; }
erro() { printf '\033[1;31m[lote] erro:\033[0m %s\n' "$1" >&2; exit 1; }

[ -f "$LOTE" ] || erro "arquivo de lote não encontrado: $LOTE"

# Portão de qualidade: lint, runtime, layout, motion e contraste.
# Roda ANTES do lote — 48 vídeos errados custam uma hora de máquina.
log "verificando a composição..."
npx hyperframes check || erro "check falhou — lote abortado, nada foi renderizado"

TOTAL=$(python3 -c "import json,sys; print(len(json.load(open('$LOTE'))))")
log "renderizando $TOTAL vídeo(s) a partir de $LOTE"

npx hyperframes render \
  --batch "$LOTE" \
  --output "$SAIDA" \
  --strict-variables \
  --batch-fail-fast \
  || erro "render em lote falhou"

log "concluído. manifesto: renders/manifest.json"
