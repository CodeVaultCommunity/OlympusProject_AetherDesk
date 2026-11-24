# Matriz final de rastreabilidade W006 — escopo Docker local

Plano `c1cf6012-e0a4-4f5a-a7fc-52a6ff0363fd` v5. A legenda **V** indica prova local sobre o candidate ou gate anterior ainda válido; **F** indica recurso fechado por decisão de produto, com teste da negação; **P** indica exigência adicional de distribuição/produção, fora da autorização de homologação local. Nenhum P é apresentado como prova concluída. As métricas, hashes, ambiente e limitações estão em `homologation-W006.md`; os gates W001–W005 e seus documentos vinculados dão o histórico integrado.

| Requisito | Estado local | Evidência principal e limite |
|---|---|---|
| R001 | V | `W001-baseline.md`, `gate-W005.md`, 138 testes do ZIP e manifesto W006; números A1/A2 permanecem históricos. |
| R002 | V | `W001-contracts.md` U001–U010 e decisões D012/D013 do plano; produção ainda requer host, chaves, destinos e capacidade. |
| R003 | V | `gate-W002.md`, `desktop.spec.ts`, 99 amostras de zoom nativo W006 e teste multiaba. |
| R004 | V | Cliente/sessão/offline e Error Boundary em `gate-W002.md`; 59 E2E do bundle e CI frontend W005. |
| R005 | V | App Registry/menu/paleta/atalhos em `gate-W004.md`; seis atalhos, axe, teclado e Orca W006. |
| R006 | V | Reflow 3 resoluções × 5 escalas CSS × 3 motores, mais zoom nativo 3 motores/99 amostras; alcance de atalhos/janelas. |
| R007 | V | Upload/quota/thumbnail/limpeza/CSP em `gate-W004.md`, regressão W005; browser W006 preserva shell. |
| R008 | V | Fixture `verify_broker_containers.ps1`: web sem socket/grupo/FD Docker; IPC tipado, nonce, revogação e restart. |
| R009 | V/F | `gate-W003.md`, `gate-W005.md`, `workloads/test_*`: ownership, job, health, rollback, secrets e proxy local; Dockerfile arbitrário e proxy público fechados. |
| R010 | V | `gate-W004.md`, E2E IDE/Monaco e regressão ZIP; limites do editor em `operations.md`. |
| R011 | V/F | `workspace/test_git.py`, `test_credentials.py`, smoke Git local; remoto fechado sem egress/host keys configuradas. |
| R012 | V/F | `workspace/test_lsp.py`, diagnóstico TypeScript nos três motores W005; extensões/CLIs arbitrárias fora do suporte. |
| R013 | V/F | `ai/test_approval.py`, `test_tools_http.py`, `test_chat.py`; replay, owner, revogação, disclosure. Providers/MCP externos fechados. |
| R014 | F | `W001-contracts.md` e `contracts-W003.md`: CLIs de IA externas sem governança MCP não são habilitadas. |
| R015 | V | Benchmarks W006 20/8, 100/10.000 arquivos, watcher/index e jobs; SLO de host independente P. |
| R016 | V | `composition/test_upgrade.py`, `support/test_migrations.py`, `verify_candidate_recovery.py`; rollback via snapshot v1, não binário v1 sobre schema novo. |
| R017 | V/P | Correlação/auditoria/métricas testadas em `support/test_correlation.py`, broker e CI; alertas/retention no host real P. |
| R018 | V/F | Regressão ZIP, scan hospedado e fixture broker hostil; 86 HIGH sem fix aceitos somente local; egress e build arbitrário fechados. |
| R019 | V/P | CI #3 quatro jobs verdes, ZIP/SBOM iguais, runbook e restore Docker; instalação systemd real e distribuição P. |
| R020 | V | `identity`, `administration`, `workloads/test_http.py`, `ai/test_chat.py`: admin lifecycle não recebe conteúdo privado alheio. |
| R021 | V | `desktop.spec.ts` revogação de capabilities; `identity/test_http.py` e testes de rotas revalidam servidor. |
| R022 | V | `support/test_leases.py`, `test_workers.py`, `test_backup_scheduler.py` e restart broker W006. |
| R023 | V/P | `support/test_lifecycle.py`, backup v2 e restore; retenção/GC físico e off-host configurados pelo operador P. |
| R024 | V | CSP/headers, upload restrito, arquivos/encoding/draft e approval UI nos gates W002–W005; axe/Orca/crash W006. |
| R025 | V/F/P | `support/test_secrets.py` testa rotação/revogação/falha sem chave; trust registry MCP externo fechado; custódia externa P. |
| R026 | V/F | `workloads/test_proxy_policy.py`, `test_proxy.py`, `test_build.py`, `test_docker_runtime.py`: owner, IP/porta, metadata/rebinding, cache e imagem; proxy público fechado. |
| R027 | V/F | `gate-W005.md` e `composition/test_app.py`: safe mode e kills IA/deploy; rollout remoto permanece fechado. |
| R028 | V/P | SBOM SPDX 285 pacotes, gate de licenças diretas e `license-review-W005.md`; notices, textos e marcas antes de distribuir P. |

| Lacuna | Estado local | Fechamento ou trava explícita |
|---|---|---|
| L001 | V | Baseline `W001-baseline.md` separada das medições W006 com commit, dataset e ambiente. |
| L002 | V/P | `gate-W005.md` reconcilia WOP e CI; Docker local não é host de produção. |
| L003 | V | Contratos v1/v2 em `test_launch.py`, `composition/test_http_integrated.py`, `test_upgrade.py`. |
| L004 | V | Migração/forward recovery/snapshot v1 em `verify_candidate_recovery.py`. |
| L005 | V/P | Percentis e amostras em `homologation-W006.md`; orçamento de host independente P. |
| L006 | V | Matriz CSS, touch e zoom nativo por motor W006. |
| L007 | V | Axe, teclado, contraste, movimento reduzido e Orca real em Firefox W006. |
| L008 | V | `desktop.spec.ts` offline/erro/multiaba, crash real nos três motores; E2E bundle W006. |
| L009 | V | `workloads/test_service.py`, `test_docker_runtime.py`, reconciliação broker após restart. |
| L010 | V/F/P | Digest/SBOM/scan/CI; Dockerfile do usuário fechado; re-scan antes de distribuição P. |
| L011 | F | Egress negado; destinos reais só após política U002 e teste em host aprovado. |
| L012 | V/F | `workspace/test_git.py`, `test_credentials.py`; remoto negado por padrão. |
| L013 | V | `workspace/test_lsp.py` e diagnóstico TypeScript; escopo limitado documentado. |
| L014 | V | 10.000 arquivos/index/busca e PTY com quota/backpressure; eco broker medido. |
| L015 | V/F | `ai/test_approval.py`, `test_chat.py`, `test_tools_http.py`; provider externo fechado. |
| L016 | V/P | Correlação/auditoria/rotação 12.000 requisições; alerta operacional no host P. |
| L017 | V/P | CI #3, hashes ZIP/SBOM, regressão e restore; deploy real P. |
| L018 | V | Wallpaper seguro/quota/thumbnail/GC em `gate-W004.md` e regressão. |
| L019 | V | Idempotência de workloads/Git/approvals e ETag desktop em testes ZIP/E2E. |
| L020 | V | Testes owner/admin negativos nos domínios de dados; privacidade por capability. |
| L021 | V | UI usa capabilities efetivas e remove app após revogação; servidor revalida. |
| L022 | V | Lease/fencing de dois workers e crash em `support/test_leases.py`, `test_workers.py`. |
| L023 | V/P | Tombstone/export/delete/restore testados; política de purga real P. |
| L024 | V/P | Cofre AES-GCM versionado, rotação e restore sintético; custódia externa P. |
| L025 | V | CSP/headers e approval UI confiável em `test_launch.py`, `ai/test_tools_http.py` e gates. |
| L026 | V | Arquivo binário/grande/encoding/EOL/draft/crash em testes workspace e três browsers. |
| L027 | V/F | Proxy owner/host/IP pinado, metadata/rebinding/colisão em testes; público desligado. |
| L028 | V/F | Build gerado, labels/volume/namespace owner e quotas em testes Docker; cache externo fechado. |
| L029 | F | MCP externo exige registry/pinagem; feature desligada por U010. |
| L030 | V/P | Backup v2 criptografado/restore medido; RPO/RTO configuráveis sem meta global, off-host P. |
| L031 | V/F | Kills, safe mode e defaults fechados em `gate-W005.md`. |
| L032 | V/P | SBOM/licenças declaradas; revisão de notices/marcas para distribuição P. |

## Pendências fora do aceite local

Antes de distribuição ou produção: host Linux independente e systemd, TLS/proxy/domínio/registry, políticas de egress e providers reais, custódia de versões de chave e cópia off-host, retenção e RPO/RTO operacionais, SLO/capacidade e soak prolongado, métrica de CPU, notices/marcas e nova decisão sobre as vulnerabilidades residuais. A decisão do responsável sobre **aceitar tecnicamente W006 apenas em Docker local** é registrada no portão próprio; esta matriz não a presume.
