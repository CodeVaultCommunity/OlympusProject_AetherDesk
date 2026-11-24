# Triagem de segurança do candidate W005

Escopo: imagem local `aetherdesk-files:w005-local` (Debian 13.8), varredura Trivy 0.76.2 em 24/11/2026, com relatório bruto em `.tmp/trivy-image-trixie.json`. Essa imagem é uma fixture de homologação, não uma imagem de produção nem o ZIP de release. Repetir a varredura na CI e no ambiente de distribuição antes de qualquer promoção.

| Resultado | Contagem |
| --- | ---: |
| Críticos | 0 |
| Altos | 86 ocorrências em 31 pacotes Debian / 27 IDs distintos |
| Altos com versão corrigida informada | 0 |
| Altos `affected` / `fix_deferred` | 82 / 4 |
| Altos ou críticos nos locks atualizados | 0 |

Os pacotes mais repetidos nos achados altos são `python3.13`, `python3.13-minimal`, `libpython3.13-stdlib`, `libpython3.13-minimal` (cinco ocorrências cada) e `util-linux`/bibliotecas associadas (quatro cada). A ausência de versão corrigida no relatório **não demonstra ausência de exploração**. Os 86 registros permanecem riscos residuais; a política automatizada bloqueia qualquer crítico e alto com correção disponível, e grava todos os altos para triagem.

Para a homologação local, manter contêineres descartáveis, dados sintéticos, rede externa desligada e sem promoção de imagem. Revarrer a imagem construída pela CI, conferir IDs/versões e atualizar a base Debian assim que houver correção. O responsável ainda precisa decidir se aceita os altos sem correção e as condições de mitigação antes de distribuir ou implantar; o aceite técnico local não equivale a essa decisão.
