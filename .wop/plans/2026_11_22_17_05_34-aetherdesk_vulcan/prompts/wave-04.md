---
artifact: wop-wave-prompt
plan_id: a47c4d01-5e49-4b24-aaaf-2535f78447e0
plan_version: 4
plan_title: "Implementar o AetherDesk com organização Vulcan"
wave_id: W004
authorized_items: I009
non_authorized_items: "I001,I002,I003,I004,I005,I006,I007,I008"
predecessor_waves: W003
blocked_successor_waves: none
language: pt-BR
source_readme: README.md
source_readme_sha256: b04889ec9885f3cea62a1ec0ee02f75fc1d25474707fae93187230f3dc448540
---

# Onda W004 — Integração e homologação

<!-- wop:prompt-section global_protocol -->
## Protocolo de execução <!-- wop:section execution_protocol -->

Identifique o pacote e leia `README.md` e todos os prompts de onda referenciados. Execute as ondas em ordem estrita; não avance antes de todos os itens da onda concluírem, serem aceitos individualmente, integrados quando necessário e de o portão passar. Integre resultados, registre evidências e transições de estado, bloqueie mudanças de escopo ou efeitos externos não autorizados e avalie o aceite final. Use somente o paralelismo cuja independência esteja demonstrada na onda correspondente.

<!-- wop:prompt-section execution_scope -->
<!-- wop:prompt-assigned-wave W004 -->
### Objetivo geral <!-- wop:field general_objective -->

Integrar o produto, validar segurança e recuperação e demonstrar instalação reproduzível na distribuição WSL 2 local, com evidência de aceite técnico e funcional desta versão.

### Requisitos atendidos <!-- wop:field requirements_addressed -->

- R001–R014.

### Instruções de execução da onda <!-- wop:field execution_instructions -->

Execute apenas I009 após verificar o portão W003. Provisione a distribuição WSL 2 descartável, integre todos os módulos, teste nela, registre resultados e avalie os critérios funcionais observáveis sem aguardar um host externo. Se a instalação exigir reinício do Windows, preserve estado e retome após o reinício; não declare prova não executada. Não trate produção como parte automaticamente autorizada desta onda.

### Justificativa de paralelismo <!-- wop:field parallelism_rationale -->

Item único: integração, segurança, instalação e recuperação compartilham composição, dados e ambiente de homologação; fragmentar criaria interferência.

### Limites de propriedade <!-- wop:field ownership_boundaries -->

I009 possui composição e infraestrutura comuns do AetherDesk e pode corrigir módulos com revisão dos respectivos contratos. Não edita Olympus nem executa implantação de produção sem autorização.

<!-- wop:prompt-assigned-item I009 -->
#### Item I009 — Produto integrado e operação

##### Objetivo <!-- wop:field objective -->

Produzir uma versão AetherDesk instalável e demonstrar os requisitos aceitos para esta versão na distribuição WSL 2 local.

##### Contexto <!-- wop:field context -->

Os contratos de W001 e módulos aceitos de W002/W003 são a base; testes locais dos módulos não provam isolamento ou recuperação do conjunto.

##### Entradas e pré-requisitos <!-- wop:field inputs_prerequisites -->

- Todos os exports, testes, políticas e decisões aceitos nos portões W001–W003; WSL 2 disponível no Windows, com distribuição descartável a provisionar em I009.

##### Escopo <!-- wop:field scope -->

- Compor backend/web/runtime, migrações e roteamento; instalar distribuição WSL 2 com systemd e registrar a origem do Docker; configurar HTTPS local e serviço; documentar operação; executar testes e2e, concorrência, segurança, carga, atualização, reversão e restauração com dados descartáveis; corrigir falhas.

##### Propriedade <!-- wop:field ownership -->

- Arquivos comuns e homologação; mudanças em módulos devem manter seus contratos e registrar revisão quando material.

##### Saídas <!-- wop:field outputs -->

- Aplicação instalável, runbooks, suíte e2e, relatório de segurança/desempenho WSL, matriz de aceite e pacote de evidências com lista explícita das provas reservadas ao servidor independente.

##### Restrições <!-- wop:field restrictions -->

- Nenhum teste destrutivo em dados reais; não transformar evidência WSL em aprovação do servidor independente; implantação real depende de autorização separada.

<!-- wop:prompt-section predecessor_verification -->
### Pré-requisitos <!-- wop:field prerequisites -->

W003 passou; verificar registros, testes e contratos dos quatro módulos, além de todas as decisões e evidências dos portões anteriores.

<!-- wop:prompt-predecessor W003 -->
## Onda W003 — Aplicativos e painéis

### Objetivo geral <!-- wop:field general_objective -->

Implementar os quatro módulos funcionais do desktop sobre fundações e contratos aceitos, com propriedade isolada por módulo.

### Critérios gerais de aceite <!-- wop:field general_acceptance_criteria -->

- Explorador/editor, terminais, monitor e administração passam contratos, fluxos positivos, erros e verificações negativas de permissão em fixtures independentes.
- Cada módulo exporta Boundary, casos de uso, ferramentas e componente web sem modificar a composição compartilhada; o portão integra os registros e confirma que os quatro podem abrir no shell.

### Portão de conclusão <!-- wop:field completion_gate -->

I005–I008 aceitos individualmente; integração de exports e rotas no portão passa; nenhuma leitura cruzada, sobrescrita silenciosa ou vazamento de métrica fica aberto. W004 só inicia após registro dessa evidência.

### Evidências exigidas <!-- wop:field evidence_requirements -->

- Suítes de contrato, integração e UI de cada módulo, cenários negativos, capturas de telas e relatório do registro integrado.

### Integração e passagem <!-- wop:field integration_handoff -->

Entregar módulos registrados, matriz de permissões implementada, contratos de erro/eventos e comandos de teste para a jornada completa de I009.

<!-- wop:prompt-predecessor-item I005 -->
#### Item I005 — Explorador e editor

##### Saídas <!-- wop:field outputs -->

- Boundary de arquivos, casos de uso, ferramenta de filesystem, Explorer, editor e testes.

##### Critérios de aceite <!-- wop:field acceptance_criteria -->

- Suíte cobre todas as operações de R005, `Ctrl+S`, abas, conflito externo, caminho relativo, symlink, tentativa de atravessar raiz, substituição explícita e arquivo criado por fixture Bash aparecendo no Explorer.

##### Evidência de verificação <!-- wop:field verification_evidence -->

- Testes de contrato/integração/UI, roteiro de concorrência e captura dos estados de conflito.

##### Requisitos de passagem <!-- wop:field handoff_requirements -->

- Exportar rotas, componente web, eventos e contratos de conflito para I009.

<!-- wop:prompt-predecessor-item I006 -->
#### Item I006 — Terminal Bash

##### Saídas <!-- wop:field outputs -->

- Serviço PTY, Boundary, cliente terminal e testes.

##### Critérios de aceite <!-- wop:field acceptance_criteria -->

- Duas sessões da mesma conta mantêm cwd/estado distintos e veem os mesmos arquivos; logout/revogação da sessão web mantêm PTYs e processos ativos para reconexão após novo login, enquanto parada de sessão os encerra; `Ctrl+C`, resize e fechamento explícito funcionam; outro usuário e permissão revogada não conseguem conectar ao PTY existente.

##### Evidência de verificação <!-- wop:field verification_evidence -->

- Testes PTY/WebSocket, cenário de revogação em conexão aberta e inspeção de terminal no navegador.

##### Requisitos de passagem <!-- wop:field handoff_requirements -->

- Exportar rotas, eventos de ciclo de vida e componente terminal para I009.

<!-- wop:prompt-predecessor-item I007 -->
#### Item I007 — Monitor de recursos

##### Saídas <!-- wop:field outputs -->

- Coletor/adaptadores, casos, Boundary e painéis de monitoramento.

##### Critérios de aceite <!-- wop:field acceptance_criteria -->

- Testes demonstram atribuição correta a dois ambientes, consumo compartilhado separado, unidades e carimbo temporal, métrica indisponível explícita, ordenação e negação de visão por usuário/processos sem permissão.

##### Evidência de verificação <!-- wop:field verification_evidence -->

- Fixtures de métricas, testes de autorização/apresentação e capturas das três visões.

##### Requisitos de passagem <!-- wop:field handoff_requirements -->

- Exportar rotas, formatos e frequência de coleta para I009.

<!-- wop:prompt-predecessor-item I008 -->
#### Item I008 — Administração e preferências

##### Saídas <!-- wop:field outputs -->

- Painel administrativo, configurações e testes de autorização/fluxo.

##### Critérios de aceite <!-- wop:field acceptance_criteria -->

- Administrador cria/edita/desativa/exclui logicamente conta, revoga autenticação sem parar processos, para sessão encerrando processos, configura frequência/destino/retenção de backup, vê permissões efetivas e retenta ambiente falho sem duplicar dados; membro não acessa rotas administrativas; preferências persistem; ação de impacto nomeia alvo e consequência.

##### Evidência de verificação <!-- wop:field verification_evidence -->

- Testes de rotas/UI, captura da confirmação e auditoria produzida por ações de teste.

##### Requisitos de passagem <!-- wop:field handoff_requirements -->

- Exportar telas/rotas e roteiro administrativo para I009.

<!-- wop:prompt-section shared_context -->
## Resultado <!-- wop:section outcome -->

Entregar uma primeira versão funcional do AetherDesk, destinada a um servidor Linux e homologada localmente em uma distribuição WSL 2 descartável: desktop web privado com contas e ambientes individuais, Explorador, editor, terminais Bash, monitoramento e administração. O pacote inclui código, contratos, testes, artefatos de instalação Linux, procedimentos de restauração e evidências dos 14 cenários de aceite descritos abaixo. A homologação local conclui este plano; validar boot, rede, segurança operacional e capacidade de um servidor Linux independente e ativar produção são trabalho posterior, sem alegação de que o WSL os comprovou.

## Contexto de execução <!-- wop:section execution_context -->

O diretório `E:\Alkimim\Projetos\CodeVault\AetherDesk` estava sem arquivos de aplicação ou repositório Git na inspeção inicial de 22/11/2026. O texto de requisitos anexado pelo usuário é a fonte do produto; seus comportamentos materiais estão transcritos em R001–R014. A referência remota `https://github.com/CodeVaultCommunity/OlympusProject_VulcanEcosystem` foi identificada no commit `4ab5824a7c7c962e96ac4480e8c254d023ba75df`; os 177 arquivos rastreados de `versioning/Stable-v1.0.0/` coincidem por SHA-256 com a cópia local em `E:\Alkimim\Projetos\CodeVault\OlympusProject\L3-VulcanEcosystem`. O `README.md` da edição tem SHA-256 `272AF70253CD5CB5E878D007BC2AAC3826E2042ECF918A35544D1CEEC9FC02C1`. A cópia local continua com alterações fora da edição e a edição não rastreada; W001 registra a comparação e a adaptação sem Minerva.

## Fatos confirmados <!-- wop:section confirmed_facts -->

- F001: O usuário pediu apenas Vulcan; Atlas e Minerva não serão produzidos para AetherDesk. Fonte: solicitação de 22/11/2026.
- F002: A cópia local Vulcan Stable-v1.0.0 organiza exemplos em `apps/<App>/`, `docs/L3_Vulcan/` e um mecanismo explícito de entrada; seus exemplos usam `entities/`, `usecases/`, `tools/`, `boundaries/` e `composition/`. Fonte: `versioning/Stable-v1.0.0/README.md` e `examples/minimal/`, inspecionados em 22/11/2026.
- F003: A conformidade formal dessa edição exige uma árvore Minerva completa e mapeamentos módulo→arquivo/símbolo em `realization.json`. AetherDesk, por escolha explícita de escopo, não alegará conformidade formal nem criará um ledger Minerva fictício. Fonte: `AGENTS.md` e `versioning/Stable-v1.0.0/README.md` locais.
- F004: O texto inicial propõe React/TypeScript, Monaco, xterm.js e runtime de isolamento, mas não fixa implementação nem políticas de ciclo de vida, ferramentas ou cópias de segurança. Fonte: texto de requisitos fornecido pelo usuário.
- F005: Em 22/11/2026, o responsável informou que não há host Linux independente, pediu homologação no WSL deste PC e autorizou adaptar o plano para concluir a versão local sem aguardar esse host. A consulta WSL sem elevação no sandbox ocultou distribuições existentes; a consulta elevada revelou `Ubuntu` e `docker-desktop`. I009 instalou separadamente `Ubuntu-24.04` em `.local-wsl/Ubuntu-24.04`, com systemd e Docker Engine nativo.

## Escopo <!-- wop:section scope -->

### Incluído

- Aplicação `apps/AetherDesk/` com núcleo Python organizado pelas responsabilidades Vulcan; interface React/TypeScript em `web/`, tratada como adaptador de interação; `launch.py` ou entrada equivalente com registro explícito; documentação de decisões e evidências em `docs/L3_Vulcan/`.
- Primeira configuração, login, sessões, papéis Administrador/Membro, permissões individuais, provisionamento e isolamento de ambientes, arquivos, editor, terminais, monitor, painel administrativo, preferências, auditoria, instalação na distribuição WSL 2 com HTTPS local e início por systemd na abertura da distribuição, backup/restauração e testes.
- Distribuição WSL 2 descartável com runtime de isolamento e dados de teste; artefatos de implantação para um servidor Linux independente, sem efetuar essa implantação nesta execução do plano.

### Excluído

- Modelos, árvores, geradores e declarações de conformidade Atlas/Minerva; alterações no repositório Olympus/Vulcan.
- Compartilhamento entre contas, lixeira, IDE com extensões/depuração, proxy de aplicações web dos usuários, GPU, histórico longo de métricas, acesso administrativo implícito a arquivos/terminais alheios e controle de processos pelo monitor.
- Comprovação de boot automático, certificado público, acesso de rede externo, quotas e carga representativa de um servidor Linux independente; esses resultados pertencem à validação posterior do host alvo e não podem ser inferidos do WSL.

## Partes interessadas e autoridade <!-- wop:section stakeholders -->

| Papel | Responsabilidade | Limite de decisão |
|---|---|---|
| Responsável pelo AetherDesk | Validar políticas de dados, processos, ferramentas, backup e aceite do produto | Aprova mudanças de escopo e eventual implantação real |
| Implementação | Definir contratos técnicos, construir e verificar em homologação | Não modifica Olympus, Atlas ou Minerva; não ativa produção sem autorização |
| Administrador do servidor | Operar contas, ambientes, cópias e recuperação | Ações administrativas pela aplicação; acesso ao hospedeiro permanece fora do produto |
| Membro | Usar o próprio ambiente conforme permissões | Não recebe acesso aos dados de terceiros |

## Requisitos <!-- wop:section requirements -->

- R001: Login privado, configuração do administrador inicial e desktop com janelas, barra de tarefas e aplicativos acessíveis no navegador.
- R002: Conta vinculada pelo backend a um ambiente Linux próprio; `/` é a mesma raiz no Bash, em programas, no Explorador e no editor; isolamento vale também para caminhos relativos e links simbólicos.
- R003: Contas individuais com criação, alteração, redefinição de senha, desativação e exclusão lógica; ambiente criado uma vez mesmo sob acessos concorrentes, processos encerrados na exclusão e arquivos preservados ao renomear, desativar ou excluir.
- R004: Papéis e permissões individuais aplicados no backend por operação e conexão contínua, com revogação efetiva em sessões abertas; visualização e controle são capacidades separadas.
- R005: Explorador lista, cria, renomeia, move, copia, exclui, envia, baixa e mostra metadados; resolve conflitos explicitamente e reflete alterações externas.
- R006: Editor com abas, sintaxe, busca/substituição, salvamento, `Ctrl+S`, proteção de alterações não salvas e detecção de concorrência externa.
- R007: Várias sessões Bash reais por conta, PTY interativo, sinais, redimensionamento, reconexão e encerramento explícito, com propriedade verificada a cada acesso; logout e revogação da sessão web mantêm processos em execução até concluírem ou serem cancelados por ação explícita.
- R008: Monitor distingue servidor, ambiente pessoal, outros ambientes e consumo compartilhado; CPU, RAM, armazenamento, I/O, rede e estado são apresentados com unidade, referência, atualização e indisponibilidade.
- R009: Administração expõe CRUD de contas, permissões efetivas, estado/falhas dos ambientes, revogar sessão e parar sessão como ações distintas, recuperação e confirmação de impacto.
- R010: Contas, permissões, preferências e arquivos persistem após reinício e atualização; backup é configurável no sistema, desativado por padrão, com frequência, destino e retenção por prazo ou substituição, e restauração verificável.
- R011: Esta versão entrega unidade systemd e configuração HTTPS para Linux, demonstra no WSL o início do serviço quando a distribuição é aberta, HTTPS local e segredos fora dos diretórios de usuários. O requisito original de início após boot de servidor Linux independente permanece fora do aceite desta versão e exige validação posterior no host alvo.
- R012: Eventos administrativos registram ator, operação, alvo e instante sem capturar conteúdo de arquivos ou terminais.
- R013: Interface expõe carregamento, salvamento, falha, desconexão e reconexão; tema, janelas abertas e suas posições persistem e são restaurados após novo login.
- R014: A primeira versão demonstra os 14 comportamentos de aceite do texto inicial, inclusive isolamento de dois usuários, duas sessões simultâneas da mesma conta, persistência, autorização negativa e restrições válidas no terminal.

## Restrições <!-- wop:section constraints -->

- C001: Não alterar nem gerar artefatos Atlas/Minerva; não declarar conformidade Vulcan Stable-v1.0.0 sem seus pré-requisitos. Reutilizar sua organização e princípios de código como adaptação identificada.
- C002: Cada operação usa identidade autenticada obtida do servidor; IDs e caminhos enviados pelo navegador não definem propriedade ou raiz.
- C003: Restrições de dados que devem valer para qualquer programa são impostas pelo ambiente e sistema de arquivos, além da API; ocultar um botão não basta.
- C004: Nunca usar comandos ou arquivos pessoais de usuários como registro administrativo básico.
- C005: Evidência WSL deve identificar distribuição, versão, daemon Docker e limites de rede, ciclo de vida e desempenho; não será apresentada como evidência de servidor independente. Usar somente contas, volumes, bancos e certificados de teste descartáveis.

## Decisões <!-- wop:section decisions -->

- D001: AetherDesk é uma aplicação independente que adota a organização Vulcan; sua fonte de requisitos é este plano, não um módulo Minerva. Não gerar `realization.json` ou `knowledge-graph.json` com linhagem Minerva inventada. Revisitar somente se o escopo incluir Minerva.
- D002: Usar um único registro de composição do backend e contratos explícitos entre núcleo, infraestrutura e adaptadores. `Boundary` nomeia apenas entrada HTTP/WebSocket; casos de uso autorizam o contexto confiável antes de causar efeitos. Revisitar se a edição remota verificada mudar essas regras.
- D003: Separar dados persistentes de imagem/base recriável; preservar arquivos na desativação e exclusão lógica. Logout e revogação não param processos; parada de sessão e exclusão os encerram. I001 fixa os contratos.
- D004: Por decisão do responsável em 22/11/2026, o aceite deste pacote é técnico e funcional por critérios observáveis em WSL 2, registrados por quem executa e revisa a evidência; não depende de assinatura humana adicional nem de um host ainda inexistente. Isso não constitui aceite de implantação em produção. Rever quando houver host alvo.

## Premissas <!-- wop:section assumptions -->

- A001: Um único servidor Linux continua sendo o destino do produto. W004 usa WSL 2 local como ambiente de homologação desta versão; medições e serviço nessa distribuição não demonstram boot nem desempenho do servidor independente.
- A002: O backend será Python para preservar diretamente a estrutura e os contratos de código demonstrados em Vulcan; o frontend será React/TypeScript como adaptador web. W001 confirma compatibilidade com o ambiente e registra qualquer adaptação antes de W002.
- A003: A primeira versão usa monitoramento atual e uma janela curta de amostras em memória. Persistência de histórico só entra por revisão do plano.

## Incógnitas <!-- wop:section unknowns -->

- U001: Resolvida em W001 para o commit remoto `4ab5824a7c7c962e96ac4480e8c254d023ba75df` e os 177 arquivos rastreados da edição Stable-v1.0.0; I001 registra limites da comparação e da adaptação.
- U002: O protótipo em Docker Linux demonstrou raiz pessoal e persistência. W004 repetirá isolamento, ferramentas e ciclo de vida no WSL; quotas e capacidade do servidor independente permanecem pendências explicitamente transferidas para a validação do host alvo. Falha de isolamento no WSL bloqueia este portão.
- U003: Resolvida pelo responsável em 22/11/2026: logout e revogação administrativa de sessão não param processos, PTYs ou desktop; novo login restaura janelas e posições. Parar sessão cancela processos. Excluir usuário para processos e preserva arquivos. I001 formaliza transições.
- U004: Resolvida pelo responsável em 22/11/2026: backup é configurável na aplicação e desativado por padrão; frequência, destino e retenção por prazo ou substituição são escolhas administrativas. O destino de teste para homologação será definido em W004.
- U005: Resolvida em I009: WSL 2 versão 2.5.10, Ubuntu 24.04.5 LTS descartável com systemd, Docker Engine 29.1.3 nativo, Caddy 2.6.2 e Python 3.12.3 foram instalados sem reinício do Windows. A validação de ciclo de vida da distribuição não substitui boot do servidor independente.

## Riscos <!-- wop:section risks -->

| Risco | Probabilidade | Impacto | Prevenção | Detecção | Responsável |
|---|---|---|---|---|---|
| Escape do ambiente ou acesso cruzado por path, symlink, API ou PTY | Média | Crítico | Isolamento Linux, identidade servidor, testes negativos e privilégios mínimos | Suíte de isolamento e revisão do modelo de ameaça | Implementação de runtime e segurança |
| Perda de arquivos em atualização, exclusão ou restauração | Média | Alto | Volumes persistentes, operações explícitas, cópias e ensaio de restauração | Verificação de hashes e jornada de recuperação | Operação |
| Credenciais ou tokens expostos em logs/terminal | Média | Alto | Armazenamento fora dos ambientes e redação de logs | Testes de vazamento e revisão de auditoria | Implementação de identidade |
| Corrida no primeiro acesso ou revogação tardia | Média | Alto | Provisionamento idempotente e checagem contínua de autorização | Testes concorrentes e de WebSocket aberto | Integração |
| Referência Vulcan local diverge do remoto | Média | Médio | Fixar identidade da fonte em W001 e limitar alegação arquitetural | Comparação de edição, estado e hashes | Responsável técnico |
| WSL difere do servidor alvo em boot, Docker, rede, permissões ou desempenho | Alta | Alto | Ambiente WSL descartável, evidência rotulada por ambiente e transferência explícita das provas do host | Comparar runbook, fontes de métricas, TLS e ciclo de vida com o contrato do servidor | Operação |

## Ambientes e operação <!-- wop:section operations -->

Desenvolvimento usa dados fictícios e testes sem privilégios do hospedeiro. Homologação deste pacote usa uma distribuição WSL 2 descartável, com systemd, runtime de isolamento, TLS local de teste, armazenamento no filesystem Linux da distribuição, contas de teste e coleta de métricas. Registrar se o daemon Docker é integrado ao Docker Desktop ou nativo; não tratar um como prova do outro. Produção, quando autorizada separadamente, recebe configuração própria, segredos fora dos volumes dos usuários, início automático após boot real, HTTPS, política de backup e runbook. W004 documenta instalação, atualização, reversão, restauração, logs, métricas e diagnóstico no WSL. Testes destrutivos ou de fuga rodam apenas nos dados e recursos descartáveis criados para o ensaio, nunca em dados reais.

## Contratos globais <!-- wop:section global_contracts -->

- GC001: Estrutura alvo: `apps/AetherDesk/entities/`, `value_objects/` quando houver uso real, `usecases/`, `tools/abstract/`, `tools/concrete/`, `boundaries/`, `composition/`, `support/`, `tests/`; `web/` contém o cliente de interação; `docs/L3_Vulcan/` guarda arquitetura, decisões e evidências; entrada raiz registra a aplicação explicitamente. Uma estrutura física distinta exige decisão documentada em W001.
- GC002: Dependências apontam para dentro: entidades/valores não importam infraestrutura ou interfaces; casos de uso recebem capacidades abstratas e contexto autenticado; ferramentas implementam efeitos; Boundary traduz HTTP/WebSocket; composição injeta implementações. Cada módulo tem dono e contrato público congelado em W001.
- GC003: IDs imutáveis de conta e ambiente são criados pelo servidor. Nome de usuário pode mudar sem alterar a identidade. Operações de arquivo e terminal derivam o ambiente do contexto autenticado. Sessões e permissões são reavaliadas nas fronteiras contínuas.
- GC004: Diretórios e contratos de módulos serão independentes por item em W002/W003. Arquivos compartilhados de registro, roteamento, migração global, configuração de build e infraestrutura são integrados somente nos gates ou em I009; módulos exportam interfaces sem editar o ponto de composição de outro item.
- GC005: Erros externos distinguem negação, conflito, indisponibilidade, perda de conexão e resultado de escrita desconhecido sem expor caminhos do hospedeiro ou segredos. IDs de evento permitem correlacionar falhas sem registrar conteúdos pessoais.

## Mapa de dependências <!-- wop:section dependency_map -->

| De | Para | Tipo | Contrato ou saída | Portão |
|---|---|---|---|---|
| W001 | W002 | Decisão/contrato | Referência, políticas, interfaces, isolamento | Protótipo e decisões aprovados |
| W002 | W003 | Saída/contrato | Identidade, runtime, desktop e SDK | Testes de fundação e integração de exports |
| W003 | W004 | Integração | Quatro módulos e permissões | Testes de módulo e registro conjunto |

## Rastreabilidade dos requisitos <!-- wop:section requirement_traceability -->

| Requisito | Fonte | Itens | Saídas | Verificação | Impacto final |
|---|---|---|---|---|---|
| R001 | Texto inicial §§2–3 | I002, I004, I009 | Identidade, desktop | Login e janelas em e2e | Acesso e navegação |
| R002 | Texto inicial §4 | I001, I003, I005, I006, I009 | Ambiente, APIs, PTY | Dois usuários, `/`, programa e symlink | Isolamento obrigatório |
| R003 | Texto inicial §3 e decisão de 22/11/2026 | I001–I003, I008, I009 | Contas/provisionamento | Concorrência, renomeação, desativação, exclusão lógica com arquivos mantidos | Persistência de identidade |
| R004 | Texto inicial §9 | I001, I002, I005–I009 | Matriz e checagens | Negação por API/WS, revogação | Autorização obrigatória |
| R005 | Texto inicial §5 | I005, I009 | Explorador/API | Operações, conflitos e Bash→UI | Arquivos utilizáveis |
| R006 | Texto inicial §6 | I005, I009 | Editor | Salvamento, concorrência e abas | Código preservado |
| R007 | Texto inicial §7 e decisão de 22/11/2026 | I001, I003, I006, I009 | PTY/terminal | Sessões, sinais, logout/revogação sem parada e parada explícita | Bash interativo persistente |
| R008 | Texto inicial §8 | I007, I009 | Monitor | Atribuição, unidades e visibilidade | Consumo confiável |
| R009 | Texto inicial §10 e decisão de 22/11/2026 | I002, I003, I008, I009 | Administração | CRUD, revogação distinta de parada | Operação de contas |
| R010 | Texto inicial §11 e decisão de 22/11/2026 | I001, I003, I008, I009 | Volumes/backup | Padrão desativado, configuração, retenções, reinício e restauração | Dados recuperáveis |
| R011 | Texto inicial §11 e decisão de escopo de 22/11/2026 | I001, I009 | Unidade systemd, proxy TLS e runbook Linux | Reabertura do WSL inicia serviço; HTTPS local e segregação de segredos; boot de servidor independente explicitamente pendente | Versão local instalável; produção condicionada à prova posterior no host |
| R012 | Texto inicial §11 | I002, I008, I009 | Auditoria | Evento ator/operação/alvo/hora e ausência de conteúdo | Responsabilização |
| R013 | Texto inicial §2 e decisão de 22/11/2026 | I004, I008, I009 | Estados/preferências | Janelas e posições restauradas após novo login | Continuidade da experiência |
| R014 | Texto inicial §13 e decisão de escopo de 22/11/2026 | I001–I009 | Matriz e2e | 14 cenários na distribuição WSL 2 | Aceite funcional da versão local |

## Estratégia de verificação <!-- wop:section verification_strategy -->

Executar verificações estáticas e testes unitários para regras puras; integração para banco, filesystem, runtime e PTY; contratos para Boundary/casos de uso/cliente; e2e para jornadas críticas na distribuição WSL 2. Fixtures isolam conta, banco, volume, porta, tempo e métricas por item. Cenários de falha incluem gravação de resultado desconhecido, provisionamento concorrente, quota/armazenamento indisponível, perda de conexão, revogação e restauração. O orçamento de desempenho proposto em W001 define número de usuários, volume de arquivos, sessões e intervalo de coleta; W004 confirma metas locais antes de medir percentis e consumo no WSL. Nenhum teste simulado substitui a prova Linux de `/` e de processos; nenhuma medição WSL substitui a medição no servidor futuro.

## Reversão e recuperação <!-- wop:section rollback_recovery -->

Antes de migração ou atualização, criar cópia verificável de banco, configurações e volumes persistentes em homologação. Se migração, montagem ou teste de isolamento falhar, parar a versão nova, restaurar binários/configuração anterior e dados conforme política de consistência documentada; verificar login, permissões e hashes de arquivos de duas contas. Mudanças de esquema irreversíveis exigem migração de retorno ou estratégia de avanço controlado antes da execução. Desativar conta não apaga dados. Produção terá ensaio e autorização próprios.

## Aceite final <!-- wop:section final_acceptance -->

- Todos os portões W001–W004 passaram em ordem e cada item tem evidência real identificada.
- R001–R010 e R012–R014 estão demonstrados na distribuição WSL 2; R011 está demonstrado apenas no recorte local declarado. Os 14 cenários passaram no WSL e as telas de login, desktop, Explorador, editor, terminal, monitores, administração e configurações foram inspecionadas.
- Isolamento, autorização, persistência, HTTPS local, início após abertura da distribuição, backup/restauração e orçamento de carga local passaram; falhas ou limitações residuais são explícitas. Boot, certificado público, rede, quotas e capacidade do servidor independente constam como requisitos de uma validação posterior antes de produção.
- O executor registra avaliação técnica e funcional contra os critérios observáveis, com evidência e ator identificados; nenhum aceite humano adicional é requisito deste pacote. Aceite para produção permanece separado.

## Cenários funcionais de aceite <!-- wop:section functional_scenarios -->

Estes cenários reproduzem o contrato observável do texto inicial. I009 registra procedimento, resultado e evidência individual para S01–S14:

1. S01: O administrador cria uma conta e o ambiente é preparado automaticamente.
2. S02: Dois usuários acessam o mesmo endereço e encontram ambientes independentes.
3. S03: Ambos criam um arquivo com o mesmo nome e mantêm conteúdos distintos.
4. S04: `cd /` leva à raiz correta de cada ambiente.
5. S05: Arquivo criado no Bash aparece no Explorador e abre no editor.
6. S06: Programas executados no terminal respeitam raiz e permissões do ambiente.
7. S07: Várias sessões Bash mantêm estados independentes e compartilham arquivos da conta.
8. S08: Dois acessos simultâneos à mesma conta reutilizam o ambiente correto.
9. S09: Reiniciar o ambiente preserva arquivos definidos como persistentes.
10. S10: Alterar identificadores enviados à API não concede acesso a outra conta.
11. S11: O monitor apresenta consumo disponível atribuído ao ambiente correto.
12. S12: Cada usuário recebe somente dados de monitoramento autorizados.
13. S13: Revogar permissão afeta conexões já abertas.
14. S14: Restrição de acesso a dados continua válida quando tentada pelo terminal.

<!-- wop:prompt-section completion_contract -->
### Critérios gerais de aceite <!-- wop:field general_acceptance_criteria -->

- Os 14 cenários de R014 passam na distribuição WSL 2 com dois usuários e duas sessões simultâneas da mesma conta; APIs/WS e terminal negam acessos cruzados e revogações abertas.
- Na distribuição WSL 2, instalação com HTTPS local e serviço systemd iniciado ao abrir a distribuição, atualização, reversão, backup configurado explicitamente no ensaio e restauração são reproduzidos com dados de teste; padrão desativado e duas modalidades de retenção são verificados. A prova registra que systemd não garante que a instância WSL permaneça ativa nem que o serviço inicie com o boot do Windows.
- O orçamento proposto em W001 é confirmado como meta deste ensaio local antes da medição; a carga no WSL é medida com perfil, amostras e percentis e atende às metas ou os desvios são corrigidos e repetidos. A medição não é apresentada como capacidade do servidor alvo.

### Portão de conclusão <!-- wop:field completion_gate -->

I009 aceito com relatório de testes, revisão de segurança, restauração, operação e limites residuais no WSL; inspeção funcional documentada contra os critérios do item. Não exigir host independente nem aprovação humana adicional para concluir este pacote. A validação do host alvo e a implantação de produção permanecem separadas.

### Evidências exigidas <!-- wop:field evidence_requirements -->

- Relatórios de unidade/integração/e2e, matriz R001–R014 com R011 delimitado, logs redigidos, medição de carga WSL, inspeção UI, instalação/reabertura da distribuição/reversão, backup/restauração e decisão de aceite técnico. Registrar como pendências externas a prova de boot e de capacidade do servidor independente.

### Integração e passagem <!-- wop:field integration_handoff -->

Entregar código e configuração versionados, runbook de instalação/atualização/reversão/restauração, matriz de evidências WSL, riscos residuais e decisão de aceite técnico; listar separadamente as verificações do servidor independente para a etapa posterior.

<!-- wop:prompt-completion-item I009 -->
#### Item I009 — Produto integrado e operação

##### Critérios de aceite <!-- wop:field acceptance_criteria -->

- Cada um dos 14 cenários tem procedimento, ambiente WSL, resultado e evidência; cenários adicionais demonstram logout/revogação com processos e janelas preservados, parada/exclusão com processos encerrados e arquivos mantidos, backup desativado por padrão e configuração das duas retenções; falhas bloqueantes são corrigidas e repetidas. Após encerrar e reabrir a distribuição, systemd inicia o serviço e os dados persistem; HTTPS local, cookies `Secure`, WebSocket `wss` e permissões dos segredos são verificados. Backup restaurado reproduz contas, permissões, preferências e arquivos sem perder isolamento.
- Testes negativos cobrem troca de IDs, path traversal/symlink, PTY alheio, revogação durante WS e restrição de filesystem via Bash; medição informa carga, amostras, percentis e comparação com metas locais previamente registradas. O relatório identifica Docker Desktop ou daemon nativo, limitações do WSL e provas ainda necessárias no servidor independente.

##### Evidência de verificação <!-- wop:field verification_evidence -->

- Comandos/versões de Windows, WSL, distribuição e Docker; relatórios de testes e Linux WSL, capturas, resultados de restauração, revisão de segurança, orçamento e medição de carga local, registro de aceite técnico e lista das provas futuras do host.

##### Requisitos de passagem <!-- wop:field handoff_requirements -->

- Entregar procedimentos operacionais, configuração sem segredos, resultados WSL e limitações para uma decisão posterior de validação e implantação em servidor independente.
