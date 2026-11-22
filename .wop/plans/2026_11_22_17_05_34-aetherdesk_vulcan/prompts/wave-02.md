---
artifact: wop-wave-prompt
plan_id: a47c4d01-5e49-4b24-aaaf-2535f78447e0
plan_version: 4
plan_title: "Implementar o AetherDesk com organização Vulcan"
wave_id: W002
authorized_items: "I002,I003,I004"
non_authorized_items: "I001,I005,I006,I007,I008,I009"
predecessor_waves: W001
blocked_successor_waves: "W003,W004"
language: pt-BR
source_readme: README.md
source_readme_sha256: b04889ec9885f3cea62a1ec0ee02f75fc1d25474707fae93187230f3dc448540
---

# Onda W002 — Fundações do produto

<!-- wop:prompt-section global_protocol -->
## Protocolo de execução <!-- wop:section execution_protocol -->

Identifique o pacote e leia `README.md` e todos os prompts de onda referenciados. Execute as ondas em ordem estrita; não avance antes de todos os itens da onda concluírem, serem aceitos individualmente, integrados quando necessário e de o portão passar. Integre resultados, registre evidências e transições de estado, bloqueie mudanças de escopo ou efeitos externos não autorizados e avalie o aceite final. Use somente o paralelismo cuja independência esteja demonstrada na onda correspondente.

<!-- wop:prompt-section execution_scope -->
<!-- wop:prompt-assigned-wave W002 -->
### Objetivo geral <!-- wop:field general_objective -->

Construir fundações verificadas e independentes para identidade, runtime pessoal e desktop, usando apenas os contratos aceitos em W001.

### Requisitos atendidos <!-- wop:field requirements_addressed -->

- R001, R002, R003, R004, R010, R012, R013.

### Instruções de execução da onda <!-- wop:field execution_instructions -->

Execute apenas I002, I003 e I004 com fixtures isoladas. Aceite cada item separadamente, depois integre exports no portão e verifique contratos congelados. Não inicie módulos funcionais posteriores.

### Justificativa de paralelismo <!-- wop:field parallelism_rationale -->

I002 escreve somente `apps/AetherDesk/identity/`, casos/entidades/ferramentas de conta e migração de identidade; I003 escreve somente runtime e fixtures Linux; I004 escreve somente `web/` shell e componentes comuns. Os três consomem contratos congelados em W001, não as saídas uns dos outros. Bancos/volumes/portas de teste são exclusivos por item; registro e composição globais são integrados no portão, depois dos itens. Pares I002–I003, I002–I004 e I003–I004 não compartilham arquivos nem efeitos externos durante execução. Uma falha de um item não altera fixtures dos demais.

### Limites de propriedade <!-- wop:field ownership_boundaries -->

I002 detém identidade, sessões, permissões, auditoria e migração própria; I003 detém provisionamento, montagem, ciclo de vida e persistência; I004 detém shell visual e SDK contratual de cliente. Nenhum item altera `AppComposition`, `launch.py`, roteamento global ou configuração comum até o portão.

<!-- wop:prompt-assigned-item I002 -->
#### Item I002 — Identidade, sessões e autorização

##### Objetivo <!-- wop:field objective -->

Entregar o núcleo de contas e permissões com contexto autenticado confiável e auditoria administrativa.

##### Contexto <!-- wop:field context -->

Casos de uso autorizam antes de validar dados controlados pelo cliente ou causar efeitos; Boundary traduz solicitações e obtém o ator da sessão.

##### Entradas e pré-requisitos <!-- wop:field inputs_prerequisites -->

- Contratos de identidade, papéis, políticas de revogação e migração de W001.

##### Escopo <!-- wop:field scope -->

- Configuração inicial, credenciais e sessões, criação/edição/desativação/exclusão lógica, redefinição de senha, papéis, permissões efetivas, revogação de autenticação distinta de parada de sessão e registro administrativo sem dados pessoais de conteúdo.

##### Propriedade <!-- wop:field ownership -->

- Arquivos de domínio, ferramentas e Boundary de identidade e sua migração; fixtures de DB próprias.

##### Saídas <!-- wop:field outputs -->

- Núcleo de identidade, esquema e migração, APIs/exports de autenticação/autorização, eventos de revogação e suíte de testes.

##### Restrições <!-- wop:field restrictions -->

- Não implementar acesso administrativo implícito aos dados de terceiros; não escrever no runtime ou shell visual.

<!-- wop:prompt-assigned-item I003 -->
#### Item I003 — Ambiente Linux individual

##### Objetivo <!-- wop:field objective -->

Entregar provisionamento idempotente, raiz pessoal e ciclo de vida de ambiente com dados persistentes.

##### Contexto <!-- wop:field context -->

O ambiente executa Bash e programas; a API nunca aceita um diretório hospedeiro ou ID livre como autoridade de propriedade.

##### Entradas e pré-requisitos <!-- wop:field inputs_prerequisites -->

- Contrato de ambiente, políticas de processo/dados e protótipo Linux aceitos em W001.

##### Escopo <!-- wop:field scope -->

- Criar/iniciar/parar/recriar ambiente, preservar execução após logout/revogação, encerrar processos na parada de sessão e exclusão, base de ferramentas, montagem pessoal, limites iniciais, estado e diagnóstico; exportar operações seguras de arquivos, PTY e métricas.

##### Propriedade <!-- wop:field ownership -->

- Runtime, ferramentas de ambiente, artefatos Linux e fixtures exclusivas; não altera identidade ou web.

##### Saídas <!-- wop:field outputs -->

- Gerenciador de ambiente, configuração da imagem/base, contrato de volumes, estado e suíte de isolamento/concorrência.

##### Restrições <!-- wop:field restrictions -->

- Testes potencialmente destrutivos apenas em Linux descartável; não montar diretórios de outro usuário nem expor socket privilegiado ao navegador.

<!-- wop:prompt-assigned-item I004 -->
#### Item I004 — Desktop e componentes comuns

##### Objetivo <!-- wop:field objective -->

Entregar o shell web responsivo que hospeda aplicativos e preserva preferências visuais.

##### Contexto <!-- wop:field context -->

O cliente apresenta o estado; não decide autorização. Usa adaptadores de API contratados e fixtures, sem depender do backend ainda em construção.

##### Entradas e pré-requisitos <!-- wop:field inputs_prerequisites -->

- Contratos HTTP/WebSocket, estados de conexão, navegação e permissões de W001.

##### Escopo <!-- wop:field scope -->

- Login, preparação, desktop, gerenciador de janelas, barra de tarefas, notificações, SDK de cliente e persistência de tema, janelas abertas e posições pelo contrato.

##### Propriedade <!-- wop:field ownership -->

- `web/` shell, UI base e mocks isolados; não edita backend nem aplicativos de W003.

##### Saídas <!-- wop:field outputs -->

- Shell React/TypeScript, contratos de slots de aplicativo, telas de login/preparação e testes de interação.

##### Restrições <!-- wop:field restrictions -->

- Não tratar ocultação visual como autorização; evitar dados de usuários de teste em snapshots de interface.

<!-- wop:prompt-section predecessor_verification -->
### Pré-requisitos <!-- wop:field prerequisites -->

W001 passou; conferir contratos, protótipo, políticas aprovadas e mapa de propriedade antes de qualquer edição.

<!-- wop:prompt-predecessor W001 -->
## Onda W001 — Contratos e prova de viabilidade

### Objetivo geral <!-- wop:field general_objective -->

Fixar a referência arquitetural, as políticas ainda abertas, os contratos de módulos e uma prova de isolamento Linux antes de construir o produto.

### Critérios gerais de aceite <!-- wop:field general_acceptance_criteria -->

- Uma decisão de arquitetura identifica edição/estado/fonte Vulcan, a adaptação sem Minerva, layout, contratos públicos, modelo de ameaça e limites; cada incógnita U001–U004 tem decisão ou bloqueio explícito.
- Um protótipo em Linux demonstra que `cd /` e leitura de `/dados.txt` permanecem no ambiente correto para dois usuários e que atualização da base não apaga dados persistentes.

### Portão de conclusão <!-- wop:field completion_gate -->

I001 aceito com evidências reproduzíveis; decisões do responsável sobre processos, dados e backup incorporadas; nenhum contrato necessário a W002 permanece indefinido. Falha de isolamento ou divergência arquitetural material bloqueia W002.

### Evidências exigidas <!-- wop:field evidence_requirements -->

- `docs/L3_Vulcan/architecture.md`, `decision-record.md`, contratos versionados, modelo de ameaça, relatório do protótipo com comandos/ambiente/resultados e registro da fonte Vulcan.

### Integração e passagem <!-- wop:field integration_handoff -->

Congele interfaces para identidade, ambiente, arquivos, PTY, métricas, auditoria e cliente web, além de ownership de arquivos e migrações. Entregue decisões D001–D003 confirmadas ou revisadas e comandos de verificação do protótipo.

<!-- wop:prompt-predecessor-item I001 -->
#### Item I001 — Referência, políticas e contratos

##### Saídas <!-- wop:field outputs -->

- Documentos e contratos GC001–GC005 refinados, matriz de permissões, tabela de transições de ambiente, mapa de persistência, decisão de runtime, orçamento de carga, relatório do protótipo e inventário de ownership por módulo.

##### Critérios de aceite <!-- wop:field acceptance_criteria -->

- Cada contrato consumido em W002/W003 define entrada, saída, falha, identidade e versão; relatório reproduz dois usuários com mesmo caminho e conteúdo diferente, raiz correta para shell e programa e persistência após recriação.
- O orçamento de carga declara usuários simultâneos, arquivos, terminais, intervalo de amostragem, ambiente de medição e limites de latência/consumo para W004.
- A fonte Vulcan tem identidade verificável ou o limite de verificação é documentado e aceito como restrição de referência; nenhuma afirmação de conformidade depende de Minerva ausente.

##### Evidência de verificação <!-- wop:field verification_evidence -->

- Hashes/estado/edição da fonte, revisão do desenho, comandos e saídas do protótipo em Linux, registro de decisão de políticas pelo responsável.

##### Requisitos de passagem <!-- wop:field handoff_requirements -->

- Entregar contratos congelados, ownership de diretórios, fixtures independentes e decisões operacionais aos itens I002–I008.

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

- Identidade e permissões, ambiente isolado e shell do desktop passam suas suítes em fixtures separadas; contratos entre módulos coincidem com W001 e não há escrita cruzada.
- Dois provisionamentos simultâneos produzem um ambiente; conta desativada perde acesso sem apagar arquivos; logout/revogação conservam processos e desktop; dados sobrevivem à recriação; shell web apresenta estados de conexão e janelas básicas.

### Portão de conclusão <!-- wop:field completion_gate -->

I002, I003 e I004 aceitos individualmente; revisão de contratos e integração de pacotes passam sem alterar ownership concorrente; nenhuma falha de isolamento ou autorização fica aberta.

### Evidências exigidas <!-- wop:field evidence_requirements -->

- Saídas de testes unitários, integração de identidade/DB, concorrência e isolamento Linux, verificações estáticas do cliente e inspeção do desktop em navegador.

### Integração e passagem <!-- wop:field integration_handoff -->

Publicar interfaces versionadas de contexto autenticado, repositório de contas, ambiente pessoal, eventos e SDK/web shell. Registrar alterações de contrato como revisão do plano antes de W003.

<!-- wop:prompt-completion-item I002 -->
#### Item I002 — Identidade, sessões e autorização

##### Critérios de aceite <!-- wop:field acceptance_criteria -->

- Testes mostram primeiro administrador único, senha não armazenada em claro, alteração de nome sem troca de ID, desativação/exclusão bloqueando novo acesso, arquivos preservados na exclusão, revogação de sessão aberta sem parar processos e negação de operações com ID de outro usuário.

##### Evidência de verificação <!-- wop:field verification_evidence -->

- Resultados de testes de DB, concorrência, revogação e ausência de credenciais em logs; esquema e comando de migração.

##### Requisitos de passagem <!-- wop:field handoff_requirements -->

- Exportar contexto, checagens de permissão, eventos de revogação e versão do esquema para I005–I008.

<!-- wop:prompt-completion-item I003 -->
#### Item I003 — Ambiente Linux individual

##### Critérios de aceite <!-- wop:field acceptance_criteria -->

- Dois logins concorrentes da mesma conta compartilham um único ambiente; dois IDs distintos usam raízes independentes; `cd /`, programa que abre `/dados.txt`, symlink e recriação obedecem isolamento e persistência; logout/revogação conservam processo ativo e parada explícita o encerra.

##### Evidência de verificação <!-- wop:field verification_evidence -->

- Saídas de testes no Linux identificado, inventário de montagens/volumes e logs de falha/retry sem dados sensíveis.

##### Requisitos de passagem <!-- wop:field handoff_requirements -->

- Exportar operações de ambiente e capacidade de coleta para I005–I007, com erros e semântica de reconexão.

<!-- wop:prompt-completion-item I004 -->
#### Item I004 — Desktop e componentes comuns

##### Critérios de aceite <!-- wop:field acceptance_criteria -->

- Inspeção em navegador demonstra abrir, mover, redimensionar, minimizar, maximizar e alternar janelas; novo login restaura janelas e posições; estados de carregamento/falha/desconexão são distinguíveis e reconexão preserva conteúdo disponível.

##### Evidência de verificação <!-- wop:field verification_evidence -->

- Build/tipos, testes de componentes e roteiro com capturas da inspeção em navegador.

##### Requisitos de passagem <!-- wop:field handoff_requirements -->

- Publicar slots de aplicativo, cliente versionado e padrões de estado para I005–I008.
