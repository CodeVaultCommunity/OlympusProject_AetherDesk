---
artifact: wop-wave-prompt
plan_id: a47c4d01-5e49-4b24-aaaf-2535f78447e0
plan_version: 2
plan_title: "Implementar o AetherDesk com organização Vulcan"
wave_id: W003
authorized_items: "I005,I006,I007,I008"
non_authorized_items: "I001,I002,I003,I004,I009"
predecessor_waves: W002
blocked_successor_waves: W004
language: pt-BR
source_readme: README.md
source_readme_sha256: 58690bbdbb9486101f0a21f6c3759c8be4abac840a930910d7221140739b0fa6
---

# Onda W003 — Aplicativos e painéis

<!-- wop:prompt-section global_protocol -->
## Protocolo de execução <!-- wop:section execution_protocol -->

Identifique o pacote e leia `README.md` e todos os prompts de onda referenciados. Execute as ondas em ordem estrita; não avance antes de todos os itens da onda concluírem, serem aceitos individualmente, integrados quando necessário e de o portão passar. Integre resultados, registre evidências e transições de estado, bloqueie mudanças de escopo ou efeitos externos não autorizados e avalie o aceite final. Use somente o paralelismo cuja independência esteja demonstrada na onda correspondente.

<!-- wop:prompt-section execution_scope -->
<!-- wop:prompt-assigned-wave W003 -->
### Objetivo geral <!-- wop:field general_objective -->

Implementar os quatro módulos funcionais do desktop sobre fundações e contratos aceitos, com propriedade isolada por módulo.

### Requisitos atendidos <!-- wop:field requirements_addressed -->

- R004, R005, R006, R007, R008, R009, R012, R013.

### Instruções de execução da onda <!-- wop:field execution_instructions -->

Execute apenas I005, I006, I007 e I008 em ambientes de teste isolados. Aceite cada módulo, depois registre os exports no portão e teste abertura conjunta no desktop. Não inicie a homologação final antes do portão.

### Justificativa de paralelismo <!-- wop:field parallelism_rationale -->

I005 detém arquivos/editor, I006 terminal, I007 monitor e I008 administração/configurações; cada um possui diretórios, Boundary, casos, ferramentas, componentes e fixtures próprios. Todos consomem W002, sem consumir saídas entre si. Pares I005–I006, I005–I007, I005–I008, I006–I007, I006–I008 e I007–I008 não editam arquivos comuns, nem usam o mesmo banco/volume/porta de teste; adaptadores falsos substituem capacidades de outros módulos. I005 e I006 operam sobre arquivos reais apenas em fixtures isoladas; conflitos de produção são testados na integração W004. Registro global ocorre somente no portão. A falha de um módulo não invalida fixtures dos demais.

### Limites de propriedade <!-- wop:field ownership_boundaries -->

Cada item detém seu módulo em `apps/AetherDesk/` e `web/apps/`; nenhuma edição direta em `AppComposition`, roteador raiz, configuração comum ou migração de outro módulo. Alterações de contrato exigem revisão antes do portão.

<!-- wop:prompt-assigned-item I005 -->
#### Item I005 — Explorador e editor

##### Objetivo <!-- wop:field objective -->

Permitir operações de arquivo e edição de código coerentes com a raiz pessoal.

##### Contexto <!-- wop:field context -->

Arquivos podem mudar pelo terminal; leitura/escrita deve observar versão e conflito, sem confiar em caminho ou ID como autoridade.

##### Entradas e pré-requisitos <!-- wop:field inputs_prerequisites -->

- Contexto/ambiente de W002, contrato de arquivos e slots web de W001/W002.

##### Escopo <!-- wop:field scope -->

- API de arquivos, upload/download, listagem/metadados, operações, eventos de atualização, Explorer e Monaco com abas, busca, salvamento e proteção de alterações.

##### Propriedade <!-- wop:field ownership -->

- Módulo de arquivos/editor e seus testes/fixtures; nenhuma edição no módulo terminal.

##### Saídas <!-- wop:field outputs -->

- Boundary de arquivos, casos de uso, ferramenta de filesystem, Explorer, editor e testes.

##### Restrições <!-- wop:field restrictions -->

- Exclusão irreversível exige confirmação de alvo na interface; lixeira fora de escopo. Limites de upload e streaming devem ser contratados e testados.

<!-- wop:prompt-assigned-item I006 -->
#### Item I006 — Terminal Bash

##### Objetivo <!-- wop:field objective -->

Entregar sessões PTY interativas, isoladas e reconectáveis.

##### Contexto <!-- wop:field context -->

Cada terminal tem processo e diretório próprios, enquanto arquivos são compartilhados pela mesma conta.

##### Entradas e pré-requisitos <!-- wop:field inputs_prerequisites -->

- Contratos de identidade/ambiente/PTY e slots web aceitos em W001/W002.

##### Escopo <!-- wop:field scope -->

- Criar/listar/reconectar/encerrar PTY, fluxo WebSocket, redimensionamento, sinais e interface xterm.js.

##### Propriedade <!-- wop:field ownership -->

- Módulo terminal, Boundary WebSocket e fixtures exclusivas.

##### Saídas <!-- wop:field outputs -->

- Serviço PTY, Boundary, cliente terminal e testes.

##### Restrições <!-- wop:field restrictions -->

- Não registrar entrada/saída do terminal; não expor socket de runtime ao cliente.

<!-- wop:prompt-assigned-item I007 -->
#### Item I007 — Monitor de recursos

##### Objetivo <!-- wop:field objective -->

Mostrar consumo próprio, do servidor e por usuário somente no nível autorizado.

##### Contexto <!-- wop:field context -->

Métricas de servidor, ambientes e serviços compartilhados têm fontes e referências diferentes; indisponibilidade não equivale a zero.

##### Entradas e pré-requisitos <!-- wop:field inputs_prerequisites -->

- Contratos de métricas, identidade e capacidades do runtime de W001/W002.

##### Escopo <!-- wop:field scope -->

- Coleta amostrada, agregação, autorização por visão, indicadores atuais/gráficos recentes e telas de monitor.

##### Propriedade <!-- wop:field ownership -->

- Módulo monitor e fixtures de métricas próprias.

##### Saídas <!-- wop:field outputs -->

- Coletor/adaptadores, casos, Boundary e painéis de monitoramento.

##### Restrições <!-- wop:field restrictions -->

- Sem controle de processos ou exposição de argumentos completos; amostragem deve respeitar orçamento medido em W004.

<!-- wop:prompt-assigned-item I008 -->
#### Item I008 — Administração e preferências

##### Objetivo <!-- wop:field objective -->

Entregar interfaces para contas, permissões, recuperação de ambientes e preferências pessoais.

##### Contexto <!-- wop:field context -->

O núcleo de identidade e runtime já define efeitos; este módulo apresenta ações e chamadas autorizadas, sem criar uma segunda política.

##### Entradas e pré-requisitos <!-- wop:field inputs_prerequisites -->

- APIs de identidade/ambiente, matriz de permissões e shell web de W001/W002.

##### Escopo <!-- wop:field scope -->

- Telas de CRUD de contas, permissões, revogação e parada de sessão como ações distintas, ambientes, auditoria, backup configurável desativado por padrão e configurações de tema/perfil; confirmação de ações com impacto e diagnóstico de falhas.

##### Propriedade <!-- wop:field ownership -->

- Componentes e Boundary de administração/preferências, sem editar serviços de identidade/runtime.

##### Saídas <!-- wop:field outputs -->

- Painel administrativo, configurações e testes de autorização/fluxo.

##### Restrições <!-- wop:field restrictions -->

- Remoção de arquivos de conta e leitura de conteúdo alheio permanecem fora de escopo; não transformar monitoramento em controle.

<!-- wop:prompt-section predecessor_verification -->
### Pré-requisitos <!-- wop:field prerequisites -->

W002 passou; conferir versões dos exports de identidade, ambiente, cliente web e os resultados de isolamento antes de iniciar módulos.

<!-- wop:prompt-predecessor W002 -->
## Onda W002 — Fundações do produto

### Objetivo geral <!-- wop:field general_objective -->

Construir fundações verificadas e independentes para identidade, runtime pessoal e desktop, usando apenas os contratos aceitos em W001.

### Critérios gerais de aceite <!-- wop:field general_acceptance_criteria -->

- Identidade e permissões, ambiente isolado e shell do desktop passam suas suítes em fixtures separadas; contratos entre módulos coincidem com W001 e não há escrita cruzada.
- Dois provisionamentos simultâneos produzem um ambiente; conta desativada perde acesso sem apagar arquivos; logout/revogação conservam processos e desktop; dados sobrevivem à recriação; shell web apresenta estados de conexão e janelas básicas.

### Portão de conclusão <!-- wop:field completion_gate -->

I002, I003 e I004 aceitos individualmente; revisão de contratos e integração de pacotes passam sem alterar ownership concorrente; nenhuma falha de isolamento ou autorização fica aberta.

### Evidências exigidas <!-- wop:field evidence_requirements -->

- Saídas de testes unitários, integração de identidade/DB, concorrência e isolamento Linux, verificações estáticas do cliente e inspeção do desktop em navegador.

### Integração e passagem <!-- wop:field integration_handoff -->

Publicar interfaces versionadas de contexto autenticado, repositório de contas, ambiente pessoal, eventos e SDK/web shell. Registrar alterações de contrato como revisão do plano antes de W003.

<!-- wop:prompt-predecessor-item I002 -->
#### Item I002 — Identidade, sessões e autorização

##### Saídas <!-- wop:field outputs -->

- Núcleo de identidade, esquema e migração, APIs/exports de autenticação/autorização, eventos de revogação e suíte de testes.

##### Critérios de aceite <!-- wop:field acceptance_criteria -->

- Testes mostram primeiro administrador único, senha não armazenada em claro, alteração de nome sem troca de ID, desativação/exclusão bloqueando novo acesso, arquivos preservados na exclusão, revogação de sessão aberta sem parar processos e negação de operações com ID de outro usuário.

##### Evidência de verificação <!-- wop:field verification_evidence -->

- Resultados de testes de DB, concorrência, revogação e ausência de credenciais em logs; esquema e comando de migração.

##### Requisitos de passagem <!-- wop:field handoff_requirements -->

- Exportar contexto, checagens de permissão, eventos de revogação e versão do esquema para I005–I008.

<!-- wop:prompt-predecessor-item I003 -->
#### Item I003 — Ambiente Linux individual

##### Saídas <!-- wop:field outputs -->

- Gerenciador de ambiente, configuração da imagem/base, contrato de volumes, estado e suíte de isolamento/concorrência.

##### Critérios de aceite <!-- wop:field acceptance_criteria -->

- Dois logins concorrentes da mesma conta compartilham um único ambiente; dois IDs distintos usam raízes independentes; `cd /`, programa que abre `/dados.txt`, symlink e recriação obedecem isolamento e persistência; logout/revogação conservam processo ativo e parada explícita o encerra.

##### Evidência de verificação <!-- wop:field verification_evidence -->

- Saídas de testes no Linux identificado, inventário de montagens/volumes e logs de falha/retry sem dados sensíveis.

##### Requisitos de passagem <!-- wop:field handoff_requirements -->

- Exportar operações de ambiente e capacidade de coleta para I005–I007, com erros e semântica de reconexão.

<!-- wop:prompt-predecessor-item I004 -->
#### Item I004 — Desktop e componentes comuns

##### Saídas <!-- wop:field outputs -->

- Shell React/TypeScript, contratos de slots de aplicativo, telas de login/preparação e testes de interação.

##### Critérios de aceite <!-- wop:field acceptance_criteria -->

- Inspeção em navegador demonstra abrir, mover, redimensionar, minimizar, maximizar e alternar janelas; novo login restaura janelas e posições; estados de carregamento/falha/desconexão são distinguíveis e reconexão preserva conteúdo disponível.

##### Evidência de verificação <!-- wop:field verification_evidence -->

- Build/tipos, testes de componentes e roteiro com capturas da inspeção em navegador.

##### Requisitos de passagem <!-- wop:field handoff_requirements -->

- Publicar slots de aplicativo, cliente versionado e padrões de estado para I005–I008.

<!-- wop:prompt-section shared_context -->
## Resultado <!-- wop:section outcome -->

Entregar uma primeira versão funcional do AetherDesk: desktop web privado para um servidor Linux, com contas e ambientes individuais, Explorador, editor, terminais Bash, monitoramento e administração. O pacote de entrega inclui código, contratos, testes, instalação reproduzível em Linux, procedimentos de restauração e evidências dos 14 cenários de aceite descritos abaixo. Este plano prepara uma implantação verificável em ambiente de homologação; a ativação em um servidor de produção é uma ação externa separada.

## Contexto de execução <!-- wop:section execution_context -->

O diretório `E:\Alkimim\Projetos\CodeVault\AetherDesk` estava sem arquivos de aplicação ou repositório Git na inspeção inicial de 22/11/2026. O texto de requisitos anexado pelo usuário é a fonte do produto; seus comportamentos materiais estão transcritos em R001–R014. A referência remota `https://github.com/CodeVaultCommunity/OlympusProject_VulcanEcosystem` foi identificada no commit `4ab5824a7c7c962e96ac4480e8c254d023ba75df`; os 177 arquivos rastreados de `versioning/Stable-v1.0.0/` coincidem por SHA-256 com a cópia local em `E:\Alkimim\Projetos\CodeVault\OlympusProject\L3-VulcanEcosystem`. O `README.md` da edição tem SHA-256 `272AF70253CD5CB5E878D007BC2AAC3826E2042ECF918A35544D1CEEC9FC02C1`. A cópia local continua com alterações fora da edição e a edição não rastreada; W001 registra a comparação e a adaptação sem Minerva.

## Fatos confirmados <!-- wop:section confirmed_facts -->

- F001: O usuário pediu apenas Vulcan; Atlas e Minerva não serão produzidos para AetherDesk. Fonte: solicitação de 22/11/2026.
- F002: A cópia local Vulcan Stable-v1.0.0 organiza exemplos em `apps/<App>/`, `docs/L3_Vulcan/` e um mecanismo explícito de entrada; seus exemplos usam `entities/`, `usecases/`, `tools/`, `boundaries/` e `composition/`. Fonte: `versioning/Stable-v1.0.0/README.md` e `examples/minimal/`, inspecionados em 22/11/2026.
- F003: A conformidade formal dessa edição exige uma árvore Minerva completa e mapeamentos módulo→arquivo/símbolo em `realization.json`. AetherDesk, por escolha explícita de escopo, não alegará conformidade formal nem criará um ledger Minerva fictício. Fonte: `AGENTS.md` e `versioning/Stable-v1.0.0/README.md` locais.
- F004: O texto inicial propõe React/TypeScript, Monaco, xterm.js e runtime de isolamento, mas não fixa implementação nem políticas de ciclo de vida, ferramentas ou cópias de segurança. Fonte: texto de requisitos fornecido pelo usuário.

## Escopo <!-- wop:section scope -->

### Incluído

- Aplicação `apps/AetherDesk/` com núcleo Python organizado pelas responsabilidades Vulcan; interface React/TypeScript em `web/`, tratada como adaptador de interação; `launch.py` ou entrada equivalente com registro explícito; documentação de decisões e evidências em `docs/L3_Vulcan/`.
- Primeira configuração, login, sessões, papéis Administrador/Membro, permissões individuais, provisionamento e isolamento de ambientes, arquivos, editor, terminais, monitor, painel administrativo, preferências, auditoria, instalação Linux com HTTPS e início automático, backup/restauração e testes.
- Ambiente de homologação Linux com runtime de isolamento e dados de teste; artefatos de implantação para um servidor de produção, sem efetuar a implantação remota nesta execução do plano.

### Excluído

- Modelos, árvores, geradores e declarações de conformidade Atlas/Minerva; alterações no repositório Olympus/Vulcan.
- Compartilhamento entre contas, lixeira, IDE com extensões/depuração, proxy de aplicações web dos usuários, GPU, histórico longo de métricas, acesso administrativo implícito a arquivos/terminais alheios e controle de processos pelo monitor.

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
- R011: Serviço inicia no Linux após boot, usa HTTPS e separa segredos dos diretórios de trabalho dos usuários.
- R012: Eventos administrativos registram ator, operação, alvo e instante sem capturar conteúdo de arquivos ou terminais.
- R013: Interface expõe carregamento, salvamento, falha, desconexão e reconexão; tema, janelas abertas e suas posições persistem e são restaurados após novo login.
- R014: A primeira versão demonstra os 14 comportamentos de aceite do texto inicial, inclusive isolamento de dois usuários, duas sessões simultâneas da mesma conta, persistência, autorização negativa e restrições válidas no terminal.

## Restrições <!-- wop:section constraints -->

- C001: Não alterar nem gerar artefatos Atlas/Minerva; não declarar conformidade Vulcan Stable-v1.0.0 sem seus pré-requisitos. Reutilizar sua organização e princípios de código como adaptação identificada.
- C002: Cada operação usa identidade autenticada obtida do servidor; IDs e caminhos enviados pelo navegador não definem propriedade ou raiz.
- C003: Restrições de dados que devem valer para qualquer programa são impostas pelo ambiente e sistema de arquivos, além da API; ocultar um botão não basta.
- C004: Nunca usar comandos ou arquivos pessoais de usuários como registro administrativo básico.

## Decisões <!-- wop:section decisions -->

- D001: AetherDesk é uma aplicação independente que adota a organização Vulcan; sua fonte de requisitos é este plano, não um módulo Minerva. Não gerar `realization.json` ou `knowledge-graph.json` com linhagem Minerva inventada. Revisitar somente se o escopo incluir Minerva.
- D002: Usar um único registro de composição do backend e contratos explícitos entre núcleo, infraestrutura e adaptadores. `Boundary` nomeia apenas entrada HTTP/WebSocket; casos de uso autorizam o contexto confiável antes de causar efeitos. Revisitar se a edição remota verificada mudar essas regras.
- D003: Separar dados persistentes de imagem/base recriável; preservar arquivos na desativação e exclusão lógica. Logout e revogação não param processos; parada de sessão e exclusão os encerram. I001 fixa os contratos.

## Premissas <!-- wop:section assumptions -->

- A001: Um único servidor Linux atende o grupo privado na primeira versão. O protótipo W001 usa Docker Desktop com daemon Linux; W004 requer host Linux de homologação identificado para instalação e medições finais.
- A002: O backend será Python para preservar diretamente a estrutura e os contratos de código demonstrados em Vulcan; o frontend será React/TypeScript como adaptador web. W001 confirma compatibilidade com o ambiente e registra qualquer adaptação antes de W002.
- A003: A primeira versão usa monitoramento atual e uma janela curta de amostras em memória. Persistência de histórico só entra por revisão do plano.

## Incógnitas <!-- wop:section unknowns -->

- U001: Resolvida em W001 para o commit remoto `4ab5824a7c7c962e96ac4480e8c254d023ba75df` e os 177 arquivos rastreados da edição Stable-v1.0.0; I001 registra limites da comparação e da adaptação.
- U002: O protótipo em Docker Linux demonstrou raiz pessoal e persistência, mas runtime, ferramentas, quotas e capacidade do host de homologação final ainda exigem validação. Falha de isolamento bloqueia o portão.
- U003: Resolvida pelo responsável em 22/11/2026: logout e revogação administrativa de sessão não param processos, PTYs ou desktop; novo login restaura janelas e posições. Parar sessão cancela processos. Excluir usuário para processos e preserva arquivos. I001 formaliza transições.
- U004: Resolvida pelo responsável em 22/11/2026: backup é configurável na aplicação e desativado por padrão; frequência, destino e retenção por prazo ou substituição são escolhas administrativas. O destino de teste para homologação será definido em W004.

## Riscos <!-- wop:section risks -->

| Risco | Probabilidade | Impacto | Prevenção | Detecção | Responsável |
|---|---|---|---|---|---|
| Escape do ambiente ou acesso cruzado por path, symlink, API ou PTY | Média | Crítico | Isolamento Linux, identidade servidor, testes negativos e privilégios mínimos | Suíte de isolamento e revisão do modelo de ameaça | Implementação de runtime e segurança |
| Perda de arquivos em atualização, exclusão ou restauração | Média | Alto | Volumes persistentes, operações explícitas, cópias e ensaio de restauração | Verificação de hashes e jornada de recuperação | Operação |
| Credenciais ou tokens expostos em logs/terminal | Média | Alto | Armazenamento fora dos ambientes e redação de logs | Testes de vazamento e revisão de auditoria | Implementação de identidade |
| Corrida no primeiro acesso ou revogação tardia | Média | Alto | Provisionamento idempotente e checagem contínua de autorização | Testes concorrentes e de WebSocket aberto | Integração |
| Referência Vulcan local diverge do remoto | Média | Médio | Fixar identidade da fonte em W001 e limitar alegação arquitetural | Comparação de edição, estado e hashes | Responsável técnico |
| Host de homologação não suporta isolamento/medição esperados | Média | Alto | Protótipo W001 e métricas com indisponibilidade explícita | Gate de capacidade antes de W002 | Operação |

## Ambientes e operação <!-- wop:section operations -->

Desenvolvimento usa dados fictícios e testes sem privilégios do hospedeiro. Homologação usa Linux com runtime de isolamento, TLS de teste, armazenamento persistente isolado, contas de teste e coleta de métricas. Produção, quando autorizada separadamente, recebe configuração própria, segredos fora dos volumes dos usuários, início automático, HTTPS, política de backup e runbook. W001 registra versões do SO/runtime e capacidade; W004 documenta instalação, atualização, reversão, restauração, logs, métricas e diagnóstico. Testes destrutivos ou de fuga rodam apenas em ambiente descartável autorizado, nunca em dados reais.

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
| R011 | Texto inicial §11 | I001, I009 | Serviço/TLS | Boot e inspeção de segredos | Instalação Linux |
| R012 | Texto inicial §11 | I002, I008, I009 | Auditoria | Evento ator/operação/alvo/hora e ausência de conteúdo | Responsabilização |
| R013 | Texto inicial §2 e decisão de 22/11/2026 | I004, I008, I009 | Estados/preferências | Janelas e posições restauradas após novo login | Continuidade da experiência |
| R014 | Texto inicial §13 | I001–I009 | Matriz e2e | 14 cenários em homologação | Aceite funcional |

## Estratégia de verificação <!-- wop:section verification_strategy -->

Executar verificações estáticas e testes unitários para regras puras; integração para banco, filesystem, runtime e PTY; contratos para Boundary/casos de uso/cliente; e2e para jornadas críticas em Linux. Fixtures isolam conta, banco, volume, porta, tempo e métricas por item. Cenários de falha incluem gravação de resultado desconhecido, provisionamento concorrente, quota/armazenamento indisponível, perda de conexão, revogação e restauração. O orçamento de desempenho é definido em W001 com número de usuários, volume de arquivos, sessões e intervalo de coleta; W004 mede percentis e consumo no host identificado. Nenhum teste simulado substitui a prova Linux de `/` e de processos.

## Reversão e recuperação <!-- wop:section rollback_recovery -->

Antes de migração ou atualização, criar cópia verificável de banco, configurações e volumes persistentes em homologação. Se migração, montagem ou teste de isolamento falhar, parar a versão nova, restaurar binários/configuração anterior e dados conforme política de consistência documentada; verificar login, permissões e hashes de arquivos de duas contas. Mudanças de esquema irreversíveis exigem migração de retorno ou estratégia de avanço controlado antes da execução. Desativar conta não apaga dados. Produção terá ensaio e autorização próprios.

## Aceite final <!-- wop:section final_acceptance -->

- Todos os portões W001–W004 passaram em ordem e cada item tem evidência real identificada.
- R001–R014 estão demonstrados; os 14 cenários da primeira versão passaram em Linux e as telas de login, desktop, Explorador, editor, terminal, monitores, administração e configurações foram inspecionadas.
- Isolamento, autorização, persistência, HTTPS, início automático, backup/restauração e orçamento de carga passaram; falhas ou limitações residuais são explícitas.
- O responsável pelo produto registra aceite funcional sobre a evidência; execução técnica e aceite humano mantêm estados distintos.

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

- Explorador/editor, terminais, monitor e administração passam contratos, fluxos positivos, erros e verificações negativas de permissão em fixtures independentes.
- Cada módulo exporta Boundary, casos de uso, ferramentas e componente web sem modificar a composição compartilhada; o portão integra os registros e confirma que os quatro podem abrir no shell.

### Portão de conclusão <!-- wop:field completion_gate -->

I005–I008 aceitos individualmente; integração de exports e rotas no portão passa; nenhuma leitura cruzada, sobrescrita silenciosa ou vazamento de métrica fica aberto. W004 só inicia após registro dessa evidência.

### Evidências exigidas <!-- wop:field evidence_requirements -->

- Suítes de contrato, integração e UI de cada módulo, cenários negativos, capturas de telas e relatório do registro integrado.

### Integração e passagem <!-- wop:field integration_handoff -->

Entregar módulos registrados, matriz de permissões implementada, contratos de erro/eventos e comandos de teste para a jornada completa de I009.

<!-- wop:prompt-completion-item I005 -->
#### Item I005 — Explorador e editor

##### Critérios de aceite <!-- wop:field acceptance_criteria -->

- Suíte cobre todas as operações de R005, `Ctrl+S`, abas, conflito externo, caminho relativo, symlink, tentativa de atravessar raiz, substituição explícita e arquivo criado por fixture Bash aparecendo no Explorer.

##### Evidência de verificação <!-- wop:field verification_evidence -->

- Testes de contrato/integração/UI, roteiro de concorrência e captura dos estados de conflito.

##### Requisitos de passagem <!-- wop:field handoff_requirements -->

- Exportar rotas, componente web, eventos e contratos de conflito para I009.

<!-- wop:prompt-completion-item I006 -->
#### Item I006 — Terminal Bash

##### Critérios de aceite <!-- wop:field acceptance_criteria -->

- Duas sessões da mesma conta mantêm cwd/estado distintos e veem os mesmos arquivos; logout/revogação da sessão web mantêm PTYs e processos ativos para reconexão após novo login, enquanto parada de sessão os encerra; `Ctrl+C`, resize e fechamento explícito funcionam; outro usuário e permissão revogada não conseguem conectar ao PTY existente.

##### Evidência de verificação <!-- wop:field verification_evidence -->

- Testes PTY/WebSocket, cenário de revogação em conexão aberta e inspeção de terminal no navegador.

##### Requisitos de passagem <!-- wop:field handoff_requirements -->

- Exportar rotas, eventos de ciclo de vida e componente terminal para I009.

<!-- wop:prompt-completion-item I007 -->
#### Item I007 — Monitor de recursos

##### Critérios de aceite <!-- wop:field acceptance_criteria -->

- Testes demonstram atribuição correta a dois ambientes, consumo compartilhado separado, unidades e carimbo temporal, métrica indisponível explícita, ordenação e negação de visão por usuário/processos sem permissão.

##### Evidência de verificação <!-- wop:field verification_evidence -->

- Fixtures de métricas, testes de autorização/apresentação e capturas das três visões.

##### Requisitos de passagem <!-- wop:field handoff_requirements -->

- Exportar rotas, formatos e frequência de coleta para I009.

<!-- wop:prompt-completion-item I008 -->
#### Item I008 — Administração e preferências

##### Critérios de aceite <!-- wop:field acceptance_criteria -->

- Administrador cria/edita/desativa/exclui logicamente conta, revoga autenticação sem parar processos, para sessão encerrando processos, configura frequência/destino/retenção de backup, vê permissões efetivas e retenta ambiente falho sem duplicar dados; membro não acessa rotas administrativas; preferências persistem; ação de impacto nomeia alvo e consequência.

##### Evidência de verificação <!-- wop:field verification_evidence -->

- Testes de rotas/UI, captura da confirmação e auditoria produzida por ações de teste.

##### Requisitos de passagem <!-- wop:field handoff_requirements -->

- Exportar telas/rotas e roteiro administrativo para I009.
