# Template de campanha — vídeos em lote

Versão parametrizada do filme 16:9 do OmniPrompt. Um `index.html`, N vídeos: cada linha do lote vira um MP4 com praça e especialidade próprias.

Testado de ponta a ponta — 4 variantes renderizadas e conferidas frame a frame.

## Rodar

```bash
./renderizar-lote.sh                          # lote de teste (4 vídeos)
./renderizar-lote.sh lote-primeira-onda.json  # onda inteira (48 vídeos)
```

O script roda `hyperframes check` **antes** do lote e aborta com código != 0 se qualquer gate falhar — 48 vídeos errados custam uma hora de máquina. Feito para a Nix chamar num cron: o código de saída alimenta o alerta do Telegram.

Saída em `renders/{slug}.mp4` mais um `renders/manifest.json` com o status de cada linha. Para mudar o destino: `SAIDA='outra/pasta/{slug}.mp4' ./renderizar-lote.sh`.

## Variáveis

Declaradas em `data-composition-variables` no `<html>`:

| Variável | Onde aparece | Exemplo |
| -------- | ------------ | ------- |
| `cidade` | Ato 1, ao lado do relógio | `Ribeirão Preto` |
| `especialidade` | Pergunta do paciente **e** o horário na agenda | `ortodontia` |
| `cta` | Botão do fecho | `Teste grátis 7 dias` |
| `slug` | Só o nome do arquivo, não aparece em tela | `londrina-ortodontia` |

Ligadas por `data-var-text` — sem script. Omitir uma variável na linha usa o `default` do esquema.

### O que deliberadamente NÃO é variável

Os números de prova (**244** mensagens, **20** consultas) e a linha de fonte. Eles vêm de **uma** clínica, no recorte 14/mai–07/jul/2026. Transformá-los em variável faria cada vídeo insinuar que o dado é da clínica destinatária — dado fabricado com aparência de prova, exatamente o que a Regra de Ouro #30 existe para impedir. Se um dia houver número por praça, ele entra junto com a própria fonte, nunca sozinho.

## Lotes

- `lote-teste.json` — 4 linhas, para validar mudanças rápido (~5 min).
- `lote-primeira-onda.json` — 48 linhas: as 12 praças da primeira onda × 4 especialidades (implante, ortodontia, estética, prótese). ~65 min de render.

Formato: array JSON de objetos, uma chave por variável.

```json
[{ "slug": "londrina-ortodontia", "cidade": "Londrina", "especialidade": "ortodontia" }]
```

`--strict-variables` está ligado no script: chave não declarada ou tipo errado vira erro, não aviso.

## Custo de máquina

~1min20 por vídeo de 18s em 4 núcleos. As 48 variantes saem em pouco mais de uma hora — irrelevante num cron de madrugada no Unraid. O renderizador reaproveita frames estáticos (~5% neste filme), então filmes mais parados rendem mais rápido.

## Antes de disparar

Dois pontos levantados na análise da campanha, que continuam valendo:

- **Anexar vídeo no WhatsApp aumenta o risco de ban** que a campanha já monitora. Link (YouTube) é mais seguro que mídia anexada — e dá métrica de visualização, que anexo não dá.
- **Nome da clínica dentro do vídeo** não foi parametrizado de propósito: praça e especialidade cobrem quase todo o ganho de personalização sem cruzar a linha do "isto foi gerado em massa".
