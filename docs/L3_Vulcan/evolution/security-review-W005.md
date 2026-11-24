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

Decisão do responsável em 24/11/2026: aceitar os achados altos **somente para homologação Docker local com dados sintéticos**. Manter contêineres descartáveis, rede externa desligada e sem promoção de imagem. Revarrer a imagem construída pela CI, conferir IDs/versões e atualizar a base Debian assim que houver correção. Distribuição e produção exigem outra decisão sobre o risco residual; o aceite técnico local não equivale a essa decisão.

Na [CI hospedada #3](https://github.com/CodeVaultCommunity/OlympusProject_AetherDesk/actions/runs/45408601796), Trivy 0.76.2 passou os bloqueios e publicou o artefato de segurança ID `14926269299`. O ZIP autenticado foi salvo em `.tmp/github-security-run3.zip` com SHA-256 `73a351c3b4414bc26ccb71b53f64dc24be401cd5d1645bf21abbc3edd2ae384c`, igual ao digest da API do GitHub. `trivy-locks.json`, `trivy-critical.json` e `trivy-fixed-high.json` contêm zero achados em suas respectivas severidades. `trivy-residual.json` lista 86 altos/27 IDs no Debian 13.8, nenhum com `FixedVersion`. Os 86 registros são idênticos aos locais por `VulnerabilityID`, `PkgName`, `InstalledVersion`, `FixedVersion`, `Status` e `Severity`; o nome/tag da imagem é a única diferença de alvo. Este resultado valida a política de homologação local aprovada acima, sem autorizar distribuição ou produção.
