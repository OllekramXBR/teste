# Vídeo OmniPrompt — "A Sofia senta na recepção"

Filme de 18s, 1920×1080 @ 30fps, para a demo do YouTube / hero da landing / Instagram.

Passa nos cinco gates do `hyperframes check` (lint, runtime, layout, motion, contraste **39/39 WCAG AA**).

```bash
cd omniprompt
npx hyperframes preview    # revisar com timeline editável
npx hyperframes render     # gerar o MP4
```

## Estrutura (um destaque por ato)

| Ato | Tempo | Ideia dominante |
| --- | ----- | --------------- |
| 1 | 0–4,2s | A clínica fechada às 23:47 — e o paciente que não está |
| 2 | 4,2–11,5s | A operação acontecendo: a conversa da Sofia e o horário de sábado sendo preenchido |
| 3 | 11,5–14,8s | A prova, com fonte declarada |
| 4 | 14,8–18s | Marca, assinatura e CTA |

## Procedência de cada afirmação (Regra de Ouro #30)

| No vídeo | Fonte |
| -------- | ----- |
| "244 mensagens fora do horário", "20 consultas" | `brainmax/projects/campanha-aquisicao-omniprompt.md` → Prova de venda, clínica 1, 14/mai–07/jul/2026 |
| "Dados de uma clínica em operação, 14/mai a 07/jul de 2026" | mesma fonte — rótulo honesto do recorte |
| "A Sofia senta na recepção." | `LandingPage.jsx` — "Os outros põem a IA na sua mão; a nossa senta na recepção" |
| "Criado por um cirurgião-dentista." | `LandingPage.jsx`, eyebrow do hero |
| "Teste grátis 7 dias" | CTA real da landing + modelo de trial da campanha |
| Conversa da Sofia | **Ilustrativa** — marcada em tela como "Exemplo ilustrativo do fluxo da Sofia", já que não há transcrição real disponível |

Nenhum número foi inventado. A conversa é o único elemento encenado e está rotulada como tal.

## Direção de arte — o que foi respeitado

Seguindo `dental-ia/PRODUCT.md`:

- **"Sala de operação à noite"** — fundo `#0e0f10`, teal `#2BC8DB` como sinal vital, navy `#0D3B66` no CTA. Mesmos valores de `frontend/src/index.css`.
- **Sora** nos títulos (embutida em `fonts/`, subsets latin + latin-ext), Inter no corpo.
- **"Mostre a operação, não a promessa"** — o ato central é a conversa acontecendo e o horário sendo ocupado, não uma lista de benefícios.
- **Vocabulário de consultório** — "horário", "encaixar", "avaliação", "cadeira".
- O traço de sinal vital atravessa o filme inteiro: o monitor é **do caixa**, não do paciente.

### Anti-referências evitadas (vetadas no PRODUCT.md)

Grid de cartõezinhos idênticos · etiqueta maiúscula espaçada em cima de seção · texto em gradiente · vidro fosco decorativo · listras coloridas na borda de cartões · hero "número grande + label" (os números aparecem dentro de uma frase, não como tiles) · azul-hospital claro · sorriso de banco de imagem.

## Arquivos

| Caminho | Papel |
| ------- | ----- |
| `index.html` | A composição inteira — DOM, CSS e timeline GSAP |
| `fonts/sora-*.woff2` | Sora 600/800, subsets latin e latin-ext |
| `vendor/gsap.min.js` | GSAP 3.14.2 embutido (renderiza offline) |

## Para adaptar

- **9:16 (Reels/Stories):** trocar `data-width`/`data-height` para 1080×1920, empilhar o ato 2 (conversa em cima, agenda embaixo) e subir os corpos de texto.
- **Narração/trilha:** adicionar `<audio data-start data-duration data-track-index>` — o framework controla a reprodução.
- **Trocar os números:** editar o ato 3 **e** a linha de fonte junto. Número sem fonte não entra.
