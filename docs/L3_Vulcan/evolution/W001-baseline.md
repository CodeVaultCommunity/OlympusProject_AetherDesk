# W001/I001 — baseline e auditoria do relato

Data: 23/11/2026. Revisão: 1. Commit inspecionado: `f0e1b6377226b5c56db2467f021c06c510fff6c0`. Árvore inicial: apenas o pacote WOP de evolução não rastreado; 102 arquivos rastreados. Fonte secundária: `Texto colado.txt` anexado à conversa, que consolida A1/A2 e não constitui execução nova. Fonte primária: código e documentos deste commit.

## Ambiente e procedimentos

| Evidência | Procedimento e amostra | Resultado | Limite |
|---|---|---|---|
| Tipo frontend | `cd web; pnpm exec tsc --noEmit` | exit 0 | Não testa interação, browser ou acessibilidade. |
| Testes Python seguros | `.venv/Scripts/python.exe -B -m unittest apps.AetherDesk.identity.test_service apps.AetherDesk.identity.test_http apps.AetherDesk.administration.test_service apps.AetherDesk.monitor.test_service -v` | 10 testes passaram em 9,303 s | Banco temporário e stubs; não cobre Docker real. |
| Ferramentas | `node --version`, `pnpm --version`, Python e `docker version --format '{{.Server.Version}}'` | Node 24.22.1; pnpm 11.25.0; Python do runtime 3.12.14; daemon Docker 28.3.3 | Docker consultado somente em leitura. A versão do Python do `.venv` consta em `pyvenv.cfg` como 3.13. |
| Código | `git rev-parse HEAD`, `rg` e leitura dos módulos citados | Achados abaixo | Inspeção estática não prova comportamento E2E. |
| Performance | `docs/L3_Vulcan/gate-W004.md`, scripts `measure_local.py` e `measure_wsl_service.py` | Resultados de 22/11/2026 preservados como históricos | Nenhum benchmark Docker foi repetido em W001. Não há host Linux independente. |
| UI | `web/src/shell.tsx`, `style.css`, `apps/files.tsx` | Estrutura e ausência de funções verificadas estaticamente | Sem captura de navegador nesta revisão. |

Não foram executados builds, migrações, ensaios hostis, restauração ou testes que criem/removam containers. O arquivo `README.md` da raiz ainda diz que o portão W004 está pendente; `docs/L3_Vulcan/gate-W004.md` registra aprovação técnica local WSL. O aceite anterior é local, sem prova de produção. Essa divergência documental deve ser corrigida em W005.

## Matriz do relato unificado

Estado: **C** confirmado no commit por inspeção ou teste indicado; **P** parcialmente confirmado; **N** não verificável aqui; **D** decisão. Os números de A1/A2 permanecem históricos.

| Seção | Achado e fonte primária | Estado | Verificação ou pendência | Requisito/efeito |
|---|---|---|---|---|
| 1, base atual | Domínios em `apps/AetherDesk`; shell em `web/src/shell.tsx`; identidade por sessão em `identity/service.py` | C | 10 testes seguros e inspeção; Docker funcional não repetido | R001; preservar contratos. |
| 2, desktop | `update()` eleva `z` em todo patch; clock calculado só no render; drag sem limite superior/direito; resize mínimo 400×260 em `shell.tsx` | C | Testar foco, arraste, resize e viewport real em W002/W006 | R003; janela pode sair da área visível e `z` ultrapassar 10.000. |
| 2, persistência | PUT completo com debounce 350 ms sem revisão; `administration/service.py` salva JSON por conta | C | Duas abas e conflito em W002 | R003/R016; última gravação vence. |
| 3, desempenho | `files.tsx` consulta a cada 2,5 s; `files/gateway.py` cria `docker exec` por operação; `monitor/service.py` usa cache | C | p50/p95 atuais com fixture isolada após W001 | R015; custo de processo e polling. |
| 3, bundle | Monaco lazy em `shell.tsx`; números de bundle em `gate-W004.md` | P | Repetir build/size na release candidate | R015; não extrapolar carregamento atual. |
| 4, UI/UX | Seis launchers com glifos Unicode, textos e hero; nenhuma árvore de apps ou paleta | C | Navegadores, teclado, leitor de tela e captura visual | R004/R005; navegação limitada. |
| 5, shell | Não há menu Iniciar nem `onContextMenu`; grid estático e background fixo | C | E2E em resoluções/zoom | R005–R007; personalização ausente. |
| 6, IDE/Git | `FilesApp` serve Explorador e Editor; Monaco só após caminho manual; terminal app separado; nenhum módulo Git | C | Jornada editor→save→terminal→Git→deploy | R010–R012; fluxo de desenvolvimento fragmentado. |
| 7, containers | `runtime/docker.py` chama CLI e `terminal/service.py` usa SDK dentro do ASGI; sem domínio workloads | C | Broker isolado e teste hostil em W002/W006 | R008/R009; privilégio amplo do daemon. |
| 8, IA/MCP | Nenhum domínio `ai/` ou endpoint MCP; capacidades atuais não incluem IA | C | Mock provider, permission/replay tests depois dos contratos | R013/R014; recurso ausente. |
| 9, segurança/contratos | HTTP duplica CSRF/Origin; FastAPI usa `HTTPException` com `detail` heterogêneo; v1 documentada | C | Contract tests por rota e headers em W002/W005 | R004/R016/R024; divergência com envelope v1. |
| 10, mapa técnico | Arquivos e módulos sugeridos coincidem com pontos de composição atuais | P | Confirmar owners em cada onda | R001/R002; mapa é proposta. |
| 11, divergências | Ordem, permissões e deploy são alternativas de produto no relato | D | Decisões em `W001-contracts.md` | R002; implementação não pode pressupor acesso amplo. |
| 12, decisões abertas | Egress, privacidade, Docker, backup, quotas e versões permanecem escolhas | D | Registro U001–U010 em `W001-contracts.md` | R002; flags seguras até decisão. |

### Diferenças entre contrato v1 e implementação

`docs/L3_Vulcan/contracts-v1.md` é referência congelada. Há envelopes `{data,event_id}` na identidade; administração, arquivos, terminal e monitor retornam em geral somente `{data}`. Erros da API usam `detail` do FastAPI, enquanto o contrato descreve `{error:{code,message,event_id,retryable}}`. O desktop v1 documenta revisão, mas `administration/service.py` não guarda revisão nem exige `If-Match`; a API aceita `dict` e valida só alguns campos. O contrato lista operações/paths que diferem das rotas reais (`/files` versus `/files/list`, `/admin/backup/config` versus `/admin/backup`, por exemplo). Esses pontos exigem matriz rota a rota e compatibilidade explícita, sem alterar silenciosamente v1.

## Catálogo L001–L032

Cada linha vincula a lacuna do relatório secundário ao componente observado, à verificação necessária e à consequência. **C** significa que a lacuna está presente; **N** significa que sua extensão depende de ambiente/decisão. Procedimento `rg` significa busca de símbolos e leitura do arquivo no commit acima.

| ID | Fonte/componente e estado | Procedimento pendente | Requisito e consequência se não verificável |
|---|---|---|---|
| L001 | Relato A1/A2, `gate-W004.md`; C: dados herdados | Repetir scripts em fixture e registrar commit/amostra | R001; otimização sem comparador confiável. |
| L002 | `README.md`, `gate-W004.md`, WOP Vulcan; C: texto divergente | Conciliar estados e limites em W005 | R001/R019; aceite local confundido com produção. |
| L003 | `contracts-v1.md`, `identity/http.py`, demais HTTP; C | Contract tests por rota, erro e WS | R016; cliente e API incompatíveis. |
| L004 | `identity/migrations`, `administration/service.py`; C | Upgrade/rollback em banco descartável | R016; perda ou bloqueio de dados. |
| L005 | Scripts de medição e `gate-W004.md`; C | p50/p95, carga, cache frio/quente e dataset | R015; regressão invisível. |
| L006 | `shell.tsx`, `style.css`; C | Browser matrix/zoom/touch | R006; atalhos fora da tela. |
| L007 | `shell.tsx`, menus inexistentes; C | Teclado, foco, leitor de tela, contraste | R004/R005; fluxo inacessível. |
| L008 | `shell.tsx`, `clients.ts`; C | Falha de app, offline, retry e duas abas | R004; perda de sessão/estado. |
| L009 | `runtime/docker.py`; C: só ambiente pessoal | Reconcile e restart/health de workloads | R009; órfãos e deploy indisponível. |
| L010 | Dockerfiles e `deploy/`; N para imagens novas | Scan, SBOM, digest, licença e build isolado | R018/R028; supply chain não atestada. |
| L011 | `runtime/docker.py` usa `--network none`; C | Política DNS/egress e teste de destinos | R008/R026; Git/IA inviáveis ou rede ampla. |
| L012 | Módulo Git ausente; C | Host key, token, hooks e comandos negativos | R011; execução remota insegura. |
| L013 | `files.tsx` usa Monaco básico; C | Linguagens/LSP/formatter suportados | R012; expectativa de VS Code incorreta. |
| L014 | `files.tsx`, `terminal/service.py`; C | 10.000 arquivos, busca, PTY e backpressure | R010/R015; UI/terminal degradados. |
| L015 | IA/MCP ausente; C | Replay, TTL, cancelamento, retenção | R013; ação não autorizada ou dados retidos. |
| L016 | `launch.py`, novos domínios ausentes; C | Correlação, logs redigidos, métricas e alerta | R017; falhas sem diagnóstico. |
| L017 | `web/package.json`, scripts WSL; C | Pipeline e matriz N/N-1 em CI | R019/R027; release não reproduzível. |
| L018 | Wallpaper ausente; C | Quota, MIME, dimensão, CSP e GC | R007/R024; conteúdo ou disco inseguros. |
| L019 | `administration/service.py` upsert; C | Concorrência e chave idempotente | R009/R022; efeitos duplicados/perdidos. |
| L020 | `architecture.md` proíbe conteúdo alheio; N para novos apps | Testes admin negativos | R020; privacidade cruzada. |
| L021 | `shell.tsx` filtra por `role`; `identity/http.py` fornece permissions; C | Override/revogação em duas sessões | R021; UI diverge da permissão real. |
| L022 | `launch.py` cria thread por processo; C | Dois workers, lease/fencing e crash | R022; backup/job duplicado. |
| L023 | `identity/service.py` usa tombstone; novos dados ausentes; C | Lifecycle de todos os recursos | R023; órfãos, retenção indefinida. |
| L024 | Não há cofre/master key; C | Restore, rotação e falha sem chave | R025; secrets irrecuperáveis/expostos. |
| L025 | `launch.py` sem política de headers/CSP; C | Inspecionar respostas e aprovação confiável | R024; XSS/spoofing. |
| L026 | `files.tsx` só texto UTF-8, dirty em memória; C | Binário, grande, reload/crash/encoding | R010/R024; perda de edição. |
| L027 | Proxy de workload ausente; C | SSRF, metadata, DNS, porta, WS/TLS | R026; acesso interno indevido. |
| L028 | Workload/build ausentes; N | Dois owners, cache/layers/logs/GC | R026; vazamento entre contas. |
| L029 | MCP externo ausente; C | Trust registry, schemas e colisões | R025; tool externa não confiável. |
| L030 | `backup/service.py` faz snapshot sem criptografia/off-host obrigatórios; C | RPO/RTO e restore de fixture | R023; recuperação não demonstrada. |
| L031 | Sem flags/kill switches no `launch.py`; C | Safe mode e reversão por domínio | R027; incidente sem contenção. |
| L032 | Sem inventário de licença/proveniência; C | Manifesto de assets/deps/imagens | R028; bloqueio legal de release. |

## Passagem e limites

I001 entrega o inventário acima a I002 e às ondas W002–W005. A baseline de segurança prova apenas controles unitários de identidade; o daemon e o WSL não foram usados para ensaio de isolamento. A baseline de desempenho atual é **pendente**: os resultados p95 históricos de `gate-W004.md` (WSL, 8 usuários, 24 logins e 160 amostras por rota; login 1.032,8 ms, lista 1.473,3 ms, download 1.016,2 ms, métricas 2.063,4 ms na segunda rodada) não foram repetidos neste commit. Não há evidência para aceitar metas de host independente, browser matrix ou melhoria de performance.
