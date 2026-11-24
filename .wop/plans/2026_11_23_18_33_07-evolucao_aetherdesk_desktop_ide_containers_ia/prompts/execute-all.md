---
artifact: wop-execute-all
plan_id: c1cf6012-e0a4-4f5a-a7fc-52a6ff0363fd
plan_version: 5
plan_title: "Evoluir o AetherDesk com desktop, IDE, containers e IA governada"
language: pt-BR
source_readme: README.md
source_readme_sha256: c407e9cbdac5c9a78569615fb6dd0aad604542b5699feeae0986be5b3e2d2612
---

# Evoluir o AetherDesk com desktop, IDE, containers e IA governada

<!-- wop:prompt-section wave_prompts -->
- prompts/wave-01.md — W001 — Descoberta, baseline e contratos
- prompts/wave-02.md — W002 — Estabilização e fronteira de privilégios
- prompts/wave-03.md — W003 — Shell e serviços de plataforma
- prompts/wave-04.md — W004 — Aplicativos de desenvolvimento e operação
- prompts/wave-05.md — W005 — Integração, migrações e operação
- prompts/wave-06.md — W006 — Hardening, desempenho e aceite

<!-- wop:prompt-section orchestration -->
## Resultado <!-- wop:section outcome -->

Entregar uma evolução verificável do AetherDesk com desktop responsivo e personalizável, shell modular, menu Iniciar e menus de contexto, broker Docker de privilégio mínimo, gestor de workloads e deploys, IDE inspirada nos padrões de interação do VS Code, integração Git e aplicativo de IA/MCP com aprovações e auditoria. A execução deve corrigir todos os pontos do relatório unificado e as lacunas L001-L032 identificadas nesta revisão, sem confundir planejamento com evidência de implementação.

O pacote deve produzir código, migrações, contratos, testes, documentação operacional, medições de desempenho, evidências de segurança, procedimentos de atualização/reversão e uma matriz de aceite. Planejamento não autoriza implantação em produção, uso de dados reais, rotação de credenciais, migração de banco externo ou ações destrutivas.

## Contexto de execução <!-- wop:section execution_context -->

O workspace inspecionado é `E:\Alkimim\Projetos\CodeVault\AetherDesk`. Ele contém backend Python/FastAPI em `apps/AetherDesk/`, frontend React/TypeScript em `web/`, artefatos de implantação em `deploy/`, documentação arquitetural em `docs/L3_Vulcan/` e um plano WOP anterior aceito, `a47c4d01-5e49-4b24-aaaf-2535f78447e0`, que entregou a primeira versão local. O relatório unificado fornecido em 23/11/2026 consolida dois pareceres sobre o AetherDesk e declara que suas medições e testes são reproduções dos relatos de origem, não uma nova execução; W001 deve revalidar fatos materiais no commit e ambiente identificados antes de qualquer otimização ou alegação de correção.

No AetherDesk atual, `web/src/shell.tsx` centraliza catálogo de apps, window manager, persistência e taskbar; `web/src/apps/files.tsx` combina Explorador e editor; o estado do desktop é JSON por conta; arquivos usam um processo `docker exec` por operação; runtime, terminal e monitor acessam o daemon Docker pelo processo ASGI. O contrato público v1 em `docs/L3_Vulcan/contracts-v1.md` está congelado. A arquitetura existente já define identidade derivada da sessão, isolamento por conta, permissões por capacidade e a intenção de um broker restrito, mas essa fronteira ainda não está separada no processo de execução.

## Fatos confirmados <!-- wop:section confirmed_facts -->

- F001: O plano anterior do AetherDesk está registrado como aceito e executado; este pacote é evolução relacionada, não reescrita retroativa desse histórico. Fonte: índice WOP local, 22/11/2026.
- F002: O TypeScript atual passou em `pnpm exec tsc --noEmit` e nove testes unitários de identidade, administração e monitor passaram em 22/11/2026; não foram encontrados testes frontend em `web/`.
- F003: O relatório unificado é fonte secundária: ele preserva resultados relatados por A1/A2, mas não constitui nova execução nem substitui baseline reproduzível no commit atual.
- F004: A lista de apps, o estado de janelas e a renderização do desktop estão concentrados em `web/src/shell.tsx`; apps são identificados por uma união estática de tipos.
- F005: Atualizações de posição e tamanho chamam a mesma função que eleva `z-index`; o backend rejeita coordenadas ou `z` absolutos acima de 10.000.
- F006: O Explorador consulta o diretório a cada 2,5 segundos, e cada operação de arquivos inicia `docker exec` com um agente Python.
- F007: `DockerEnvironmentBroker` usa o CLI Docker; terminal e monitor usam Docker SDK no mesmo serviço ASGI. A separação de broker descrita na arquitetura ainda não existe como processo de privilégio mínimo.
- F008: O runtime pessoal atual inicia com `--network none`; Git remoto, registries, CLIs de IA, provedores de IA e gerenciadores de pacotes não funcionarão sem política de saída controlada.
- F009: O contrato v1 exige compatibilidade ou versão nova para mudanças incompatíveis; desktop, workloads, Git e IA exigirão migrações e contratos explícitos.
- F010: Nenhum arquivo de aplicação foi modificado durante a análise ou esta revisão; somente o pacote WOP é atualizado.
- F011: A visibilidade do app Administração no shell atual é derivada de `role === 'admin'`, enquanto o backend permite capacidades efetivas com overrides; UI e autorização podem divergir até existir catálogo filtrado por capacidades.
- F012: `AdministrationService` cria `desktop_states` e `backup_settings` em runtime no mesmo SQLite de identidade, fora da cadeia de migrações versionadas da identidade.
- F013: O agendador de backup é uma thread iniciada no lifespan do processo ASGI; múltiplos workers podem executar schedulers concorrentes sem lease ou eleição explícita.
- F014: O estado do desktop não possui revisão persistida ou `updated_at`; o cliente faz upsert completo e pode perder atualização concorrente.

## Escopo <!-- wop:section scope -->

### Incluído

- Revalidação do relatório unificado contra o commit, ambiente e contratos atuais, com enumeração e rastreabilidade das lacunas L001-L032.
- Correções P0 do window manager, persistência, responsividade, relógio, temas, tratamento de sessão e infraestrutura de testes frontend.
- App Registry, menu Iniciar, menus de contexto, ícones SVG, wallpapers, grid responsivo, personalização e barra de tarefas.
- Extração do acesso Docker para um broker restrito e auditável, com política de rede, secrets e compatibilidade com os ambientes pessoais existentes.
- Domínio de workloads/deploys com ownership, jobs, build, start/stop/restart, logs, métricas, health, rollback e remoção segura.
- IDE dedicada com árvore de arquivos, Monaco, painéis, terminais, Git e deploy integrado.
- Aplicativo de IA com provedores, cofre de segredos, chat, MCP, ferramentas autorizadas, aprovações, auditoria e limites.
- Migrações, compatibilidade de API, observabilidade, CI, segurança de supply chain, testes, desempenho, recuperação e documentação operacional.

### Excluído

- Implantação em produção, migração de dados reais, alteração de DNS público, emissão de certificado público ou rotação de segredos reais sem autorização posterior.
- Kubernetes, cluster multi-host, Compose arbitrário, acesso privilegiado, GPU, marketplace de extensões VS Code e compatibilidade binária com extensões VS Code.
- Controle do host físico pelo menu Iniciar; “parar ambiente” afeta somente recursos do usuário no AetherDesk.
- Garantia de que uma CLI de IA arbitrária no terminal respeite aprovações do aplicativo; isso só é garantido quando a CLI usa o proxy/MCP governado do AetherDesk.
- Paridade total com VS Code, marketplace de extensões, execução irrestrita de Docker Compose e suporte multi-host; essas frentes exigem decisão e plano posterior.

## Partes interessadas e autoridade <!-- wop:section stakeholders -->

| Papel | Responsabilidade | Limite de decisão |
|---|---|---|
| Responsável pelo produto | Decide sequência, política de rede, privacidade administrativa, quotas e autorização de produção | Aprova mudanças materiais de escopo e implantação real |
| Implementação AetherDesk | Implementa código, migrações, testes e documentação neste workspace | Não acessa produção nem repositórios externos sem autorização |
| Operação/segurança | Aprova fronteira Docker, secrets, egress, backup, reversão e testes hostis | Não amplia acesso de administrador a dados privados sem decisão explícita |
| Administrador AetherDesk | Gerencia contas e workloads conforme capacidades | Não recebe automaticamente acesso a chats, secrets, arquivos ou terminais privados |
| Membro | Usa desktop, IDE, Git, workloads e IA dentro das próprias permissões | Não escolhe ownership pelo cliente nem manipula recursos de terceiros |

## Requisitos <!-- wop:section requirements -->

- R001: Revalidar o relatório unificado no commit e ambiente identificados, reconciliar o histórico WOP e produzir baseline funcional, de contrato, segurança, acessibilidade e desempenho antes de otimizar.
- R002: Resolver ou bloquear explicitamente as decisões de sequência, editor, permissões, administração, deploy, rede, secrets, tools, quotas, Docker, backup e contratos antes dos respectivos consumidores.
- R003: Corrigir o window manager P0: foco/z-index, drag/resize, limites, reflow, relógio, tema, responsividade e persistência concorrente/versionada.
- R004: Unificar cliente HTTP e tratamento de sessão/erros/offline; introduzir testes frontend, lint, acessibilidade, E2E e isolamento de falhas por app.
- R005: Implementar App Registry, menu Iniciar, menus de contexto, ícones, taskbar, atalhos, Command Palette e personalização acessível.
- R006: Permitir escolher, ordenar e posicionar apps por grade lógica; reflow deve manter todos os atalhos e janelas acessíveis sob zoom e resolução suportados.
- R007: Permitir background sólido, gradiente, galeria e upload seguro com quota, thumbnail, modos de ajuste, limpeza e CSP.
- R008: Remover acesso Docker irrestrito do serviço web e usar broker de privilégio mínimo com allowlist, autenticação, auditoria, quotas e política de rede.
- R009: Implementar workloads/deploys com ownership server-side, capacidades separadas, jobs idempotentes, build seguro, health, logs, métricas, rollback, proxy de portas, secrets e recuperação.
- R010: Implementar IDE dedicada com árvore, Monaco, tabs, busca, painéis redimensionáveis, terminal direito/inferior, sessões persistentes, status bar e deploy simplificado.
- R011: Implementar Git com status, diff, stage, commit, branch, pull/push e histórico, protegendo credenciais, host keys, hooks, conflitos e operações destrutivas.
- R012: Definir suporte limitado e verificável a LSP/diagnósticos/formatters sem prometer compatibilidade integral com extensões VS Code.
- R013: Implementar IA/MCP com provedores, secrets criptografados, chat streaming, ferramentas tipadas, permissões, approvals vinculados à ação, auditoria, quotas, privacidade e proteção contra prompt injection.
- R014: Manter explícito que CLIs de IA arbitrárias fora do MCP governado dependem de isolamento de runtime, filesystem, egress e secrets.
- R015: Substituir polling e processos por operação onde o baseline justificar; aplicar cache, eventos, paginação, cancelamento e jobs assíncronos com budgets medidos.
- R016: Versionar dados e contratos, proteger compatibilidade v1, definir `/api/v2` quando necessário e provar upgrade/rollback/restore.
- R017: Implementar observabilidade com logs redigidos, correlação, métricas, tracing apropriado, SLOs e alertas para broker, jobs, deploys, Git e IA.
- R018: Aplicar least privilege, supply-chain security, isolamento multiusuário, rate limits, idempotência e testes hostis somente em ambientes descartáveis autorizados.
- R019: Entregar CI/release reproduzível, documentação de operação, migração, backup, recuperação e aceite em ambiente identificado, sem confundir WSL com produção.
- R020: Fixar privacidade e autoridade administrativa: controle de ciclo de vida não implica acesso a conteúdo privado sem capacidade e decisão explícitas.
- R021: Fazer catálogo, menus, atalhos e rotas frontend refletirem capacidades efetivas e mudanças de permissão em tempo real, mantendo autorização obrigatória no servidor.
- R022: Executar scheduler, outbox e jobs com lease/fencing, idempotência, recuperação e graceful shutdown, sem duplicação em múltiplos processos.
- R023: Definir lifecycle, retenção, exportação, exclusão, backup e restore para todos os dados novos e existentes, com RPO/RTO e criptografia aprovados.
- R024: Aplicar segurança web global e contratos de conteúdo para wallpapers, arquivos e Monaco, incluindo CSP/headers, metadata stripping, limites, encoding, crash recovery e UI de aprovação confiável.
- R025: Implementar lifecycle da master key e secrets e trust registry para providers/MCP, com rotação, revogação, versionamento e falha segura.
- R026: Isolar proxy, rede, portas, build cache, imagens e logs por owner, bloqueando SSRF, metadata access, DNS rebinding e vazamento entre tenants.
- R027: Usar feature flags, kill switches, safe mode e compatibilidade web/API/broker para rollout e rollback controlados.
- R028: Verificar licença, atribuição, marca e proveniência de dependências, assets, imagens e integrações antes do release.

## Restrições <!-- wop:section constraints -->

- C001: Não modificar código durante W001; produzir apenas inventário, decisões, contratos, baselines e plano de migração.
- C002: Não executar implantação, migração de dados reais, build hostil, rotação de key ou alteração de infraestrutura externa durante planejamento; execução posterior usa ambientes explicitamente autorizados.
- C003: Ownership vem sempre do `ActorContext`; IDs enviados pelo cliente nunca definem proprietário.
- C004: Serviço web, ambientes pessoais e workloads de usuário nunca recebem o socket Docker.
- C005: `--privileged`, host PID/network, devices, mounts arbitrários e capabilities extras são negados por padrão.
- C006: Ações destrutivas, administrativas, de deploy e aprovação são auditadas e idempotentes; conteúdo privado e secrets são redigidos.
- C007: Mudança incompatível não altera silenciosamente `/api/v1`; usa compatibilidade aditiva ou `/api/v2`.
- C008: Testes destrutivos, fuzzing de container e restore usam recursos descartáveis nomeados; produção exige autorização separada.
- C009: Nenhum critério pode ser considerado aprovado por implementação simulada quando depende de Linux, Docker, navegador ou provedor externo real.
- C010: Resultados herdados do relatório são hipóteses de baseline até serem reproduzidos no commit e ambiente registrados.
- C011: Feature flag ou kill switch nunca substitui autorização, migração, isolamento ou teste; o estado seguro padrão mantém egress, deploy por Dockerfile e providers de IA desabilitados.

## Decisões <!-- wop:section decisions -->

- D001: Atualizar o plano de evolução existente `c1cf6012-e0a4-4f5a-a7fc-52a6ff0363fd`, removendo escopo alheio ao relatório atual, preservando o histórico Vulcan aceito e evitando pacote duplicado.
- D002: Estabilizar desktop, HTTP/dados/workers e broker antes dos novos domínios; na onda seguinte, shell, workloads, workspace/Git e IA/MCP podem evoluir em módulos isolados, e as UIs dependentes só começam após seus contratos passarem.
- D003: Usar arquitetura de app registry e módulos de domínio; arquivos compartilhados de composição, capability catalog, migração global e registro frontend são integrados somente em W005.
- D004: Broker é infraestrutura central para ambiente pessoal, arquivos, terminais, workloads, Git e tools de IA; não é detalhe interno do app Containers.
- D005: Interface inspirada no VS Code significa padrões de layout e interação, não clone visual nem compatibilidade completa de extensões.
- D006: O padrão de privacidade administrativa é “controlar sem ler conteúdo”; ampliar acesso exige capacidade distinta, aviso ao usuário e decisão registrada.
- D007: O padrão de rede é deny-by-default com egress mediado; exceções são por classe de destino e workload, observáveis e revogáveis.
- D008: O App Registry usa capacidades efetivas retornadas pelo servidor; papel é informação administrativa, não critério suficiente para visibilidade ou autorização.
- D009: O MVP de deploy começa com templates/imagens aprovadas. Dockerfile de usuário só é habilitado por flag após BuildKit rootless/isolado, testes hostis e decisão registrada.
- D010: A IDE principal é workbench próprio sobre Monaco/xterm; `code-server`/`openvscode-server` permanece alternativa futura sujeita a licença, isolamento e integração.
- D011: Workers usam leases persistentes com fencing e operações idempotentes; uma thread por processo sem coordenação não é arquitetura aceita.
- D012: Em 23/11/2026, o responsável dispensou explicitamente a prova das unidades systemd em host Linux independente para seguir o plano sem host/VM disponível. Para o portão W002, aceitar a fixture Docker Linux descartável como evidência da fronteira web/broker, mantendo a lacuna systemd registrada. Esta dispensa não autoriza produção nem substitui os demais critérios de segurança, migração, regressão ou rollback.
- D013: Em 23/11/2026, o responsável escolheu o navegador integrado do Codex como ambiente interativo da execução, sem novas janelas no Brave pessoal. Para o aceite técnico local de I004/W002, aceitar a matriz Playwright isolada nos motores Chromium, Firefox e WebKit com viewports CSS equivalentes aos zooms de I002, mais inspeção visual/teclado no navegador integrado. Esses testes são conclusivos para reflow, alcance dos controles e fluxos exercitados no ambiente registrado; não são prova universal de zoom nativo, duplicação pelo menu do navegador, leitor de tela ou crash de processo nos motores não ensaiados. A prova nativa de zoom já obtida no Brave pode permanecer como evidência histórica, mas nenhum teste adicional deve abrir o navegador pessoal. As lacunas nativas ficam explicitamente para I014/W006 antes do aceite final, com ambiente próprio ou decisão posterior de waiver; não são apresentadas como verificadas em W002.

## Premissas <!-- wop:section assumptions -->

- A001: O AetherDesk continua destinado inicialmente a servidor Linux único; WSL/local é homologação, não prova de produção. Validar novamente no portão W006.
- A002: O contrato v1 permanece atendido por compatibilidade aditiva; incompatibilidades usam `/api/v2` ou migração explícita. Validar em W001 e W005.
- A003: O perfil provisório existente — 20 contas, 8 usuários simultâneos, até 4 PTYs por usuário, 10.000 arquivos e 2 GiB por conta — é ponto inicial de medição, não resultado aceito. W001 confirma ou revisa o orçamento.
- A004: Ícones serão SVG tree-shakable; o desenho seguirá padrões familiares de IDE sem copiar marcas ou assets proprietários.
- A005: SQLite permanece adequado ao servidor único até a medição demonstrar o contrário; novas tabelas usam migrações versionadas e rollback/forward recovery definido.

## Incógnitas <!-- wop:section unknowns -->

- U001: Quais fatos, medições e hipóteses do relatório permanecem válidos no commit atual? I001 reexecuta verificações seguras, classifica divergências e bloqueia otimizações sem baseline.
- U002: Qual política de egress é aceita para Git, registries, pacotes e IA? I002 propõe alternativas e registra decisão antes de liberar workloads, Git e IA.
- U003: Administradores podem ver logs, executar comandos ou acessar chats/secrets de workloads alheios, ou apenas controlar ciclo de vida? I002 exige decisão de privacidade; o padrão é controle sem conteúdo privado.
- U004: O daemon dedicado será Docker rootless, daemon segregado com proxy de autorização ou broker diante do daemon atual? I002 mede compatibilidade e congela a escolha; acesso irrestrito pelo ASGI é proibido após W002.
- U005: Quais provedores de IA, políticas de retenção e limites de custo serão permitidos? I002 define contrato mínimo e I009 mantém provedores desabilitados até configuração explícita.
- U006: O host Linux independente, registry e domínio/proxy de aplicações ainda não estão identificados. W006 pode aceitar homologação local, mas não produção.
- U007: As capacidades de containers serão agregadas ou separadas por leitura, build, lifecycle, logs, exec, remoção e administração? I002 congela a matriz antes de I007/I011.
- U008: O MVP de deploy aceitará somente templates/imagens aprovadas ou Dockerfile de usuário em BuildKit rootless isolado? O padrão seguro é templates; ampliar exige gate próprio.
- U009: Quais RPO, RTO, criptografia, destino off-host e retenção valem para banco, volumes, workloads, wallpapers, secrets e conversas? I002 registra a política antes de W005.
- U010: Quais feature flags e kill switches controlam broker, egress, deploy, Git remoto e IA durante rollout? I002 define nomes, owner e estado seguro.

## Riscos <!-- wop:section risks -->

| Risco | Probabilidade | Impacto | Prevenção | Detecção | Responsável |
|---|---|---|---|---|---|
| Otimizar com baseline herdado ou obsoleto | Alta | Alto | Reexecução identificada em W001 | Divergência de commit, ambiente, dataset ou percentis | Responsável técnico |
| Escape ou controle do daemon Docker | Média | Crítico | Broker isolado, daemon/rootless, allowlist e ausência de socket em apps | Testes hostis e inspeção de processo/mounts | Segurança/runtime |
| Perda de dados em migração ou deploy | Média | Alto | Migrações reversíveis/forward recovery, backup e jobs idempotentes | Restore e rollback ensaiados | Dados/operação |
| Exfiltração por egress, Git ou IA | Média | Crítico | Proxy deny-by-default, secret scoping, redaction e allowlists | Logs de egress e canários sem segredo real | Segurança |
| Prompt injection aciona tool perigosa | Alta | Alto | Separar dados/instruções, capability check e aprovação vinculada a argumentos | Testes adversariais de MCP | IA/segurança |
| Build malicioso afeta host | Média | Crítico | Build isolado, sem mounts/privilege, quota, timeout, scan e provenance | Cenários de Dockerfile hostil | Workloads |
| Admin ganha acesso implícito a conteúdo | Média | Alto | Capacidades separadas e padrão control-only | Testes de autorização/IDOR e auditoria | Identidade |
| Reflow perde ícones ou janelas | Média | Médio | Grade lógica, collision resolver e matriz de viewport | E2E em zoom/resoluções suportadas | Frontend |
| Performance degrada com watchers/jobs | Média | Alto | Baseline, budgets, backpressure e caches limitados | Carga com percentis e recursos | Performance |
| Frontend/API/broker incompatíveis em rollout | Média | Alto | Versionamento, compatibility window e rollback | Testes N/N-1 e smoke pós-upgrade | Release |
| Scheduler ou worker executa job duplicado | Média | Alto | Lease, fencing, idempotência e reconciliação | Jobs concorrentes com mesmo operation_id | Plataforma |
| UI exibe app/ação por role após revogação | Média | Alto | Catálogo por capacidades e eventos de permissão | Testes role/override/revogação | Identidade/frontend |
| Cache, log ou imagem cruza tenants | Baixa/média | Crítico | Namespace por owner, quotas, GC e testes canário | Hash/label/owner divergente | Workloads/segurança |
| Master key indisponível ou rotacionada incorretamente | Baixa/média | Crítico | Custódia, versionamento, backup e ensaio de rotação | Falha de decrypt/readiness e restore | Segurança/operação |

## Ambientes e operação <!-- wop:section operations -->

Desenvolvimento usa o workspace local, fixtures e bancos descartáveis. Testes interativos de UI usam o navegador integrado do Codex em aba temporária; a matriz reproduzível usa processos Playwright isolados, nunca janelas pessoais do Brave, conforme D013. Testes Docker usam nomes, redes, volumes e daemons identificados e removíveis; nunca reutilizam containers pessoais ou dados reais. A prova W002 das unidades systemd em host independente foi dispensada pela decisão D012; a fixture Docker Linux deve registrar daemon, isolamento, montagem, grupos, commit e limpeza. Homologação posterior usa WSL 2 dedicada ou host Linux de teste equivalente quando disponível, registrando kernel, Docker/daemon, proxy, browser, resolução, zoom e commit; a ausência desse ambiente fica explícita no aceite técnico local. Produção permanece bloqueada até host, backup, secrets, domínio, registry, capacidade, rollback e janela de mudança serem aprovados.

O perfil provisório AetherDesk mede 20 contas, 8 usuários concorrentes, 4 PTYs por usuário, 10.000 arquivos e 2 GiB por conta. Metas iniciais herdadas: login p95 menor que 1 s, listagem de 100 itens p95 menor que 500 ms, abertura de arquivo de 1 MiB p95 menor que 1 s, eco PTY p95 menor que 150 ms e coleta de métricas menor que 2% de CPU do host. W001 deve confirmar dataset, warm/cold state, amostras e budgets adicionais de build, deploy, Git e chat antes de torná-los gates.

## Contratos globais <!-- wop:section global_contracts -->

- GC001: Identidade e ownership são derivados da sessão; toda API, WebSocket, job e tool revalida conta, sessão, capacidade e recurso.
- GC002: O broker recebe operações tipadas e allowlisted, não comandos Docker arbitrários; registra ator, operação, recurso, resultado e correlação sem conteúdo privado.
- GC003: Cada mutação remota ou longa usa `operation_id`/idempotency key, estado observável e resultado terminal; retry não duplica deploy, container, aprovação ou secret.
- GC004: Secrets são criptografados fora dos volumes de usuário, nunca retornam completos, são injetados por referência e redigidos de logs, erros e auditoria.
- GC005: Workloads internos AetherDesk não aparecem no catálogo do usuário. Banco é autoridade de ownership; labels Docker são defesa adicional.
- GC006: Estado de desktop v2 usa `schemaVersion`, revisão/ETag, posições lógicas e migração; estado transitório de drag/resize não é persistido a cada evento.
- GC007: Contratos v1 congelados permanecem testados. Novos contratos incompatíveis usam `/api/v2` e uma janela N/N-1 definida em W001.
- GC008: Cada módulo novo exporta interface e testes próprios sem editar `launch.py`, capability catalog global, registro de apps ou migração agregada antes de W005.
- GC009: Tickets de aprovação IA vinculam ator, sessão, tool, hash dos argumentos, risco, TTL e nonce de uso único; alteração de argumentos invalida aprovação.
- GC010: Admin controla workloads alheios apenas pelas capacidades concedidas; logs, exec, arquivos, chats e secrets exigem capacidades separadas e política explícita.
- GC011: App Registry, menu, context menu e rotas frontend derivam visibilidade de capacidades efetivas e reagem a revogação; ocultação visual nunca substitui `require` server-side.
- GC012: Scheduler, outbox e workers adquirem lease com fencing, heartbeat e recuperação; `operation_id` impede efeito duplicado após timeout, retry, crash ou múltiplos processos.
- GC013: Cada dado possui owner, classificação, retenção, export/delete, backup/restore e descarte verificável; tombstone de conta não apaga conteúdo sem política aprovada.
- GC014: Respostas web aplicam headers/CSP e conteúdo enviado passa por validação, limites e metadata stripping; approval é chrome confiável, não conteúdo controlado pelo modelo.
- GC015: Feature flags e kill switches têm owner, default seguro, telemetria, prazo de remoção e teste de rollback; versões web/API/broker negociam compatibilidade.
- GC016: Master key e secrets possuem versão, escopo, rotação, revogação, backup e restore; providers e servidores MCP externos exigem registro de confiança e schema versionado.
- GC017: Proxy, DNS, portas, networks, build cache, imagens e logs são namespaces por owner; endpoints internos/metadata e rebinding são bloqueados por política e testes.

## Sequência das ondas <!-- wop:section wave_sequence -->

1. W001 — Revalidar o diagnóstico, medir baseline e congelar contratos.
2. W002 — Estabilizar HTTP/dados/desktop/workers e extrair a fronteira Docker.
3. W003 — Construir shell e serviços independentes de workloads, workspace/Git e IA/MCP.
4. W004 — Construir IDE, app Containers e app IA sobre contratos aceitos.
5. W005 — Integrar módulos, migrações, compatibilidade, observabilidade e release.
6. W006 — Endurecer, medir, ensaiar recuperação e aceitar a evolução.

## Mapa de dependências <!-- wop:section dependency_map -->

| De | Para | Tipo | Contrato ou saída | Portão |
|---|---|---|---|---|
| W001 | W002 | Decisão/contrato | Baselines, catálogo L001–L032, broker/desktop/worker/key/migration contracts | I001/I002 aceitos |
| W002 | W003 | Saída/segurança | Desktop foundation e broker SDK | Regressão e boundary tests |
| W003 | W004 | Contrato | Shell slots e clients workloads/Git/IA | Módulos isolados aceitos |
| W004 | W005 | Integração | Descriptors, bundles e client adapters | UIs isoladas aceitas |
| W005 | W006 | Release | Candidate, migrations, observabilidade e rollback | Gate de integração passa |

## Rastreabilidade dos requisitos <!-- wop:section requirement_traceability -->

| Requisito | Fonte | Itens | Saídas | Verificação | Impacto final |
|---|---|---|---|---|---|
| R001 | Relatório unificado, F001–F014 e L001–L002 | I001, I002, I014 | Baseline e reconciliação WOP | Manifesto/commit/testes/medições | Execução parte de fatos atuais |
| R002 | Seção 12 do relatório e U001–U010 | I001, I002, I014 | ADRs e decision log | Owners, alternativas, decisão/bloqueio | Consumidores não assumem decisões abertas |
| R003 | Relatório §§2 e 5.4 | I002, I004, I014 | Window manager/desktop v2 | Stress drag, viewport, ETag | Desktop estável |
| R004 | Relatório §§2–4, 9 e L008 | I002, I004, I013, I014 | Client/test harness/errors | CI, offline/session/E2E | Resiliência frontend |
| R005 | Relatório §§4–5 | I006, I013, I014 | Shell/App Registry | Acessibilidade/E2E | Navegação personalizável |
| R006 | Relatório §5.4 | I004, I006, I014 | Grid/reflow | Matriz zoom/resolução | Itens sempre acessíveis |
| R007 | Relatório §5.5 e L018 | I006, I013, I014 | Wallpaper service | Upload/quota/CSP/cleanup | Personalização segura |
| R008 | Relatório §§7–9 e risco central | I002, I005, I013, I014 | Broker | Inspeção mounts/abuse | Fronteira Docker segura |
| R009 | Relatório §7 e L009–L010 | I007, I011, I013, I014 | Workloads/deploy | Ownership/build/rollback | Deploy seguro |
| R010 | Relatório §6 | I010, I013, I014 | IDE | E2E editor/terminal/deploy | Desenvolvimento intuitivo |
| R011 | Relatório §6.4 e L012 | I008, I010, I013, I014 | Git service/UI | Local/remoto/conflict/security | Git protegido |
| R012 | L013 | I002, I008, I010, I014 | LSP boundary | Sandbox/language tests | Escopo IDE honesto |
| R013 | Relatório §8 e L015 | I009, I012, I013, I014 | AI/MCP/approvals | Adversarial/replay/privacy | IA governada |
| R014 | Ressalva CLI IA | I002, I005, I009, I010, I012, I014 | Egress/MCP disclosure | CLI governada versus externa | Limite de segurança explícito |
| R015 | Relatório §3 e L005/L014 | I002, I005, I008, I013, I014 | Events/cache/jobs | Benchmarks/load | Performance mensurada |
| R016 | Relatório §9.2 e L004 | I002, I004, I013, I014 | API/schema migrations | N/N-1/rollback/restore | Compatibilidade |
| R017 | L016 | I002, I007–I009, I013, I014 | Observabilidade | Logs/metrics/traces/alerts | Operação diagnosticável |
| R018 | Threat model e L010/L019 | I002, I003, I005, I007–I009, I013, I014 | Security controls | Hostile/fuzz/idempotency tests | Hardening |
| R019 | Seção 9.3 e L017 | I002, I003, I013, I014 | CI/release/runbooks | Pipeline/recovery/homologação | Entrega operável |
| R020 | L020 | I002, I007, I009, I011, I012, I014 | Privacy/capabilities | Admin negative tests | Conteúdo privado protegido |
| R021 | F011/L021 | I002, I003, I006, I013, I014 | Capability-aware catalog/events | Role/override/revocation E2E | UI e servidor coerentes |
| R022 | F013/L022/L019 | I002, I003, I007, I009, I013, I014 | Lease/fencing/job runtime | Multi-process crash/retry tests | Jobs sem duplicação |
| R023 | L023/L030 | I002, I003, I006–I009, I013, I014 | Lifecycle/retention/backup policy | Delete/export/RPO/RTO/restore | Dados governados e recuperáveis |
| R024 | L018/L025/L026 | I002, I003, I004, I006, I008, I010, I013, I014 | Web/content/editor security | Headers/CSP/file/recovery tests | Superfície web e dados seguros |
| R025 | L024/L029 | I002, I003, I009, I012, I013, I014 | Key lifecycle/MCP trust registry | Rotate/revoke/schema drift tests | Secrets e tools confiáveis |
| R026 | L027/L028 | I002, I005, I007, I011, I013, I014 | Proxy/cache tenant isolation | SSRF/rebinding/cross-owner tests | Rede e artifacts isolados |
| R027 | L017/L031 | I002, I003, I013, I014 | Flags/kill switches/version matrix | Safe-mode/N-N-1/rollback | Rollout controlado |
| R028 | L010/L032 | I002, I006–I009, I013, I014 | License/provenance inventory | Policy scan/review | Release legal e rastreável |

## Estratégia de verificação <!-- wop:section verification_strategy -->

Usar static/type/lint para invariantes de código; unit/property para grid, estado, policy, lease e aprovação; integration para SQLite, broker, filesystem, Git, jobs, key store, providers e migrations; contract para API v1/v2, IPC, clients, MCP schemas e descriptors; component/accessibility/visual regression para cada app; E2E para jornadas multiusuário; security/fuzz para trust boundaries; performance/load/soak para budgets; e restore/rollback/key rotation para operação. Fixtures isolam conta, workspace, volume, rede, cache, registry, provider, browser, clock e randomness. Em W002, usar aba temporária do navegador integrado para inspeção visual/teclado e Playwright isolado para os três motores/viewport equivalente; não tocar no Brave pessoal. Evidência registra commit, ambiente, comando/procedimento, dataset, resultado e limitações, distinguindo viewport CSS de zoom nativo e varredura axe de leitor de tela.

## Reversão e recuperação <!-- wop:section rollback_recovery -->

Antes de cada migração/integration gate, gerar backup criptografado e verificado de banco/configuração/volumes de fixture e manifesto de versões, incluindo procedimento separado para master key. Frontend pode reverter para bundle N-1 enquanto API mantém janela compatível. Broker usa rollout com health, feature flag/kill switch e adapter anterior disponível. Workload deploy preserva release anterior até health passar. Migrações têm down migration segura ou forward recovery documentado; secrets nunca entram em backup em claro. Se isolamento, migration, key rotation, approval, lease ou restore falhar, acionar safe mode, parar avanço, preservar logs redigidos, restaurar candidate/dados anteriores, verificar duas contas e reexecutar o gate. Produção terá ensaio e autorização próprios.

## Aceite final <!-- wop:section final_acceptance -->

- W001–W006 passaram em ordem e todos os itens têm evidência real no commit e ambientes identificados.
- R001–R028 e L001–L032 estão satisfeitos ou possuem rejeição explícita com consequência e decisão do responsável.
- AetherDesk demonstra desktop responsivo/personalizável, broker seguro, workloads/deploy, IDE/Git e IA/MCP com isolamento, privacidade, observabilidade, desempenho e recuperação aceitos.
- Release, migrations, CI, SBOM, runbooks, security/performance/accessibility/restore reports e riscos residuais estão entregues.
- Aceite técnico não autoriza produção; host real, domínio, registry, secrets, backup, capacidade e janela de mudança exigem decisão posterior identificada.

## Protocolo de execução <!-- wop:section execution_protocol -->

Identifique o pacote e leia `README.md` e cada prompt de onda referenciado. Execute as ondas em ordem estrita; bloqueie avanço até todos os itens da onda concluírem, serem aceitos individualmente, integrados quando necessário e o portão passar. Verifique outputs e evidências predecessoras, integre resultados, registre transições e avalie cada gate e o aceite final. Paralelize somente itens cuja independência esteja comprovada na onda. Pare diante de efeitos externos não autorizados, falha crítica, blocker, mudança material de escopo ou divergência entre README, prompts, índice e ambiente.

## Lacunas adicionais do relatório unificado <!-- wop:section omitted_findings -->

1. L001: O relatório reproduz diagnósticos e medições de A1/A2, mas não revalida commit, configuração, ambiente, dataset ou resultado; implementação precisa começar por baseline independente.
2. L002: Não reconcilia o plano WOP anterior aceito, o plano de evolução já registrado, o README que ainda alerta contra produção e as provas exclusivas de um host Linux real.
3. L003: Não exige auditoria de aderência entre implementação e `contracts-v1.md`, inclusive envelope de erro, revisões e estados de ambiente.
4. L004: Não define estratégia de migração, rollback e compatibilidade para desktop v2, workloads, Git, secrets, conversas e aprovações.
5. L005: Lista otimizações sem baseline reproduzível, percentis, dataset, orçamento e ambiente de medição.
6. L006: Não define matriz de navegadores, resolução, zoom, densidade, touch e viewport para provar o reflow do desktop.
7. L007: Acessibilidade não cobre foco entre janelas, focus trap em menus/diálogos, leitor de tela, `prefers-reduced-motion`, contraste e navegação integral por teclado.
8. L008: Não inclui Error Boundaries, recuperação de falhas por app, cancelamento de requests, estado offline, retry idempotente e concorrência entre múltiplas abas/dispositivos.
9. L009: O gestor de containers não detalha health checks, estado desejado/observado, rollback de release, retenção de imagens/logs, garbage collection e reconciliação após reinício.
10. L010: Não cobre registry, pinagem por digest, SBOM, proveniência, scan de imagem/dependência e políticas para Dockerfiles maliciosos.
11. L011: Não define proxy de egress, DNS, allowlist, rate limit e observabilidade para Git, registries, pacotes e provedores de IA.
12. L012: Git precisa de política para SSH host keys, tokens/chaves, redaction, conflitos, operações destrutivas, assinatura e proteção contra comandos/hook não confiáveis.
13. L013: A IDE não especifica limite de suporte para LSP, diagnósticos, formatters, code actions e extensões; prometer paridade total com VS Code seria incorreto.
14. L014: Não define watcher/indexação/busca global, limites de arquivos, backpressure do terminal, backlog de reconexão e quotas de PTY.
15. L015: IA/MCP não detalha retenção e exportação de conversas, divulgação de dados ao provedor, ticket de aprovação vinculado a argumentos/TTL/nonce e revogação durante streaming.
16. L016: Não estabelece logs estruturados, correlação de jobs, métricas, tracing, SLOs, alertas e redaction para novos domínios.
17. L017: Não define gates de CI, artefatos de release, upgrade/rollback de banco e compatibilidade entre versão web, API e broker.
18. L018: Wallpapers precisam de quota, deduplicação, thumbnail, remoção de órfãos, CSP e validação de conteúdo, além de MIME e dimensões.
19. L019: Não define idempotência e controle de concorrência para deploy, preferências, aprovações e ações repetidas após perda de conexão.
20. L020: Não fixa a fronteira de privacidade do administrador sobre logs, exec, arquivos, chats e secrets de outros usuários.
21. L021: Não explicita que a UI atual decide Administração por `role`, enquanto autorização real usa capacidades efetivas e overrides; catálogo, menus e rotas precisam refletir capacidades sem substituir checagem server-side.
22. L022: Não define eleição, lease, fencing e shutdown para scheduler de backup, outbox e futuros workers em implantação com múltiplos processos; jobs podem duplicar ou ficar órfãos.
23. L023: Não fecha lifecycle de dados após desativação/exclusão de conta para desktop state, wallpapers, workloads, volumes, imagens, logs, build cache, tokens, secrets, conversas e auditoria.
24. L024: “Secrets criptografados” não define geração, custódia, rotação, versionamento, backup/restore e indisponibilidade da master key, nem separação entre secrets de usuário, sistema e workload.
25. L025: Não define política web global de CSP, `frame-ancestors`, headers, origem, sanitização, Trusted Types quando aplicável e UI confiável para impedir spoofing de approvals por conteúdo gerado.
26. L026: O editor não possui contrato explícito para arquivo binário, encoding, line endings, arquivo grande, autosave, `beforeunload`, recuperação após crash/reload e limite de modelos Monaco.
27. L027: O proxy de workloads não trata explicitamente SSRF, metadata endpoints, DNS rebinding, colisão/ownership de portas, WebSocket, TLS, limites de corpo/tempo e isolamento de rotas.
28. L028: Build cache, layers, imagens, registry cache e logs podem vazar dados entre contas se não houver namespace, quota, retenção e garbage collection por owner.
29. L029: O MCP externo não possui trust registry, pinagem de servidor/versão, resolução de colisão de nomes de tools, política de schema change e distinção visual entre tools nativas e de terceiros.
30. L030: Backup não define RPO/RTO, criptografia, cópia off-host, teste periódico de restore, tratamento da master key nem execução única do scheduler.
31. L031: Não há estratégia de feature flags, rollout gradual, kill switches e safe mode para broker, egress, Git remoto, deploys e IA sob incompatibilidade ou incidente.
32. L032: Não há gate de licenças, atribuição e uso de marca para ícones, Monaco, bibliotecas, `code-server`/`openvscode-server`, imagens base e SDKs de provedores.
