---
artifact: wop-wave-prompt
plan_id: a47c4d01-5e49-4b24-aaaf-2535f78447e0
plan_version: 2
plan_title: "Implementar o AetherDesk com organização Vulcan"
wave_id: W001
authorized_items: I001
non_authorized_items: "I002,I003,I004,I005,I006,I007,I008,I009"
predecessor_waves: none
blocked_successor_waves: "W002,W003,W004"
language: pt-BR
source_readme: README.md
source_readme_sha256: 58690bbdbb9486101f0a21f6c3759c8be4abac840a930910d7221140739b0fa6
---

# Onda W001 — Contratos e prova de viabilidade

<!-- wop:prompt-section global_protocol -->
## Protocolo de execução <!-- wop:section execution_protocol -->

Identifique o pacote e leia `README.md` e todos os prompts de onda referenciados. Execute as ondas em ordem estrita; não avance antes de todos os itens da onda concluírem, serem aceitos individualmente, integrados quando necessário e de o portão passar. Integre resultados, registre evidências e transições de estado, bloqueie mudanças de escopo ou efeitos externos não autorizados e avalie o aceite final. Use somente o paralelismo cuja independência esteja demonstrada na onda correspondente.

<!-- wop:prompt-section execution_scope -->
<!-- wop:prompt-assigned-wave W001 -->
### Objetivo geral <!-- wop:field general_objective -->

Fixar a referência arquitetural, as políticas ainda abertas, os contratos de módulos e uma prova de isolamento Linux antes de construir o produto.

### Requisitos atendidos <!-- wop:field requirements_addressed -->

- R002, R003, R004, R007, R010, R011, R014.

### Instruções de execução da onda <!-- wop:field execution_instructions -->

Execute apenas I001. Fixe os contratos e produza a prova Linux; entregue a decisão e a evidência ao portão da onda. Não inicie implementação de módulos posteriores.

### Justificativa de paralelismo <!-- wop:field parallelism_rationale -->

Item único: decisões de arquitetura, isolamento e contratos são dependências conjuntas da implementação.

### Limites de propriedade <!-- wop:field ownership_boundaries -->

I001 pode criar somente o esqueleto e os documentos/fixtures de descoberta do AetherDesk. A cópia Olympus é somente leitura.

<!-- wop:prompt-assigned-item I001 -->
#### Item I001 — Referência, políticas e contratos

##### Objetivo <!-- wop:field objective -->

Produzir um desenho implementável do AetherDesk que preserve a organização Vulcan sem depender de Atlas ou Minerva.

##### Contexto <!-- wop:field context -->

A fonte local Stable-v1.0.0 está não rastreada na cópia Olympus; o clone remoto do commit `4ab5824a7c7c962e96ac4480e8c254d023ba75df` teve os 177 arquivos rastreados dessa edição comparados sem diferenças. Isto não é declaração de conformidade AetherDesk.

##### Entradas e pré-requisitos <!-- wop:field inputs_prerequisites -->

- Requisitos R001–R014, URL e clone remoto verificados, cópia local Vulcan, Docker Linux descartável e decisões do responsável sobre U003/U004 registradas em 22/11/2026.

##### Escopo <!-- wop:field scope -->

- Registrar a edição/estado da referência; definir stack, layout, APIs e eventos, modelo de dados/ownership, fluxo de autenticação, transições distintas de logout/revogação/parada/exclusão, persistência do desktop, ferramentas, limites, backup configurável, observabilidade e orçamento de carga; provar raiz `/` e separação de usuários.

##### Propriedade <!-- wop:field ownership -->

- Possui `docs/L3_Vulcan/`, protótipo descartável e contratos iniciais; não edita código ou histórico de Olympus.

##### Saídas <!-- wop:field outputs -->

- Documentos e contratos GC001–GC005 refinados, matriz de permissões, tabela de transições de ambiente, mapa de persistência, decisão de runtime, orçamento de carga, relatório do protótipo e inventário de ownership por módulo.

##### Restrições <!-- wop:field restrictions -->

- Limitar a equivalência remota aos 177 arquivos rastreados e comparados da edição Stable-v1.0.0; não gravar no repositório Olympus.

<!-- wop:prompt-section predecessor_verification -->
### Pré-requisitos <!-- wop:field prerequisites -->

Nenhuma onda anterior. A URL Vulcan, o clone do commit remoto identificado e a cópia local são entradas de inspeção; limitar qualquer alegação à edição e aos arquivos efetivamente comparados.

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

- Uma decisão de arquitetura identifica edição/estado/fonte Vulcan, a adaptação sem Minerva, layout, contratos públicos, modelo de ameaça e limites; cada incógnita U001–U004 tem decisão ou bloqueio explícito.
- Um protótipo em Linux demonstra que `cd /` e leitura de `/dados.txt` permanecem no ambiente correto para dois usuários e que atualização da base não apaga dados persistentes.

### Portão de conclusão <!-- wop:field completion_gate -->

I001 aceito com evidências reproduzíveis; decisões do responsável sobre processos, dados e backup incorporadas; nenhum contrato necessário a W002 permanece indefinido. Falha de isolamento ou divergência arquitetural material bloqueia W002.

### Evidências exigidas <!-- wop:field evidence_requirements -->

- `docs/L3_Vulcan/architecture.md`, `decision-record.md`, contratos versionados, modelo de ameaça, relatório do protótipo com comandos/ambiente/resultados e registro da fonte Vulcan.

### Integração e passagem <!-- wop:field integration_handoff -->

Congele interfaces para identidade, ambiente, arquivos, PTY, métricas, auditoria e cliente web, além de ownership de arquivos e migrações. Entregue decisões D001–D003 confirmadas ou revisadas e comandos de verificação do protótipo.

<!-- wop:prompt-completion-item I001 -->
#### Item I001 — Referência, políticas e contratos

##### Critérios de aceite <!-- wop:field acceptance_criteria -->

- Cada contrato consumido em W002/W003 define entrada, saída, falha, identidade e versão; relatório reproduz dois usuários com mesmo caminho e conteúdo diferente, raiz correta para shell e programa e persistência após recriação.
- O orçamento de carga declara usuários simultâneos, arquivos, terminais, intervalo de amostragem, ambiente de medição e limites de latência/consumo para W004.
- A fonte Vulcan tem identidade verificável ou o limite de verificação é documentado e aceito como restrição de referência; nenhuma afirmação de conformidade depende de Minerva ausente.

##### Evidência de verificação <!-- wop:field verification_evidence -->

- Hashes/estado/edição da fonte, revisão do desenho, comandos e saídas do protótipo em Linux, registro de decisão de políticas pelo responsável.

##### Requisitos de passagem <!-- wop:field handoff_requirements -->

- Entregar contratos congelados, ownership de diretórios, fixtures independentes e decisões operacionais aos itens I002–I008.
