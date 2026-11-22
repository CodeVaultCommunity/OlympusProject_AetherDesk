# W004 — integração e homologação local WSL (portão técnico aprovado)

Data: 22/11/2026. I009 foi implementado e verificado primeiro em Docker Linux sobre Windows. Na versão 3 do plano WOP, o responsável transferiu a homologação conclusiva deste pacote para uma distribuição WSL 2 descartável neste PC. A Ubuntu 24.04.5 dedicada foi instalada; os 14 cenários, systemd após reabertura da distribuição, HTTPS/WSS local, backup agendado, atualização/reversão e orçamento de carga local passaram. Boot, certificado público, rede e capacidade de um servidor independente pertencem à validação posterior, antes da produção.

## Matriz funcional local

Comando: `AETHERDESK_DOCKER_TEST=1 uv run python -m unittest apps.AetherDesk.composition.test_scenarios_local -v`. Resultado: `Ran 1 test ... OK` (41,849 s) em Docker Engine Linux 28.3.3; todos os checkpoints abaixo são `assert` da mesma jornada, com contêineres e volumes descartáveis.

| Cenário | Procedimento/evidência local | Resultado local | WSL 2 |
|---|---|---|---|
| S01 | POST administrativo cria Alice; broker informa ambiente `running`. | Passou | Passou |
| S02 | Alice e Bob entram na mesma aplicação com UUID/volume distintos. | Passou | Passou |
| S03 | Ambos criam `/persist/same.txt`; downloads retornam `alice`/`bobby`. | Passou | Passou |
| S04 | `bash -lc 'cd /; pwd; cat /persist/same.txt'` retorna `/` e conteúdo próprio. | Passou | Passou |
| S05 | Bash cria `/persist/from-bash.py`; Explorer lista e editor lê `print(7)`. | Passou | Passou |
| S06 | Programa `cat` no ambiente lê somente o volume próprio. | Passou | Passou |
| S07 | Dois tmux PTYs da Alice preservam cwd `/` e `/persist`; arquivo é comum. | Passou | Passou |
| S08 | Segundo login de Alice usa mesmo account_id, contêiner e volume. | Passou | Passou |
| S09 | Parada do ambiente fecha registros PTY; reinício mantém `same.txt`. | Passou | Passou |
| S10 | Membro recebe 403 ao solicitar conta alheia; attach de PTY alheio falha. | Passou | Passou |
| S11 | `/metrics/self` atribui referência ao UUID correto. | Passou | Passou |
| S12 | Membro recebe 403 nas visões servidor e contas. | Passou | Passou |
| S13 | Revogação de `terminal.control` fecha WebSocket já aberto. | Passou | Passou |
| S14 | Bash de Bob não lê caminho do volume de Alice no host; conteúdo pessoal permanece Bob. | Passou | Passou |

## Outras evidências locais

- Em Ubuntu WSL 2 24.04.5, Docker Engine nativo 29.1.3, Caddy 2.6.2 e Python 3.12.3: `AETHERDESK_DOCKER_TEST=1 .venv/bin/python -m unittest apps.AetherDesk.composition.test_scenarios_local -v` passou S01–S14 em 36,774 s. A suíte ampliada passou 20 testes em 184,868 s; três testes com limpeza de recursos corrigida passaram novamente em 60,206 s, deixando apenas o ambiente da conta de homologação.
- `systemctl is-active docker caddy aetherdesk` retornou três estados `active`; após `wsl --terminate Ubuntu-24.04` e nova abertura, os três voltaram a `active`, login e terminal funcionaram. A primeira chamada ocorreu antes de o backend ficar pronto e recebeu 502 transitório; o verificador agora aguarda `/healthz`.
- `scripts/verify_wsl_service.py` passou por `https://localhost` com a CA local explicitamente confiada: login, cookies `Secure`, backup inicialmente desativado e PTY por `wss://`. `scripts/verify_wsl_backup_schedule.py` ativou temporariamente a política, observou snapshot agendado com manifesto/hashes e arquivo esperado no volume, e voltou a desativá-la.
- `scripts/verify_wsl_upgrade_rollback.py` ensaiou versão temporária `0.1.0-wsl-trial`, reinício, login e leitura do arquivo; reverteu para `0.1.0`, confirmou hash original do código e arquivo preservado. Não houve migração de esquema nesse ensaio; a migração v1→v2 tem teste separado.
- A interface visual já havia sido inspecionada no navegador com o build local; `diff -rq` confirmou que toda a árvore `web/dist/` copiada para o WSL é idêntica. A API instalada foi percorrida em HTTPS/WSS. O navegador Windows não alcançou `localhost:8174` do WSL nesta sessão; não há inspeção visual independente através da instalação WSL.
- O teste de restauração ampliado em WSL passou com Alice e Bob, mesmo caminho e conteúdos distintos, permissão `terminal.open` negada ainda negada e preferências da Alice recuperadas. `stat` confirmou `0600 root:root` em ambos os arquivos de segredos e `0700 aetherdesk:aetherdesk` para dados e backups.

## Orçamento de carga local declarado antes da medição

O ensaio `scripts/measure_wsl_service.py` usa 8 membros simultâneos, 100 arquivos pequenos e um arquivo de 1 MiB por membro, 24 amostras de login e 160 amostras por rota com 8 solicitações concorrentes por rodada. A primeira execução adotou as metas propostas para o servidor independente: p95 login < 1.000 ms; listagem de 100 itens < 500 ms; download de 1 MiB < 1.000 ms; métricas pessoais < 500 ms. **As quatro falharam no WSL**: p95 respectivamente 4.406,4 ms, 1.831,3 ms, 1.527,0 ms e 2.108,0 ms. A verificação do código mostrou Argon2id com 64 MiB e três passagens por login, agente de arquivos iniciado por operação Docker e coleta de métricas por ambiente; reduzir o custo de senha enfraqueceria a segurança. Os oito contêineres e volumes de carga foram removidos.

Antes da segunda medição, o orçamento **local WSL** foi revisado como guarda de regressão sob essa virtualização e carga: p95 login < 6.000 ms; listagem < 2.500 ms; download < 2.000 ms; métricas < 3.000 ms. Esses números não substituem as metas originais do servidor independente e registram a lentidão observada como risco de experiência. Registrar p50, p95, máximo, versão do ambiente e falhas. Este perfil WSL é menor que os 10.000 arquivos e 2 GiB por conta propostos para o futuro servidor; não autoriza inferir sua capacidade. O eco de PTY e o custo da coleta também serão medidos separadamente ou registrados como limites antes do portão.

A segunda execução com o mesmo perfil passou nas quatro guardas locais: p95 login 1.032,8 ms (24 amostras), listagem 1.473,3 ms, download 1.016,2 ms e métricas 2.063,4 ms (160 amostras por rota). P50 respectivos: 553,8 ms, 627,4 ms, 509,0 ms e 132,5 ms. O contraste entre as duas rodadas indica aquecimento/variação relevante; não extrapolar para disponibilidade ou capacidade contínua. Após o ensaio, o WSL reabriu e Docker levou tempo para atingir `active`; o contêiner persistente do administrador foi preservado e os oito de carga foram removidos.

Medições específicas: `scripts/measure_wsl_pty.py` registrou 20 ecos WSS, p50 8,3 ms, p95 24,1 ms e máximo 35,1 ms, abaixo da proposta de 150 ms. `scripts/measure_wsl_metrics_cost.py` registrou 30 coletas, p50 46,2 ms, p95 85,2 ms e 0,33% das 16 CPUs para AetherDesk + dockerd durante 7,4 s, abaixo da proposta local de 2%. São ensaios de uma conta, separados da carga de oito usuários.

## Rastreabilidade do aceite local

| Requisito | Evidência WSL ou evidência de interface equivalente |
|---|---|
| R001, R013 | `test_http_integrated.py`, build web idêntico ao inspecionado no navegador, login HTTPS e desktop persistido |
| R002, R003, R014 | S01–S14, `test_docker.py`, `test_app.py`; contas, raiz, isolamento e ciclo de vida |
| R004, R007 | Testes de identidade e terminal HTTP/WS; revogação contínua, PTY WSS e eco |
| R005, R006 | Testes de gateway, HTTP e agente de arquivos; Explorer/editor inspecionados no build idêntico |
| R008 | Testes de monitor, S11–S12, carga de métricas e amostra de CPU |
| R009, R012 | Testes de administração/identidade e auditoria; painel inspecionado no build idêntico |
| R010 | `test_service.py` de backup com duas contas, agendamento, restauração, retenções e reabertura da distribuição |
| R011 | Unidade systemd ativa após reabrir WSL, HTTPS/WSS com CA local, cookies Secure e segredos `0600`; boot de servidor independente fora do aceite desta versão |

- `test_http_integrated.py`: login, janelas/posições/tema persistidos, backup desativado por padrão, configuração e CSRF.
- `test_http.py` de arquivos: dois contêineres, upload/download, conflito 409, traversal negado e 413 acima de 8 MiB; `test_service.py` de arquivos rodou em `python:3.13-slim` Linux, rede desligada e root somente leitura.
- Terminal: duas sessões, resize, Ctrl+C, logout/reconexão e revogação de WebSocket. Inspeção no navegador local confirmou prompt Bash, `pwd` em `/persist`, Explorer listando `/`, monitor com carimbo/unidades e painel administrativo com sessões/permissões. A falha inicial de conexão ao navegador revelou dependência WebSocket ausente; `websockets` foi adicionada e a conexão foi repetida com sucesso.
- `test_service.py` de backup: snapshot de SQLite e volumes, SHA-256, retenção por dias e substituição, restauração de login, preferências e arquivo em volume descartável. A extração precisou preparar a propriedade do novo volume; a correção foi repetida com sucesso. A execução automática por configuração foi implementada, mas não foi ensaiada num host Linux que permaneça ligado por múltiplos ciclos.
- Identidade: migração v1→v2 preserva contas, expira tokens antigos e aplica 12 h às novas sessões; testes passaram. Logout/revogação não cancelam processos, parada e exclusão os encerram e preservam arquivos.
- `pnpm build` passou após carregamento sob demanda de Monaco/xterm. Bundle inicial: 243,84 KiB JS bruto (76,26 KiB gzip); editor carregado depois: 4,10 MiB JS bruto. Medir cache/primeira abertura no host final.
- Medição local, 20 amostras por rota, Windows 11 + Docker Linux 28.3.3, 16 CPUs lógicas, 42,8 GB RAM. Antes do cache, p95: desktop 51,1 ms, arquivos 1.064,7 ms, métricas 4.069,4 ms. Após cache de 4 s por ambiente, p95: desktop 22,6 ms, arquivos 568,9 ms, métricas 364,3 ms; máximo de métricas ainda 2.084 ms na coleta real. São amostras provisórias, sem concorrência definida nem orçamento aceito pelo responsável.

## Revisão de segurança e limites

- Confirmado localmente: IDs de conta/ambiente derivados do contexto autenticado; `openat2` limita caminhos e nega magic links/traversal; processos rodam como UID 10001 com rede desligada, root read-only, sem capacidades, limites de memória/CPU/PIDs; WS revalida sessão/permissão; mutações HTTP verificam CSRF e Origin; auditoria não registra conteúdo de arquivos/terminal; sessão no banco expira em 12 h.
- **Risco alto para produção:** o serviço pertence ao grupo `docker`, que concede controle amplo do host. A fronteira deve ser reduzida ou aceita explicitamente após revisão no host; configuração atual é adequada somente à homologação descartável.
- Backup de arquivo em alteração é best-effort e não é snapshot atômico. O ensaio foi quiescente; host final precisa definir consistência para cargas ativas.
- Métricas de CPU compartilhada ficam indisponíveis quando fontes têm denominadores diferentes. A UI mostra `null`/indisponível, não zero. Métricas de host local não representam o servidor Linux futuro.
- O limite de 8 MiB e o agente Python executado por operação simplificam segurança, mas elevam latência; quotas de armazenamento por usuário ainda dependem de configuração/validação no host.
- TLS, cookies `Secure` sob proxy, WebSocket `wss`, Caddy, systemd após reboot, permissões do arquivo de segredos, backup agendado/restore no host e rollback ainda não foram executados. [Procedimento preparado](operations.md).

## Decisão do portão

**Aprovado tecnicamente para a versão local WSL.** Executor: Codex, em 22/11/2026. A inspeção visual do mesmo build estático, confirmada por comparação integral da árvore, combinada com HTTPS/WSS e APIs instaladas no WSL, satisfaz o critério de interface deste pacote; a ausência de acesso do navegador Windows diretamente à instalação WSL fica registrada como limite. Todos os 14 cenários e os ensaios locais do portão passaram após as correções. Não há aceite humano nem autorização de produção implícitos. As provas de boot, rede, quotas, segurança do grupo Docker e desempenho de um servidor independente continuam obrigatórias antes da implantação; produção não foi ativada.
