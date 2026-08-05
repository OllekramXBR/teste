# HyperFrames — instalação no macOS e no Unraid

Pacote de instalação do [HyperFrames](https://github.com/heygen-com/hyperframes) — framework open-source (Apache 2.0) da HeyGen que transforma **HTML + CSS + animações em vídeo MP4 determinístico** (Chromium headless + FFmpeg).

Duas formas de rodar: nativamente **no Mac** (via CLI, o caminho normal de desenvolvimento) ou como **container Docker no Unraid** (para deixar um preview/render server na rede).

## Instalação no macOS

Requisitos: Node.js 22+ e FFmpeg. O Chromium usado na renderização é baixado automaticamente pelo Puppeteer na primeira execução.

Script automático (verifica/instala Homebrew, Node 22, FFmpeg, cria o projeto e roda o diagnóstico):

```bash
bash install-mac.sh meu-video
```

Ou manualmente:

```bash
brew install node ffmpeg
npx hyperframes init meu-video
cd meu-video
npx hyperframes preview    # preview no navegador com live reload
npx hyperframes render     # renderiza o MP4
```

Para usar com um agente de IA (Claude Code, Cursor, Codex), instale as 19 skills do projeto:

```bash
npx skills add heygen-com/hyperframes --full-depth
```

Depois basta pedir em linguagem natural, por exemplo: *"Usando `/hyperframes`, cria um vídeo de 10 segundos com um título em fade-in e música de fundo."*

## Instalação no Unraid

Não existe imagem oficial publicada em registry, então a imagem é construída localmente a partir do `Dockerfile` deste repositório (baseado no ambiente de renderização de produção do projeto: Node 22, Chromium do sistema, FFmpeg e o conjunto completo de fontes Noto).

### Opção A — Docker Compose (recomendado)

Requer o plugin **Docker Compose Manager** (Community Applications).

1. Clone este repositório em uma share do Unraid, por exemplo:
   ```bash
   git clone https://github.com/OllekramXBR/teste.git /mnt/user/appdata/hyperframes-build
   ```
2. No Docker Compose Manager, adicione uma stack apontando para
   `/mnt/user/appdata/hyperframes-build/docker-compose.yml` (ou rode no terminal):
   ```bash
   cd /mnt/user/appdata/hyperframes-build
   docker compose up -d --build
   ```
3. Acesse o preview em `http://IP-DO-UNRAID:3002`.

### Opção B — Template do dockerMan (interface nativa do Unraid)

1. Construa a imagem no terminal do Unraid:
   ```bash
   cd /mnt/user/appdata/hyperframes-build
   docker build -t hyperframes-studio:latest .
   ```
2. Copie o template para o pendrive de boot:
   ```bash
   cp unraid/hyperframes-template.xml /boot/config/plugins/dockerMan/templates-user/
   ```
3. Em **Docker → Add Container**, selecione o template **HyperFrames**, confira porta e caminho do workspace e aplique.

## Uso

- O volume `/workspace` (padrão `/mnt/user/appdata/hyperframes`) guarda os projetos. Na primeira subida, o container roda `hyperframes init` e cria um projeto de exemplo.
- **Preview:** abra `http://IP-DO-UNRAID:3002` no navegador — edição com live reload.
- **Renderizar um MP4:**
  ```bash
  docker exec -it hyperframes hyperframes render
  ```
  O vídeo sai dentro do próprio workspace, acessível pela share.
- **Outros comandos úteis:** `hyperframes lint`, `hyperframes check`, `hyperframes doctor`, `hyperframes add <bloco-do-catálogo>`.

## Notas

- `--shm-size=1g` é necessário: o Chromium headless trava renderizando 1080p+ com o `/dev/shm` padrão de 64 MB do Docker.
- O servidor de preview do HyperFrames faz bind em `127.0.0.1` por padrão; a variável `HYPERFRAMES_PREVIEW_HOST=0.0.0.0` (já definida na imagem) é o mecanismo oficial de opt-in para exposição na LAN. Não exponha essa porta para a internet — não há autenticação.
- Para renderização pesada/distribuída, o HyperFrames também suporta AWS Lambda e cloud render da HeyGen (`hyperframes cloud render`), fora do escopo deste container.
