# Instalação e operação Linux

## Homologação local WSL 2

A homologação anterior usou uma distribuição Ubuntu 24.04 WSL 2 descartável. Em 22/11/2026, ela foi instalada em `.local-wsl/Ubuntu-24.04`, com `systemd`, Docker Engine 29.1.3 nativo da distribuição, Caddy 2.6.2 e Python 3.12.3. Na W002 do plano v4, a distribuição não pôde ser registrada (`CreateVm/E_INVALIDARG`). O responsável dispensou o teste das unidades systemd em host independente para esse portão e autorizou fixtures Docker Linux descartáveis. Os serviços systemd e produção continuam sem validação nesta etapa.

Para reproduzir em uma distribuição descartável, instalar Ubuntu 24.04 no WSL 2, `docker.io`, `caddy`, `python3-venv` e `python3-pip`. Copiar `apps/`, `web/dist/`, `launch.py`, `deploy/`, `scripts/setup_wsl_homologation.py`, `scripts/verify_wsl_service.py` e `scripts/verify_wsl_backup_schedule.py` para `/opt/aetherdesk`, preservando `web/dist/`. Criar `.venv` e instalar `deploy/requirements.txt` e `httpx` para os verificadores. Construir as três imagens Docker com os comandos abaixo. O usuário web `aetherdesk` não pertence ao grupo `docker`; somente `aetherdesk-broker` pertence. Bancos e socket são acessíveis ao grupo compartilhado `aetherdesk`. Executar como root:

```bash
python3 /opt/aetherdesk/scripts/setup_wsl_homologation.py
cd /opt/aetherdesk
.venv/bin/python scripts/verify_wsl_service.py
.venv/bin/python scripts/verify_wsl_backup_schedule.py
```

O configurador cria segredos aleatórios somente na primeira execução, instala a unidade systemd e configura Caddy em `https://localhost` com CA local. O verificador confia explicitamente em `/var/lib/caddy/.local/share/caddy/pki/authorities/local/root.crt`; não desabilita a verificação TLS. A senha da conta de teste fica em `/etc/aetherdesk/test-admin.password` com modo `0600`. O backup agendado é ativado apenas durante seu ensaio e desativado em `finally`.

Encerrar somente `Ubuntu-24.04` com `wsl --terminate Ubuntu-24.04` e reabri-la comprova o início da unidade ao iniciar a distribuição, após aguardar `/healthz`. Isso não comprova boot do Windows nem de um servidor Linux independente; serviços systemd não mantêm a instância WSL viva. A validação de boot real, TLS público, acesso externo, quotas e capacidade do host permanece necessária antes de produção.

## Servidor Linux independente — procedimento futuro

Alvo futuro: um servidor Debian amd64 com systemd, Docker Engine, Python 3.13, Caddy, DNS do domínio e portas 80/443 alcançáveis para emissão TLS. Os comandos abaixo ainda precisam ser executados em **host independente descartável** antes de serem adotados em produção. O responsável informou em 22/11/2026 que esse host ainda não existe.

## Preparar o pacote

Em uma máquina de build, instalar Node/pnpm e executar `pnpm install --frozen-lockfile && pnpm build` em `web/`. O pacote entregue ao servidor contém `apps/`, `web/dist/`, `launch.py`, `deploy/` e `pyproject.toml`/`uv.lock`. Não copiar `.local-demo`, `.venv`, `node_modules`, `.reference-vulcan` ou segredos.

No host, instalar Docker Engine, Python 3.13 com `venv`, `pip` e Caddy a partir dos repositórios oficiais adequados à distribuição. Conferir `docker version`, `python3 --version`, `caddy version` e `systemctl --version`. Copiar o pacote para `/opt/aetherdesk`, de propriedade de `root:root`, com permissão de leitura para o serviço. Executar:

```bash
sudo useradd --system --home-dir /var/lib/aetherdesk --shell /usr/sbin/nologin aetherdesk
sudo useradd --system --no-create-home --shell /usr/sbin/nologin --gid aetherdesk --groups docker aetherdesk-broker
sudo install -d -m 0770 -o aetherdesk -g aetherdesk /var/lib/aetherdesk
sudo install -d -m 0770 -o aetherdesk -g aetherdesk /var/backups/aetherdesk
cd /opt/aetherdesk
sudo python3 -m venv .venv
sudo .venv/bin/pip install --requirement deploy/requirements.txt
sudo docker build -t aetherdesk-runtime:w002 apps/AetherDesk/runtime
sudo docker build -t aetherdesk-terminal:w003 apps/AetherDesk/terminal
sudo docker build -f apps/AetherDesk/files/Dockerfile -t aetherdesk-files:w003 .
```

Criar `/etc/aetherdesk/aetherdesk.env` a partir de `deploy/aetherdesk.env.example`. Gerar segredos diferentes e aleatórios, inclusive `AETHERDESK_BROKER_SECRET_B64` a partir de 48 bytes aleatórios em base64; manter o arquivo `root:root`, modo `0600`. Bancos SQLite existentes precisam de acesso pelo grupo `aetherdesk` antes do corte. O serviço web escuta apenas `127.0.0.1:8174` e não deve definir `AETHERDESK_ALLOW_INSECURE_LOCAL_HTTP` fora de testes locais. Instalar as duas unidades `deploy/aetherdesk.service` e `deploy/aetherdesk-broker.service` em `/etc/systemd/system/`, configurar Caddy e validar:

```bash
sudo systemctl daemon-reload
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl enable --now docker caddy aetherdesk-broker aetherdesk
id -nG aetherdesk
id -nG aetherdesk-broker
sudo stat -c '%U:%G %a %n' /run/aetherdesk-broker /run/aetherdesk-broker/broker.sock
curl --fail --silent http://127.0.0.1:8174/healthz
curl --fail --silent http://127.0.0.1:8174/readyz
curl --fail --head https://SEU_DOMINIO/healthz
```

O proxy Caddy encaminha HTTP e WebSocket ao serviço local e obtém HTTPS para um domínio elegível. Confirmar certificado, redirecionamento HTTP→HTTPS, cookie `Secure`, `wss://`, cabeçalho HSTS e origem/CSRF com o domínio real. Se a instalação for apenas em rede privada sem DNS público, configurar uma CA interna e confiar nela nos clientes antes de testar; não ignorar alertas de certificado. [Caddy: HTTPS automático](https://caddyserver.com/docs/automatic-https), [proxy e WebSocket](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy).

## Primeira conta e operações

O bootstrap é único. Carregar as variáveis de `/etc/aetherdesk/aetherdesk.env` em um shell administrativo sem imprimir os segredos e executar `sudo --preserve-env=AETHERDESK_BOOTSTRAP_TOKEN,AETHERDESK_DATA_DIR -u aetherdesk /opt/aetherdesk/.venv/bin/python -m apps.AetherDesk.identity.cli bootstrap --username admin` a partir de `/opt/aetherdesk`. O comando solicita a senha sem eco. Entrar pelo domínio HTTPS; o evento `account.created` provisiona o ambiente. Depois, criar membros no painel de Administração.

No painel, **Revogar acesso** invalida autenticação web e mantém Bash/processos e janelas para o próximo login. **Parar sessão** revoga autenticação e interrompe os processos do contêiner, preservando o volume. Desativar/excluir conta interrompe processos; a exclusão lógica mantém os arquivos. O painel não dá acesso ao conteúdo alheio.

`AETHERDESK_ACCOUNT_RETENTION_SECONDS` é opcional e não tem valor padrão. Quando definido, a exclusão lógica registra a data de elegibilidade para purga no tombstone da conta; sem valor, `purge_after` fica vazio. Nenhum worker executa purga física nesta versão. O operador deve definir separadamente retenção, hold, exportação, backup e recuperação antes de ativar GC.

Logs: `journalctl -u aetherdesk -f`, `journalctl -u aetherdesk-broker -f` e `journalctl -u caddy -f`. Verificar estado das duas unidades, `/healthz`, `docker ps --filter label=aetherdesk.account_id`, espaço de `/var/lib/docker`, memória do host e os eventos administrativos. Confirmar que `aetherdesk` não pertence ao grupo `docker` nem acessa `/var/run/docker.sock`. Não incluir conteúdo de terminais/arquivos nos relatórios.

`/healthz` indica apenas que o processo web responde. `/readyz` exige banco de identidade presente e handshake HMAC com broker de protocolo 1; retorna 503 quando o broker não responde ou a versão não coincide. As rotas `/api/v2` rejeitam explicitamente `X-AetherDesk-API-Version` incompatível com 426. Monitorar ambos durante rollout e parar o corte se `/readyz` falhar.

## Rollout e proxy de workloads

`AETHERDESK_FEATURES=ide,workloads,ai` é opt-in e deve ser idêntico nas duas unidades. `AETHERDESK_KILL_AI=1` remove a IA; `AETHERDESK_KILL_DEPLOYS=1` bloqueia deploy/restart e o broker reverte jobs pendentes antes de reconciliar. `AETHERDESK_SAFE_MODE=1` mantém leitura, suspende mutações pendentes de workloads, desabilita suas ações e rotas e a IA; reiniciar **web e broker** juntos após mudar estas flags. O modo seguro não interrompe automaticamente containers já em execução. Egress Git remoto, registry, pacotes e provedores de IA permanece fechado neste candidate; nenhuma flag o ativa sem política de destino aprovada.

O proxy de workloads permanece desativado por padrão. Para ensaio isolado, `AETHERDESK_ENABLE_WORKLOAD_PROXY=1` exige DNS/roteamento de `*.apps.local` em uma origem distinta do desktop, TLS confiável, preservação de `Host` e encaminhamento ao mesmo serviço ASGI. A API emite ticket de 60 segundos para workload próprio em execução; o navegador o envia uma vez por POST ao host da aplicação, que estabelece cookie host-only de até uma hora. O broker prende IP, rede, porta e ownership, rejeita redirects e remove cookies/credenciais antes do upstream. O domínio `.apps.local` é exclusivo da fixture local; substituir por domínio público requer implementação e novo teste de isolamento. Não ativar este proxy em produção com o domínio hardcoded. Conteúdo de workloads não recebe acesso às rotas do desktop no host da aplicação.

O candidate é produzido por `python scripts/build_release.py --output release-candidate` após `pnpm build` e verificado por `python scripts/verify_release.py --directory release-candidate` e `python scripts/verify_candidate_install.py --archive release-candidate/aetherdesk-candidate.zip`. Arquivar `SHA256SUMS`, manifesto e SBOM junto do ZIP. O workflow `.github/workflows/candidate.yml` tem gates frontend, Linux/Docker, Trivy e release; sua execução hospedada depende de commit/push e não foi comprovada pela fixture local. O scan local da imagem Debian 13 encontrou zero achados críticos e 86 altos sem correção informada; a decisão de risco e a revarredura no ambiente de release ainda são necessárias.

## Backup e restauração

Backup começa **desativado**. Um administrador escolhe no painel frequência em horas, destino absoluto e retenção por dias ou substituição. RPO e RTO desejados são parâmetros opcionais em horas, sem meta fixa global; quando o backup está ativo e há RPO configurado, a frequência não pode excedê-lo. RTO é objetivo operacional e exige ensaio de restauração, não uma garantia criada pela configuração. O broker confere a configuração a cada minuto e só cria snapshot após o intervalo escolhido. O destino deve ser gravável por `aetherdesk-broker`, liberado no `ReadWritePaths` da unidade e ficar fora dos volumes dos usuários. O manifesto v2 cobre SQLite de identidade, terminais, workloads, IA, cofre e nonces, além de volumes pessoais e de workloads; cada entrada tem SHA-256. Com features v2 habilitadas, backup agendado exige `AETHERDESK_BACKUP_KEY_B64` de 32 bytes independente das chaves de workload. O resultado é um arquivo `.adbackup` AES-256-GCM; `verify` e `restore` exigem a mesma chave. A cópia de arquivos que mudam durante o tar é best-effort; para consistência atômica sob escrita intensa, o host deve oferecer snapshot do armazenamento ou janela operacional quiescente. Custódia da chave, destino off-host, retenção e RPO/RTO permanecem decisões do operador antes de backup real.

```bash
sudo --preserve-env=AETHERDESK_BOOTSTRAP_TOKEN,AETHERDESK_DATA_DIR,AETHERDESK_RUNTIME_IMAGE,AETHERDESK_BACKUP_KEY_B64 -u aetherdesk-broker /opt/aetherdesk/.venv/bin/python -m apps.AetherDesk.backup.cli run-now --destination /var/backups/aetherdesk --retention days --days 7
sudo --preserve-env=AETHERDESK_BACKUP_KEY_B64 -u aetherdesk-broker /opt/aetherdesk/.venv/bin/python -m apps.AetherDesk.backup.cli verify /var/backups/aetherdesk/aetherdesk-EXEMPLO.adbackup
```

Para restauração, **parar o serviço**, fazer cópia de segurança do estado atual, usar destino descartável, verificar hashes, restaurar bancos e volumes, reiniciar o serviço e testar login, permissões, preferências, `/persist` de duas contas e isolamento. Exemplo de ensaio:

```bash
sudo systemctl stop aetherdesk aetherdesk-broker
sudo --preserve-env=AETHERDESK_BACKUP_KEY_B64 /opt/aetherdesk/.venv/bin/python -m apps.AetherDesk.backup.cli restore /var/backups/aetherdesk/aetherdesk-EXEMPLO.adbackup --data-dir /var/lib/aetherdesk-restaurado --confirm-offline
```

O CLI **não** apaga arquivos antigos de volumes já existentes; restaurar em host/volumes descartáveis para o ensaio. Em recuperação real, planejar substituição de volumes e bancos separadamente, com reversão testada. Os segredos do arquivo `/etc/aetherdesk/aetherdesk.env` não entram no snapshot e devem ser custodiados fora dos ambientes dos usuários.

## Cofre de segredos — recuperação em fixture

O cofre interno guarda somente ciphertext, nonce e versão da chave no SQLite. A chave mestra fica fora desse banco e dos volumes de usuário. Antes de ativar provedores ou backup real, o operador precisa definir custódia, cópia independente, acesso de recuperação e retenção de cada versão da chave; esta integração ainda não existe. Não remover uma versão antiga enquanto algum snapshot recuperável contiver entradas cifradas com ela.

Em uma restauração **descartável**, recuperar o banco e as versões da chave por canais separados. Construir `Keyring` apenas em memória com as versões necessárias e executar `SecretVault.verify_restore()` antes de liberar o serviço. O método verifica a autenticação AES-GCM de todas as entradas ativas e devolve somente contagem e versões, sem valores, nomes ou donos. Chave ausente resulta em `MASTER_KEY_UNAVAILABLE`; ciphertext ou chave incorreta resulta em `SECRET_UNAVAILABLE`. Manter o serviço fechado nesses casos e preservar o snapshot original. A prova em `support/test_secrets.py` usa chaves e dados de fixture; não comprova custódia, backup criptografado externo ou RTO de produção.

## Atualização e reversão

Antes da atualização, executar `run-now`, `verify` e registrar hashes de dois arquivos de contas distintas. Guardar pacote anterior e imagem Docker anterior. Parar `aetherdesk`, instalar pacote novo em diretório de versão separado, instalar dependências fixadas, construir imagem nova com tag de versão, executar migrações em cópia de dados e testar a jornada em homologação. Alternar `/opt/aetherdesk` para a versão nova só após aprovação técnica; reiniciar e verificar `/healthz`, login, arquivo, PTY e métricas. Em falha, parar versão nova, voltar código/imagens anteriores e restaurar snapshot apenas se a migração de dados exigir. Não executar reversão cega sobre arquivos novos sem decidir política de perda.

Na transição v1→v2 do AetherDesk, **a migração de dados exige o snapshot para voltar ao binário v1**. O schema `terminals` v2 acrescenta colunas e o v1 insere registros por posição; portanto, iniciar o v1 sobre o banco já migrado falha na criação de terminais. Antes de alternar a versão, guardar os bancos e volumes em um snapshot consistente e verificar sua restauração em destino descartável. Para reversão, parar web e broker v2, restaurar juntos os bancos e volumes do snapshot v1 em destino isolado, verificar hashes/contas e somente então iniciar código e imagem v1. O caminho alternativo é manter v2 e aplicar forward recovery sobre o snapshot v1. Nenhum dos dois caminhos recupera automaticamente escritas posteriores ao snapshot; o operador deve decidir a janela e registrar essa perda potencial antes da troca.

## Risco de privilégio

Somente `aetherdesk-broker` controla o Docker Engine; pertencer ao grupo `docker` equivale a amplo controle do host. O web usa socket Unix com operações tipadas, HMAC, expiração e vínculo conta/ambiente verificado pelo broker. A homologação precisa provar permissões reais de processo, caminhos/symlinks, negação via PTY, origem/CSRF, revogação em conexão aberta e limites de recursos. Este runbook não declara a instalação aprovada sem essas provas.

O agente de arquivos da imagem atual anuncia o protocolo persistente por `/opt/aetherdesk/.aetherdesk-file-stream-v1`. O broker faz uma sondagem fixa uma vez por contêiner: imagens antigas sem o marcador continuam com o protocolo de uma requisição por `docker exec`, e imagens atualizadas reutilizam o processo para requisições JSON por linha. Reconstruir a imagem de runtime antes do corte do broker; contêineres pessoais já existentes mantêm a imagem antiga até serem recriados pelo fluxo de rollout, sem migrar seus volumes por esta mudança. O broker encerra o agente ao parar/remover o ambiente e ao desligar. Confirmar os dois caminhos em fixture antes de atualização real.
