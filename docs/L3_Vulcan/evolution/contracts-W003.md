# Contratos de passagem W003 → W004/W005

Plano `c1cf6012-e0a4-4f5a-a7fc-52a6ff0363fd` v5. Estes módulos são isolados nesta onda. A composição global, as capacidades efetivas, as rotas HTTP e o registro final dos apps pertencem à W005.

## Shell I006

`web/src/shell/app-registry.tsx` exporta `AppDescriptor`, `appRegistry`, `visibleApps(permissions)` e `appByKind(kind)`. Novos apps de W004 devem exportar `kind`, título, descrição, capacidade e ícone SVG com nome acessível no botão. `web/src/shell/personalization.ts` preserva pins de apps temporariamente revogados sem torná-los visíveis. O menu e o desktop recebem apenas a lista de capacidades efetivas, nunca confiam em `role` para autorizar uma ação.

## Workloads I007

`WorkloadService` recebe `ActorContext`, callbacks de autorização e revogação, runtime e templates já aprovados. `project`, `create`, `state`, `job`, `request`, `configure_secrets`, `reconcile`, `logs`, `metrics`, `admin_state`, `admin_request` e `gc` compõem o contrato interno. `request` aceita deploy/start/stop/restart/remove; start e restart exigem template anterior. A revisão do pedido entra no label Docker, de modo que o mesmo pedido não reinicia duas vezes e a revisão nova recria preservando o volume. Operações de deploy/controle e configuração de secret usam UUID `operation_id`; uma requisição nova marca a anterior ainda pendente como `superseded`. `state` do dono não retorna secret refs; o estado do administrador não retorna logs, métricas privadas ou conteúdo. O admin control-only só pode pedir stop/restart/remove. Jobs são reconciliados pelo worker com lease/fencing; a UI observa `pending`, `completed`, `failed` ou `superseded`.

`BuildService` aceita apenas contexto do diretório do owner, base local por digest e Dockerfile gerado. Comando e porta são argumentos tipados assinados no template e vinculados à operação idempotente. O scanner obrigatório emite `subject`, `high` e `critical`; qualquer achado high/critical bloqueia o template. O build testado no Docker real usou scanner fake controlado. Um scanner de release real e seu banco de vulnerabilidades são gate de I014 antes de produção. `TemplateRegistry` verifica HMAC do manifesto e hashes de SBOM, provenance e scan. `DockerWorkloadRuntime` não publica porta no host; workload com porta usa rede bridge interna exclusiva. `proxy_route` entrega host/IP/subnet/porta para `WorkloadProxy`, que limita HTTP, não segue redirect e não usa URL do cliente. W005 deve obter `Host` do request autenticado, registrar/remover rotas durante reconciliação e impedir acesso direto à bridge. WebSocket/TLS/dominio público permanecem desativados até política e teste de W005/W006.

Secret refs devem ter scope `workload`, pertencer ao dono e ser configuradas via `configure_secrets` com `operation_id`. O runtime usa `/run/secrets` em tmpfs privado e injeta bytes por stdin no Docker exec; secret não entra em argumento, env, label, volume ou arquivo do workspace. Rotação da revisão recria o contêiner; revogação interrompe reconciliação e para o workload. A imagem aprovada precisa de `/bin/sh` e comando explícito quando usa secrets. W005 deve selecionar esse suporte no catálogo de templates.

Migrações privadas: `workloads.core.v1`, `workloads.secrets.v2`, `workloads.secret_ops.v3`, `workloads.build.v1`, `workloads.routes.v1` e as leases do suporte. O endpoint futuro deve mapear erros de domínio para estados HTTP sem devolver stderr Docker ou bytes de secret.

## Workspace/Git I008

`WorkspaceFiles` oferece árvore paginada, leitura segura de texto/download, gravação por revisão e busca limitada/cancelável. `LinuxWatcher` emite `created`, `changed`, `deleted` e `overflow`; `WorkspaceIndex` reconstrói em overflow e atualiza por evento. `GitWorkspace` recebe root e owner fixos, callbacks de permissão e revogação, allowlist de hosts, known hosts e `GitCredentials`. Exporta status, diff, stage, unstage, commit, branch, history, pull/push com cancelamento e descarte com preview token. A saída do Git não inclui stderr bruto; o helper askpass fixo deve ser instalado pelo pacote Linux antes de habilitar Git remoto HTTPS.

`LspService` é contrato opcional desabilitado por padrão; `LanguageServer` exige imagem por digest, memória e timeout limitados. W005 só pode habilitar linguagem com runner isolado no broker. W004 pode representar diagnóstico indisponível sem iniciar executável do repositório. O índice FTS5 cria sua tabela privada em banco externo ao workspace; os arquivos e o Git usam o root do broker, não path absoluto vindo do navegador.

## IA/MCP I009

`ChatService` recebe providers explicitamente habilitados, `SecretVault` e limites de caracteres, custo e requisições por minuto. Provider externo exige disclosure antes do stream; credential_ref de scope `ai` é resolvida no momento da chamada e revalidada a cada bloco. `Provider.stream` é adapter tipado; U005 mantém providers reais desabilitados até configuração explícita. A UI W004 deve usar provider fake e mostrar retenção/export/delete, custo e cancelamento.

`ToolRegistry` exige `TrustedSource(enabled=True)` com fingerprint, versão e digest da política de cada tool externa; `disable_source` revoga a origem. `ApprovalEngine` faz request/approve/invoke/status de tickets vinculados a conta, sessão, versão, argumentos e nonce. UI W004 deve apresentar alvo, consequências, origem, risco e expiração fora de conteúdo não confiável. Falha após entrada no executor fica `unknown`, exige reconciliação humana/operacional e não autoriza replay. Não registrar tool de shell genérica nem converter saída de provider/arquivo/log em instrução. Migrações privadas: `ai.approvals.v1`, `ai.chat.v1`, `ai.chat.rate.v2` e `support.secrets.v1`.
