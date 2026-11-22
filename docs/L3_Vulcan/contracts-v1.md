# Contratos públicos propostos — versão 1

Estado: **versão 1 congelada no gate W001**. Transporte JSON em `/api/v1`; WebSocket em `/api/v1/ws`. Mudança incompatível exige `/api/v2` ou migração explícita. Todos os IDs são UUID criados no servidor. Tempo em UTC RFC 3339; tamanhos em bytes. A sessão autenticada gera `ActorContext(account_id, session_id, role, permissions_version)` no servidor. `target_account_id` fornecido pelo cliente nunca substitui esse contexto para recursos pessoais.

## Resposta e falhas comuns

Sucesso HTTP retorna `{data, revision?, event_id}`; erro retorna `{error:{code,message,event_id,retryable}}`, sem caminhos do host nem conteúdo pessoal. Códigos: `UNAUTHENTICATED` 401, `FORBIDDEN` 403, `NOT_FOUND` 404, `CONFLICT` 409, `STALE_REVISION` 412, `UNAVAILABLE` 503, `UNKNOWN_WRITE_OUTCOME` 503. Fluxos WS enviam `{type, revision, payload, event_id}`; no erro ou revogação enviam `error` e fecham com código apropriado. Toda mutação valida CSRF e versão de permissão. O consumidor deve consultar o estado atual depois de `UNKNOWN_WRITE_OUTCOME` antes de repetir.

## Contratos por domínio

| Domínio/versão | Entrada | Saída e efeito | Identidade/autorização | Falhas específicas |
|---|---|---|---|---|
| Identidade v1 | `POST /bootstrap` com token único, `POST /login` com nome/senha, `POST /logout`, `GET /me` | Sessão opaca em cookie; `/me` retorna ID, papel e permissões efetivas. Logout revoga somente a sessão web, mantém ambiente e processos. | Bootstrap só enquanto não existe administrador; login só conta ativa. | Token usado, senha inválida, conta desativada. |
| Sessões v1 | `GET /admin/sessions`, `POST /admin/sessions/{id}/revoke`, `POST /admin/accounts/{id}/stop-session` com confirmação | Revogar invalida autenticação; parar invalida sessões e encerra PTYs/processos do ambiente, preservando volume; eventos auditados. | Administrador com capacidades distintas `sessions.revoke` e `sessions.stop`. | Sessão ausente, estado em transição, parada parcial. |
| Contas v1 | `POST/GET/PATCH /admin/accounts`, `POST /admin/accounts/{id}/password-reset`, `POST /admin/accounts/{id}/disable`, `DELETE /admin/accounts/{id}` | ID imutável; mudança de nome mantém volume; exclusão lógica impede login, encerra processos e mantém arquivos; resposta informa estado e revisão. | Administrador com capacidades `accounts.view`/`accounts.manage`; proibir excluir último administrador ativo. | Nome em conflito, versão obsoleta, provisionamento falho. |
| Permissões v1 | `GET/PUT /admin/accounts/{id}/permissions` com revisão | Matriz efetiva e nova `permissions_version`; conexões WS reavaliam ao receber evento de revogação e antes de cada ação. | `permissions.view` separado de `permissions.manage`; nenhum papel concede acesso implícito a arquivos/PTY alheios. | Escalada proibida, revisão obsoleta. |
| Ambiente v1 | `GET /environment`, `POST /environment/ensure`, `POST /admin/accounts/{id}/environment/retry` | Estado `absent/provisioning/ready/stopping/stopped/failed`, ID imutável e erro redigido; `ensure` idempotente sob concorrência. | Pessoal derivado de `ActorContext`; retry somente administrador com `environment.manage`. | Runtime indisponível, quota, transição concorrente. |
| Arquivos v1 | `GET /files?path=`, `GET /files/content?path=`, `PUT /files/content?path=` com `If-Match`, `POST /files/{mkdir,move,copy,upload}`, `DELETE /files?path=`, `GET /files/download?path=` | Lista metadados com revisão; conteúdo binário/UTF-8; operações atômicas quando possível; conflito de nome exige escolha explícita. | `files.read`/`files.write` por operação; ambiente sempre da sessão. Broker resolve path dentro do namespace e área permitida, nega symlink externo. | Caminho inválido, quota, conflito, revisão obsoleta, resultado desconhecido. |
| Terminal v1 | `POST /terminals`, `GET /terminals`, `DELETE /terminals/{id}`, WS `/ws/terminals/{id}` com `input/resize/signal`, `output/exit` | PTY real por ID imutável, buffer curto para reconexão; ambiente e processo continuam após logout/revogação. | Dono = `ActorContext.account_id`; `terminal.open`/`terminal.control` separados; checagem por mensagem e na reconexão. | PTY ausente, backlog perdido, permissão revogada, ambiente parado. |
| Métricas v1 | `GET /metrics/self`, `GET /metrics/server`, `GET /admin/metrics/accounts` | `{scope,subject_id,at,interval_ms,metrics:{cpu,ram,storage,io,network},availability}` com unidade e origem por campo; indisponível não vira zero. | `metrics.self`, `metrics.server`, `metrics.accounts` separados; outros ambientes só agregados ou com permissão administrativa explícita. | Coletor indisponível, amostra vencida. |
| Preferências e desktop v1 | `GET/PUT /preferences`, `GET/PUT /desktop/state` com revisão | Tema, layout, janelas abertas, posição/tamanho/z-index, aplicativo e estado restaurável; salvo por conta entre logins. | Própria conta; `preferences.read/write`; nenhuma URL de arquivo externo persistida sem validação. | Revisão obsoleta, estado inválido. |
| Backup v1 | `GET/PUT /admin/backup/config`, `POST /admin/backup/run`, `GET /admin/backup/jobs`, `POST /admin/backup/restore` com confirmação e manifesto | `enabled=false` por padrão; frequência, destino externo, retenção `{mode:days,days}` ou `{mode:replace_previous}`; jobs com estado, hashes e erro redigido. Restauração exige parada coordenada. | `backup.view`, `backup.manage`, `backup.restore` separados; segredos do destino não voltam na API. | Destino inválido, espaço insuficiente, manifesto/hash inválido. |
| Auditoria v1 | `GET /admin/audit?cursor=` | Eventos `{id,actor_id,operation,target_id,at,result}`; sem comandos, texto de arquivos ou bytes de PTY. | Somente `audit.view`; escrita server-side para mutações administrativas. | Consulta inválida, armazenamento indisponível. |

## Matriz mínima de permissões

| Capacidade | Membro inicial | Administrador inicial | Escopo |
|---|---|---|---|
| `files.read`, `files.write`, `terminal.open`, `terminal.control`, `metrics.self`, `preferences.read`, `preferences.write` | Sim | Sim | Somente próprio ambiente |
| `metrics.server` | Não | Sim | Host agregado |
| `metrics.accounts`, `accounts.view`, `permissions.view`, `audit.view`, `backup.view` | Não | Sim | Administração, sem conteúdo privado |
| `accounts.manage`, `permissions.manage`, `environment.manage`, `sessions.revoke`, `sessions.stop`, `backup.manage`, `backup.restore` | Não | Sim | Operações distintas e auditadas |

Permissões individuais podem retirar ou acrescentar capacidades, sujeitas a validação de escalada. `view` nunca implica `manage`; `sessions.revoke` nunca implica `sessions.stop`. O broker aceita somente `EnvironmentCapability(account_id, environment_id, operation, expires_at)` assinada pelo serviço e vinculada à chamada atual; não confia em IDs de rota.

## Contratos internos e ownership

| Protocolo v1 | Método e resultado | Falha | Dono inicial |
|---|---|---|---|
| `IdentityStore` | `create/get/update_account`, `verify_password`, `create/revoke_session`, `effective_permissions` → entidades/revisões | conflito, inexistente, armazenamento | I002 `apps/AetherDesk/identity/` |
| `EnvironmentBroker` | `ensure(account_id)` → estado/ID; `stop(environment_id)` → estado; `open_file/pty/metrics` → handles vinculados | runtime, quota, estado, negação | I003 `apps/AetherDesk/runtime/` |
| `FilePort` | `list/read/write/move/copy/delete` em ambiente derivado → metadados/revisão | conflito, symlink, quota, resultado desconhecido | I005 `apps/AetherDesk/files/` |
| `TerminalPort` | `create/attach/write/resize/signal/close` → PTY e stream | não encontrado, revogado, desconectado | I006 `apps/AetherDesk/terminal/` |
| `MetricPort` | `sample(scope, subject)` → amostra com disponibilidade | coletor indisponível | I007 `apps/AetherDesk/monitor/` |
| `AdminPort` | contas/sessões/permissões/backup → estados auditados | negação, conflito, falha parcial | I008 `apps/AetherDesk/admin/` |
| `DesktopClient` | `me`, `desktop/state`, eventos `session_revoked`/`permission_changed`/`environment_state` | erro comum da API | I004 `web/` |

I001 detém este documento. I002/I003/I004 usam fixtures e migrações próprias. I005–I008 detêm seus módulos e testes. `AppComposition`, `launch.py`, roteamento, migrações combinadas e configuração de build só são alterados no portão de integração ou I009. Contratos de banco usam IDs estáveis; tabelas de um domínio não são alteradas por outro item.
