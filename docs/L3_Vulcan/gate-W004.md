# W004 — integração e homologação (portão pendente)

Data: 22/11/2026. I009 foi implementado e verificado **localmente em Docker Linux sobre Windows**. Na versão 3 do plano WOP, o responsável transferiu a homologação conclusiva deste pacote para uma distribuição WSL 2 descartável neste PC. O portão W004 **ainda não passou**: não há distribuição WSL instalada nem evidência de instalação, systemd, HTTPS local, restauração agendada e carga nesse ambiente. Boot, certificado público, rede e capacidade de um servidor independente pertencem à validação posterior, antes da produção.

## Matriz funcional local

Comando: `AETHERDESK_DOCKER_TEST=1 uv run python -m unittest apps.AetherDesk.composition.test_scenarios_local -v`. Resultado: `Ran 1 test ... OK` (41,849 s) em Docker Engine Linux 28.3.3; todos os checkpoints abaixo são `assert` da mesma jornada, com contêineres e volumes descartáveis.

| Cenário | Procedimento/evidência local | Resultado local | WSL 2 |
|---|---|---|---|
| S01 | POST administrativo cria Alice; broker informa ambiente `running`. | Passou | Pendente |
| S02 | Alice e Bob entram na mesma aplicação com UUID/volume distintos. | Passou | Pendente |
| S03 | Ambos criam `/persist/same.txt`; downloads retornam `alice`/`bobby`. | Passou | Pendente |
| S04 | `bash -lc 'cd /; pwd; cat /persist/same.txt'` retorna `/` e conteúdo próprio. | Passou | Pendente |
| S05 | Bash cria `/persist/from-bash.py`; Explorer lista e editor lê `print(7)`. | Passou | Pendente |
| S06 | Programa `cat` no ambiente lê somente o volume próprio. | Passou | Pendente |
| S07 | Dois tmux PTYs da Alice preservam cwd `/` e `/persist`; arquivo é comum. | Passou | Pendente |
| S08 | Segundo login de Alice usa mesmo account_id, contêiner e volume. | Passou | Pendente |
| S09 | Parada do ambiente fecha registros PTY; reinício mantém `same.txt`. | Passou | Pendente |
| S10 | Membro recebe 403 ao solicitar conta alheia; attach de PTY alheio falha. | Passou | Pendente |
| S11 | `/metrics/self` atribui referência ao UUID correto. | Passou | Pendente |
| S12 | Membro recebe 403 nas visões servidor e contas. | Passou | Pendente |
| S13 | Revogação de `terminal.control` fecha WebSocket já aberto. | Passou | Pendente |
| S14 | Bash de Bob não lê caminho do volume de Alice no host; conteúdo pessoal permanece Bob. | Passou | Pendente |

## Outras evidências locais

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

**Pendente.** Provisionar WSL 2, repetir S01–S14 e os ensaios de HTTPS local, início por systemd após reabrir a distribuição, backup agendado/restauração, segurança, atualização/reversão e carga; corrigir falhas e registrar aceite técnico com critérios observáveis. A WOP permanece `in_progress` / `not_evaluated`. As provas de boot, rede, quotas e desempenho de um servidor independente continuam pendentes para a etapa de implantação futura; produção não foi ativada.
