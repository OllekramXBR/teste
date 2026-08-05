# HyperFrames no Unraid — imagem de preview/render
#
# Replica o ambiente de renderização de produção do HyperFrames
# (mesmo Chromium, fontes e FFmpeg do Dockerfile.test oficial do repo
# heygen-com/hyperframes), com o CLI `hyperframes` instalado globalmente.
#
# Build:  docker build -t hyperframes-studio:latest .
# Run:    docker run -d -p 3002:3002 -v /mnt/user/appdata/hyperframes:/workspace hyperframes-studio:latest

FROM node:22-bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    unzip \
    ffmpeg \
    chromium \
    libgbm1 \
    libnss3 \
    libatk-bridge2.0-0 \
    libdrm2 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libcups2 \
    libasound2 \
    libpangocairo-1.0-0 \
    libxshmfence1 \
    libgtk-3-0 \
    fonts-liberation \
    fonts-noto-color-emoji \
    fonts-noto-cjk \
    fonts-noto-core \
    fonts-noto-extra \
    fonts-noto-ui-core \
    fonts-freefont-ttf \
    fonts-dejavu-core \
    fontconfig \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean \
    && fc-cache -fv

# Usa o Chromium do sistema em vez de baixar um na instalação do Puppeteer
ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true
ENV PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium
ENV CONTAINER=true

RUN npm install -g hyperframes && npx --yes hyperframes --version

# O preview do HyperFrames faz bind em 127.0.0.1 por padrão; dentro do
# container é preciso expor na interface do Docker para a LAN enxergar.
ENV HYPERFRAMES_PREVIEW_HOST=0.0.0.0
ENV HYPERFRAMES_PORT=3002

WORKDIR /workspace
VOLUME /workspace
EXPOSE 3002

COPY start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

ENTRYPOINT ["/usr/local/bin/start.sh"]
