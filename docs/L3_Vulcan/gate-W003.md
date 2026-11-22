# Portão W003 — módulos e integração

Data: 22/11/2026. Resultado técnico: **passou** para I005–I008. A W004 permanece separada e depende de homologação Linux final e aceite do responsável.

| Item | Export e verificação | Resultado |
|---|---|---|
| I005 Arquivos/editor | `files/http.py`, `gateway.py`, agente Linux com `openat2`; Explorer e Monaco. Testes Linux de operações, conflito, mudança pelo Bash, traversal e symlink; teste HTTP com dois contêineres, upload/download, conteúdo distinto, conflito e limite de 8 MiB; inspeção visual do editor em fixture e Explorador com raiz real. | Aceito |
| I006 Terminal | `terminal/service.py`, `http.py`, xterm.js. PTYs reais em tmux, duas sessões, resize, Ctrl+C, logout/reconexão, revogação de WebSocket aberto, propriedade e fechamento; inspeção no navegador real com `pwd` em `/persist`. | Aceito |
| I007 Monitor | `monitor/service.py`, `http.py`, tela com visões própria/servidor/contas. Teste de atribuição, negação e indisponibilidade; inspeção no navegador da leitura de contêiner e host com unidades/carimbo. CPU compartilhada permanece explicitamente indisponível porque as referências de CPU não são comparáveis. | Aceito |
| I008 Administração/preferências | `administration/service.py`, `http.py`, telas de contas, permissões, sessões, backup e tema. Teste de estado do desktop, padrão de backup desativado, duas modalidades de retenção, autorização e parada; inspeção no navegador de contas, permissões, sessões e retentativa de ambiente. | Aceito |

## Integração no portão

- `launch.py` registra os quatro roteadores, identidade, broker Docker, composição e estado pessoal. O cliente `web/src/clients.ts` liga os aplicativos às rotas; `web/src/shell.tsx` preserva janelas e posições na conta.
- A imagem `aetherdesk-files:w003` inclui Bash, tmux e agente Python. O agente roda dentro do contêiner da conta, sem aceitar `account_id` do navegador. O backend local foi observado com cookie/CSRF, Explorer listando `/`, terminal WebSocket e monitor ativo.
- `pnpm build` concluiu com TypeScript válido em 22/11/2026. O bundle inicial gerado é grande (4,68 MiB JS antes de gzip) por Monaco; otimização e medição de carga pertencem a W004.
- Suíte conjunta W002/W003: 14 testes executados; 13 passaram, e 1 falhou por expectativa antiga do novo evento `account.created`. A expectativa foi corrigida e os 4 testes de identidade passaram em repetição. O teste HTTP de arquivos foi repetido após adicionar streaming limitado e passou. Os 2 testes Linux de `LinuxFileService` passaram em `python:3.13-slim` com rede desligada e root somente leitura. Esses resultados não substituem a execução final da suíte após os ajustes de W004.

## Contratos entregues a I009

- Arquivos: caminhos absolutos do namespace pessoal; limite de 8 MiB por transferência; conflito `409`, revisão stale `412`, upload em fluxo com buffer limitado; `replace=true` exige ação explícita na UI.
- Terminal: IDs UUID por conta, PTY tmux persistente em logout/revogação, WebSocket fechado quando a autenticação é revogada; parada de sessão encerra o contêiner/processos.
- Métricas: amostragem sob demanda a cada 5 s na UI, até 30 amostras recentes em memória; valor `null` representa ausência de medição. Visões servidor/contas exigem capacidades próprias.
- Administração: estado do desktop por conta em SQLite; backup desativado por padrão, frequência em horas, destino absoluto, retenção `replace` ou `days`; execução automática e restauração pertencem a I009.

## Pendências direcionadas a W004

Executar a matriz S01–S14 e o teste de carga em host Linux de homologação; implementar e ensaiar backup/restauração; provar TLS/boot/systemd; revisar segurança, volume de arquivos, consistência em concorrência e bundle; obter aceite funcional do responsável. O responsável confirmou que **ainda não há host Linux** para essa etapa. O Docker Linux local foi usado apenas como ambiente descartável de isolamento e integração.
