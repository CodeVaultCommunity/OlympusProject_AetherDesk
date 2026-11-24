# Portão W003 — shell e serviços isolados

Plano `c1cf6012-e0a4-4f5a-a7fc-52a6ff0363fd` v5. **Gate técnico local W003 aprovado após revalidação em 24/11/2026.** Ao consumir I007 na W004 foi detectado que `start` faltava e `restart` não avançava a revisão do contêiner; serviço e Docker foram corrigidos e a regressão integral repetiu. Este aceite cobre módulos isolados e fixtures locais, não exposição HTTP global nem produção.

| Item | Aceite isolado | Evidência |
| --- | --- | --- |
| I006 Shell | Sim | `pnpm build`, `pnpm lint`, dez testes frontend e 97 E2E aprovados, duas omissões intencionais; axe WCAG A/AA e foco contido do menu em Chromium, Firefox e WebKit; matriz viewport/touch/reduced motion e revogação. Evidência visual/assistiva nativa segue D013/I014. |
| I007 Workloads | Sim | Testes Linux com Docker real de isolamento, build sem Dockerfile do usuário, rede interna, logs/metrics, secret tmpfs por referência, health/rollback e revisão idempotente para start/restart; scan/SBOM/provenance assinados em fixture, owner/admin/IDOR, job superseded e migração v1→v3. Benchmark de 100 workloads/20 contas/oito workers teve 100 starts únicos; request p95 109,184 ms e reconcile p95 281,572 ms com runtime fake. |
| I008 Workspace/Git | Sim | Watcher Bash/inotify sem polling, FTS5/eventos, busca/arquivo/revisão, Git local e remoto bare, conflito, cancelamento, token askpass, known hosts e output limitado; contrato LSP desabilitado por padrão. Benchmark 10.000 arquivos: index build 10,728 s e busca p95 1,73 ms na fixture Windows; watcher Linux p95 0,945 ms/100 eventos. |
| I009 IA/MCP | Sim | Provider fake com disclosure, stream/cancel/revogação de sessão e secret, quotas de custo/caracteres/taxa, retenção/export/delete, trust pinado de tool externa, approval exato/replay/estado `unknown`, testes adversariais de saída não confiável e migração chat v1→rate v2. Provider externo continua desabilitado até configuração explícita U005. |

## Gate e handoff

- A regressão `scripts/verify_linux_suite.ps1` passou novamente com **119 testes, zero falha e zero omissão** em Docker Linux descartável após a correção de `start`/`restart`. `git diff --check` e consistência WOP foram conferidos. Execuções anteriores encontraram ordem não determinística na busca e corrida na fixture de secret; ambas foram corrigidas.
- `contracts-W003.md` registra exports, clients, migrations privadas, estados e limites necessários a I010–I012. `security-review-W003.md` liga cada threat case aos controles e às provas. Nenhum módulo W003 foi registrado em `launch.py`, composição HTTP, capability catalog ou shell global antes de W005.
- O scanner de imagem real, provider externo, domínio/proxy público, WebSocket/TLS, egress e host Linux independente continuam condicionados aos gates W005/W006. O build com scanner fake e o proxy com upstream fake são provas de contrato local; o Docker real confirmou isolamento, rede e secret injection. Nenhuma implantação de produção foi feita.
- W004 está liberada para I010–I012 em seus diretórios e fixtures. W005/W006 permanecem bloqueadas até seus predecessores.
