# W001/I002 — contratos e decisões para a evolução

Data: 23/11/2026. Revisão: 1. Base: commit `f0e1b6377226b5c56db2467f021c06c510fff6c0`, `docs/L3_Vulcan/{architecture,contracts-v1,threat-model,operations,gate-W004}.md` e [baseline](W001-baseline.md). Este documento é proposta técnica de contrato. **Nenhum item ou portão W001 está aceito apenas por sua redação.** Decisões de operação em host real ficam condicionadas à evidência e ao responsável indicado.

## Decisões U001–U010

| ID | Responsável | Resultado operacional para implementação | Bloqueio/condição |
|---|---|---|---|
| U001 | Engenharia | Achados confirmados, parciais e não verificáveis na baseline W001/I001. Comparação de performance usa apenas amostra reproduzida na mesma configuração. | Repetir benchmark atual antes de aceitar ganho. |
| U002 | Produto + segurança | Egress negado por padrão. Classes `git_remote`, `registry`, `packages`, `ai_provider` e `workload_public` exigem política de destinos e quotas separadas; proxy valida DNS/IP a cada conexão. | Nenhuma classe habilitada sem destinos, limites e teste. |
| U003 | Produto + privacidade | Admin pode ver metadados e operar lifecycle com capacidade explícita. Logs, exec, arquivos, chats e secrets alheios ficam negados por padrão, cada um com capacidade separada se produto decidir ampliar. | Ampliação exige decisão do responsável, aviso e teste negativo. |
| U004 | Engenharia + segurança | Broker local em processo separado, socket Unix protegido, protocolo de operações tipadas; só ele acessa daemon Docker. Serviço ASGI e containers não recebem socket/grupo Docker. Preferir daemon rootless dedicado se compatível com volumes, PTY e backup. | Escolha final do daemon depende de protótipo Linux e teste de isolamento; não promover broker ao host real antes disso. |
| U005 | Produto | Interface de provedores versionada. Nenhum provedor externo cadastrado/ativo por padrão; retenção de chat configurável e export/delete por owner. Orçamento padrão zero para chamadas externas até configuração. | Preços, política do provedor e retenção real precisam de decisão antes de habilitar. |
| U006 | Operação | WSL é homologação local; não há host Linux independente, domínio, registry ou proxy de workloads identificados. | Bloqueia aceite de produção, não o desenvolvimento isolado. |
| U007 | Produto + segurança | Capacidades separadas: `containers.read`, `containers.build`, `containers.lifecycle`, `containers.logs`, `containers.exec`, `containers.remove`, `containers.deploy`, `containers.admin.lifecycle`; acesso a conteúdo alheio exige capacidades próprias futuras. | UI deriva da matriz efetiva, backend sempre revalida. |
| U008 | Produto + segurança | MVP usa templates/imagens aprovadas e digest fixo. Dockerfile do usuário, Compose arbitrário e build com rede ficam desabilitados. | Habilitar Dockerfile só após BuildKit isolado/rootless, scan e ensaio hostil. |
| U009 | Produto (decisão em 23/11/2026) + operação | RPO, RTO e retenção serão configuráveis, sem meta fixa global. O mecanismo deve aceitar criptografia autenticada, destino off-host e política por classe de dados; valores de fixture serão identificados em cada ensaio. | Destino e custódia de chave são configurados pelo operador antes de ativar backup real; nenhum número de fixture vira compromisso operacional. |
| U010 | Engenharia + operação | Flags independentes `broker_v2`, `egress_git`, `egress_registry`, `egress_packages`, `egress_ai`, `deploy_templates`, `deploy_dockerfile`, `git_remote`, `ai_providers`, `mcp_external`, `workload_proxy`; todas fechadas por padrão, salvo `broker_v2` no ambiente de teste após gate. Kill switch prevalece sobre flag. | Cada ativação exige owner, compatibilidade, observabilidade e rollback testado. |

Esses resultados implementam defaults conservadores já previstos no plano. Não implicam escolha comercial, acesso a produção ou autorização para transferência de dados a provedores externos.

## Contratos transversais congelados para implementação

1. Identidade: `ActorContext` server-side define owner. Cada HTTP, WS, job, broker call e tool revalida sessão/capacidade/recurso; IDs do corpo/rota não definem owner. Catálogo frontend usa permissões efetivas e atualiza após revogação.
2. HTTP: manter rotas v1 funcionais. Normalizar `{data,revision?,event_id}` e `{error:{code,message,event_id,retryable}}` de forma aditiva; mudanças que alterem semântica de campos, códigos ou precondições existentes usam `/api/v2`. CSRF/Origin comuns; mutação longa exige `Idempotency-Key`, `operation_id` e consulta de resultado.
3. Desktop v2: `schemaVersion=2`, `revision` monotônica e ETag, apps conhecidos no registry, janelas validadas, posição lógica `column,row` mais fallback/clamp de viewport, wallpaper referenciado por ID. `PUT` com `If-Match`; conflito 412 oferece recarregar/mesclar. Migração do JSON v1 é idempotente e preserva estado bruto em backup de fixture.
4. Broker: socket de acesso restrito, autenticação mútua local, autorização de operação e resource binding, nonce/TTL para mutações, allowlist de imagem/mount/network/flags, limites de CPU/RAM/PIDs/storage, auditoria sem conteúdo. ASGI, runtime pessoal e workload nunca veem Docker socket. Operações de backup também passam pelo broker.
5. Workers: lease persistente com fencing token monotônico, heartbeat, deadline e recuperação; outbox e jobs trazem `operation_id` único. Shutdown para de aceitar jobs, libera lease e grava estado antes de encerrar. Reexecução consulta estado observado antes de efeito remoto.
6. Workloads: banco é autoridade de owner; labels Docker reforçam. Criar por template/digest gera job assíncrono. Estado desejado/observado, health, release anterior, logs com retenção, quotas, GC e reconciliação após crash. Admin lifecycle não implica leitura de logs/exec. Cada rota/proxy vincula owner e rejeita endereço interno, metadata, rebinding e porta alheia.
7. Workspace/Git: resolver caminhos sob `/persist` sem seguir symlink externo. Arquivo texto mantém encoding, EOL, revision e recovery draft; binário/grande abre em modo limitado. Git local executa subcomandos tipados, com paths após `--`, hooks externos desabilitados, timeout/output limit; SSH host keys fixadas e credenciais em cofre. Remoto depende de egress explícito.
8. IA/MCP: provider configurado por referência a secret, com disclosure de envio e quotas. Tool nativa/externa tem schema, versão, capability, classificação de risco e timeout. Aprovação humana vincula ator, sessão, tool, hash dos argumentos, risco, TTL e nonce único; revalidar antes do efeito e após streaming/cancelamento. Conteúdo de prompt, arquivo ou tool não pode criar UI de aprovação. MCP externo exige trust registry e prefixo/versão para evitar colisões.
9. Dados: cada tabela/artefato declara owner, classificação, retenção, export/delete, inclusão em backup, restore e GC. Tombstone não elimina dados automaticamente. Master key fora de volumes e do banco, com versão, rotação, custódia separada e falha segura sem chave. Segredos nunca voltam completos nem entram em log/backup em claro.
10. Rollout: versões web/API/broker negociam janela N/N-1. Flag não substitui autorização; safe mode desabilita deploy, egress, IA e mutações de workload, mantendo leitura/recuperação. Observabilidade expõe correlação e estado de jobs sem conteúdo pessoal.

## Matriz R003–R028

Colunas compactas: interface/dado; permissão/falha; verificação; ciclo de vida/reversão. Todas são contratos para testes posteriores, não evidência de implementação.

| R | Interface e dado | Permissão e falha | Verificação | Ciclo de vida e reversão |
|---|---|---|---|---|
| 003 | Desktop v2, window state, ETag | preferences.write; 412/invalid state | Drag/foco/resize/duas abas | v1→v2; backup bruto, N-1 compatível |
| 004 | HTTP client, sessão, error boundary | sessão ativa; 401/offline/retry | unit/E2E revogação, falha de app | limpar cache ao logout; voltar client N-1 |
| 005 | Registry, Start/context menu, shortcuts | capacidades efetivas; app revogado | teclado, a11y, E2E | descriptor versionado; flag por app |
| 006 | Grid lógico e posições | owner; viewport reduzido | zoom 67–200%, touch, resize | manter ordem lógica; fallback/clamp |
| 007 | Wallpaper ID/blob/thumbnail | preferences.write; MIME/quota | upload malicioso, CSP, GC | remover órfãos; tema sólido fallback |
| 008 | Broker IPC, capability token | allowlist; daemon indisponível | boundary e mount negatives | adapter N-1 só em fixture; kill switch |
| 009 | Workload/job/release/proxy | owner + capability; conflict/timeout | dois owners, crash, rollback | retention/GC; release anterior |
| 010 | IDE workspace/layout/terminal | files/terminal; revisão obsoleta | editor/save/PTY/deploy E2E | recovery draft; layout v1 fallback |
| 011 | Git status/diff/stage/commit/remoto | git.* + files; conflito/host key | local, remote deny, hooks | credencial revogável; repo preservado |
| 012 | LSP/formatter adapter limitado | files.read/write; servidor falho | linguagens suportadas | processo descartável; editor básico fallback |
| 013 | Provider/chat/tool/approval | ai.* + alvo; replay/timeout | prompt injection, nonce, revoke | export/delete/retention; provider off |
| 014 | Terminal CLI + MCP token escopado | egress/tools; CLI fora de proxy | CLI governada vs externa | revogar token; egress off |
| 015 | Events/cache/search/jobs | owner; stale/backpressure | p50/p95, carga, cancelamento | TTL/GC; polling limitado fallback |
| 016 | API v1/v2 + schemas | auth/CSRF; version skew | contract N/N-1, upgrade | down/forward recovery e snapshot |
| 017 | logs/metrics/traces/events | leitura operacional; redaction | correlação, alertas, segredo fixture | retenção por classe; desligar tracing |
| 018 | políticas runtime/build/web | owner; escape/quota | hostile fixture/IDOR/SSRF | quarentena/kill switch e restore |
| 019 | pipeline/manifest/SBOM/runbook | release operator; gate falho | CI, instalação WSL/host | pacote N-1 e dados compatíveis |
| 020 | admin lifecycle/metadados | admin.lifecycle; conteúdo negado | admin negative tests | trilha de acesso/retention |
| 021 | capabilities catalog/event | permissions efetivas; revogação | override e WS/E2E | invalidar cache; UI oculta app |
| 022 | lease/fencing/outbox/job | worker identity; lease perdido | dois workers, crash/retry | recuperar job; backup único |
| 023 | inventory/retention/backup | owner + privacy; conta apagada | export/delete/restore 2 contas | tombstone, GC, cópia off-host |
| 024 | CSP/headers/content/editor | upload/files; XSS/binário | CSP, MIME, crash recovery | quarantine, draft/backup; safe UI |
| 025 | key vault/provider/MCP registry | secret scope; key indisponível | rotate/revoke/schema drift | key escrow/restore; provider off |
| 026 | proxy/network/cache namespaces | owner; SSRF/rebinding | cross-owner/cache/metadata | revogar rota, apagar cache/artefato |
| 027 | flags/version negotiation | operador; skew/incident | safe mode e N/N-1 | rollback de bundle/broker/flag |
| 028 | asset/license/SBOM inventory | release gate; licença incerta | scan/review de dependências | substituir asset e refazer build |

## Baseline, budgets e matriz de teste

O commit atual passou `tsc --noEmit` e dez testes Python seguros. Não há testes frontend automatizados no `web/package.json`. A medição anterior em WSL (`gate-W004.md`) mostrou p95 da segunda rodada com 8 membros: login 1.032,8 ms (24 amostras), listagem 1.473,3 ms, download 1 MiB 1.016,2 ms, métricas 2.063,4 ms (160 amostras cada). São dados históricos, não revalidados aqui; primeira rodada excedeu os limites, revelando variação de aquecimento. O alvo independente herdado de `architecture.md` (login <1 s, lista de 100 <500 ms, arquivo 1 MiB <1 s, PTY <150 ms, métricas <2% CPU) é hipótese, não aceite.

Para novo baseline, registrar host, Python/Node/Docker, imagem digest, commit, 20 contas/8 simultâneos, 100/10.000 arquivos, 1 MiB/2 GiB por conta, cache frio/quente, 30 ou mais amostras por operação e p50/p95/p99/erro. Separar custo de login Argon2id do custo Docker e medir UI (LCP, interação de drag, abertura Monaco). Uma melhoria exige mesmo dataset e ambiente, redução de p95 sem regressão de isolamento ou erro. Guardas locais WSL anteriores (login <6 s, lista <2,5 s, download <2 s, métricas <3 s) servem apenas para regressão local; W001 não lhes concede aceite novo.

Matriz visual mínima: Chromium, Firefox e WebKit em desktop 1920×1080, 1366×768 e 1024×768; zoom 67%, 100%, 125%, 150% e 200%; viewport 390×844 e 768×1024 com touch; teclado-only, leitor de tela, alto contraste e `prefers-reduced-motion`. Em cada combinação, todos os ícones devem permanecer alcançáveis por rolagem/reflow e janelas devem ter título e controles recuperáveis. Se o runner de browser não estiver disponível, marcar combinação não verificada, sem declarar aceite.

## Migrações, propriedade e passagem

Migração ordenada: (1) inventário e snapshot de SQLite/volumes de fixture; (2) runner exclusivo versionado para tabelas hoje criadas por `AdministrationService`, `TerminalService` e `BackupService`; (3) desktop v2 com conversão v1 idempotente e revisão; (4) tabelas de lease/outbox/flags/key metadata; (5) workloads/Git/IA com schema próprio; (6) contract tests N/N-1; (7) ensaio restore e forward recovery. Cada passo registra versão, backup, transação, reexecução e critério de parada. Rollback de código não deve abrir schema incompatível; se down migration destruir dados, aplicar forward recovery documentado.

Ownership de W002: I003 possui `support/http`, identidade, runner de migração, lease/outbox/flags/secret foundation; I004 possui desktop/frontend foundation e `administration/service.py` para estado; I005 possui broker/runtime/terminal/files/monitor adapters. A composição em `launch.py` é integrada no portão W002 para provar o critério explícito de ASGI sem Docker; o catálogo global de apps e os domínios novos continuam nas ondas posteriores. W003 recebe interfaces estáveis, não autorização para Dockerfile arbitrário ou egress externo.

## Ameaças e revisão técnica

Fronteiras adicionais às de `threat-model.md`: browser→approval (spoofing por texto da IA); tool externa→MCP (schema/identidade/collision); provider→dados privados (retenção/custo); web→broker (token reutilizado/command injection); broker→daemon (montagem e flags); workload→proxy/metadata (SSRF e DNS rebinding); build→cache de outro owner; scheduler→backup (dupla execução); atualização→schema/key (rollback quebrado). Controles correspondentes estão nos contratos 1–10; provas são testes negativos de duas contas, replay/expiração, dois workers, DNS/IP mutável, cache isolado, restore e matriz N/N-1 em ambiente descartável.

Revisão técnica inicial por inspeção do código: contratos acima são implementáveis sem quebrar o v1 se o cliente antigo continuar atendido. Revisão de segurança e aceite dos contratos permanecem **pendentes** de protótipo do broker/egress em Linux, ensaio de backup/key e decisão operacional U009. Nenhum acesso a produção ou provedor foi testado.
