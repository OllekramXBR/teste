# Vídeo de exemplo

Composição HyperFrames de 10 segundos, 1920×1080 @ 30fps, em três atos (abertura → três cartões → encerramento), animada com GSAP.

Foi **renderizada e validada** — `hyperframes check` passa nos cinco gates (lint, runtime, layout, motion e contraste WCAG AA) e o MP4 saiu com 300 frames.

## Testar no Mac

```bash
cd exemplo
npx hyperframes preview    # abre no navegador com live reload e timeline editável
npx hyperframes render     # gera o MP4 em renders/
```

Requer Node.js 22+ e FFmpeg (`brew install node ffmpeg`) — ou rode `bash ../install-mac.sh` na raiz do repositório.

Vale rodar também `npx hyperframes check`, que é o portão de qualidade completo antes de renderizar.

## Estrutura

| Arquivo             | Papel                                                          |
| ------------------- | -------------------------------------------------------------- |
| `index.html`        | A composição inteira — DOM, CSS e a timeline GSAP               |
| `vendor/gsap.min.js`| GSAP 3.14.2 embutido, para a composição renderizar offline      |
| `renders/`          | Saída dos renders (ignorada pelo git)                           |

## Como ler o `index.html`

- O root (`#root`) declara `data-composition-id`, `data-width`, `data-height` e `data-duration="10"`.
- Cada cena é um `.clip` com `data-start`, `data-duration` e `data-track-index` — o framework controla a visibilidade dos clips.
- Existe **uma única** timeline GSAP pausada, registrada em `window.__timelines["main"]`, construída de forma síncrona no load.
- O preenchimento de fundo fica num filho full-bleed (`#fundo-fill`), nunca no root — pôr no root faz o compositor de frames renderizar preto.
- Os `.set(..., { autoAlpha: 0 })` nos limites das cenas são *hard kills* exigidos pelo linter: sem eles, um seek não-linear pode cair depois do fade e deixar estado de visibilidade obsoleto.

## Editar

Mude os textos, as cores em `:root` ou os tempos das cenas e rode `npx hyperframes preview` — o reload é automático. Para mexer na duração total, ajuste o `data-duration` do root **e** as posições na timeline.
