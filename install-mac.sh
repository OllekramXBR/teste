#!/usr/bin/env bash
# Instalação do HyperFrames no macOS
#
#   curl -fsSL https://raw.githubusercontent.com/OllekramXBR/teste/claude/hugging-face-hyperframes-mk71i0/install-mac.sh | bash
#
# ou, com o repositório já clonado:  bash install-mac.sh [nome-do-projeto]
#
# Requisitos que o script verifica/instala: Homebrew, Node.js 22+, FFmpeg.
# O Chromium usado na renderização é baixado automaticamente pelo Puppeteer
# na primeira execução — não precisa instalar nada de browser à mão.

set -euo pipefail

PROJETO="${1:-my-video}"

log()  { printf '\033[1;34m==>\033[0m %s\n' "$1"; }
erro() { printf '\033[1;31mErro:\033[0m %s\n' "$1" >&2; exit 1; }

[ "$(uname -s)" = "Darwin" ] || erro "Este script é para macOS. No Linux/Unraid use o Dockerfile deste repositório."

# ── Homebrew ──────────────────────────────────────────────────────────────────
if ! command -v brew >/dev/null 2>&1; then
  log "Homebrew não encontrado — instalando..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  # Apple Silicon instala em /opt/homebrew; Intel em /usr/local
  if [ -x /opt/homebrew/bin/brew ]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
  elif [ -x /usr/local/bin/brew ]; then
    eval "$(/usr/local/bin/brew shellenv)"
  fi
else
  log "Homebrew encontrado: $(brew --version | head -1)"
fi

# ── Node.js 22+ ───────────────────────────────────────────────────────────────
node_ok=false
if command -v node >/dev/null 2>&1; then
  major="$(node --version | sed 's/^v//' | cut -d. -f1)"
  if [ "$major" -ge 22 ] 2>/dev/null; then
    log "Node.js $(node --version) OK (requisito: >= 22)"
    node_ok=true
  else
    log "Node.js $(node --version) é antigo — o HyperFrames exige >= 22. Atualizando..."
  fi
fi

if [ "$node_ok" = false ]; then
  brew install node@22
  # node@22 é keg-only: precisa entrar no PATH
  PREFIX="$(brew --prefix node@22)"
  export PATH="$PREFIX/bin:$PATH"
  SHELL_RC="$HOME/.zshrc"
  [ "${SHELL##*/}" = "bash" ] && SHELL_RC="$HOME/.bash_profile"
  if ! grep -q "node@22/bin" "$SHELL_RC" 2>/dev/null; then
    printf '\nexport PATH="%s/bin:$PATH"\n' "$PREFIX" >> "$SHELL_RC"
    log "PATH do node@22 adicionado a $SHELL_RC"
  fi
  log "Node.js $(node --version) instalado"
fi

# ── FFmpeg ────────────────────────────────────────────────────────────────────
if command -v ffmpeg >/dev/null 2>&1; then
  log "FFmpeg encontrado: $(ffmpeg -version | head -1 | cut -d' ' -f1-3)"
else
  log "Instalando FFmpeg (necessário para codificar o MP4)..."
  brew install ffmpeg
fi

# ── Projeto HyperFrames ───────────────────────────────────────────────────────
if [ -d "$PROJETO" ]; then
  log "A pasta '$PROJETO' já existe — pulando o init."
else
  log "Criando o projeto '$PROJETO'..."
  npx --yes hyperframes init "$PROJETO" --non-interactive --example blank
fi

# ── Diagnóstico ───────────────────────────────────────────────────────────────
log "Rodando o diagnóstico do HyperFrames..."
(cd "$PROJETO" && npx --yes hyperframes doctor) || true

cat <<EOF

Pronto. Próximos passos:

  cd $PROJETO
  npx hyperframes preview    # abre o preview no navegador com live reload
  npx hyperframes render     # renderiza o MP4

Para usar com um agente de IA (Claude Code, Cursor, Codex), instale as skills:

  npx skills add heygen-com/hyperframes --full-depth

Depois é só pedir, por exemplo:
  "Usando /hyperframes, cria um vídeo de 10 segundos com um título em fade-in."

EOF
