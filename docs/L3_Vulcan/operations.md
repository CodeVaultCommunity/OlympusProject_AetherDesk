# Instalação e operação Linux

## Homologação local WSL 2

A versão 3 do plano usa uma distribuição Ubuntu 24.04 WSL 2 descartável para concluir a homologação local. Em 22/11/2026, a distribuição `Ubuntu-24.04` foi instalada em `.local-wsl/Ubuntu-24.04`, com `systemd`, Docker Engine 29.1.3 **nativo da distribuição**, Caddy 2.6.2 e Python 3.12.3. Não depende da integração Docker Desktop. Dados e segredos ficam no filesystem Linux, em `/var/lib/aetherdesk` e `/etc/aetherdesk`; `.local-wsl/` é ignorado pelo Git.

Para reproduzir em uma distribuição descartável, instalar Ubuntu 24.04 no WSL 2, `docker.io`, `caddy`, `python3-venv` e `python3-pip`. Copiar `apps/`, `web/dist/`, `launch.py`, `deploy/`, `scripts/setup_wsl_homologation.py`, `scripts/verify_wsl_service.py` e `scripts/verify_wsl_backup_schedule.py` para `/opt/aetherdesk`, preservando `web/dist/`. Criar `.venv` e instalar `deploy/requirements.txt` e `httpx` para os verificadores. Construir as três imagens Docker com os comandos abaixo, criar o usuário de sistema `aetherdesk` no grupo `docker` e os diretórios `/var/lib/aetherdesk` e `/var/backups/aetherdesk` com dono `aetherdesk` e modo `0700`. Executar como root:

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
sudo usermod -aG docker aetherdesk
sudo install -d -m 0700 -o aetherdesk -g aetherdesk /var/lib/aetherdesk
sudo install -d -m 0700 -o aetherdesk -g aetherdesk /var/backups/aetherdesk
cd /opt/aetherdesk
sudo python3 -m venv .venv
sudo .venv/bin/pip install --requirement deploy/requirements.txt
sudo docker build -t aetherdesk-runtime:w002 apps/AetherDesk/runtime
sudo docker build -t aetherdesk-terminal:w003 apps/AetherDesk/terminal
sudo docker build -f apps/AetherDesk/files/Dockerfile -t aetherdesk-files:w003 .
```

Criar `/etc/aetherdesk/aetherdesk.env` a partir de `deploy/aetherdesk.env.example`. Gerar segredos diferentes e aleatórios; manter o arquivo `root:root`, modo `0600`. O serviço escuta apenas `127.0.0.1:8174` e não deve definir `AETHERDESK_ALLOW_INSECURE_LOCAL_HTTP` fora de testes locais. Instalar `deploy/aetherdesk.service` em `/etc/systemd/system/`, substituir `desk.example.com` em `deploy/Caddyfile.example`, instalar como `/etc/caddy/Caddyfile` e validar:

```bash
sudo systemctl daemon-reload
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl enable --now docker caddy aetherdesk
curl --fail --silent http://127.0.0.1:8174/healthz
curl --fail --head https://SEU_DOMINIO/healthz
```

O proxy Caddy encaminha HTTP e WebSocket ao serviço local e obtém HTTPS para um domínio elegível. Confirmar certificado, redirecionamento HTTP→HTTPS, cookie `Secure`, `wss://`, cabeçalho HSTS e origem/CSRF com o domínio real. Se a instalação for apenas em rede privada sem DNS público, configurar uma CA interna e confiar nela nos clientes antes de testar; não ignorar alertas de certificado. [Caddy: HTTPS automático](https://caddyserver.com/docs/automatic-https), [proxy e WebSocket](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy).

## Primeira conta e operações

O bootstrap é único. Carregar as variáveis de `/etc/aetherdesk/aetherdesk.env` em um shell administrativo sem imprimir os segredos e executar `sudo --preserve-env=AETHERDESK_BOOTSTRAP_TOKEN,AETHERDESK_DATA_DIR -u aetherdesk /opt/aetherdesk/.venv/bin/python -m apps.AetherDesk.identity.cli bootstrap --username admin` a partir de `/opt/aetherdesk`. O comando solicita a senha sem eco. Entrar pelo domínio HTTPS; o evento `account.created` provisiona o ambiente. Depois, criar membros no painel de Administração.

No painel, **Revogar acesso** invalida autenticação web e mantém Bash/processos e janelas para o próximo login. **Parar sessão** revoga autenticação e interrompe os processos do contêiner, preservando o volume. Desativar/excluir conta interrompe processos; a exclusão lógica mantém os arquivos. O painel não dá acesso ao conteúdo alheio.

Logs: `journalctl -u aetherdesk -f` e `journalctl -u caddy -f`. Verificar `systemctl status aetherdesk`, `/healthz`, `docker ps --filter label=aetherdesk.account_id`, espaço de `/var/lib/docker`, memória do host e os eventos administrativos. Não incluir conteúdo de terminais/arquivos nos relatórios.

## Backup e restauração

Backup começa **desativado**. Um administrador escolhe no painel frequência em horas, destino absoluto e retenção por dias ou substituição. O serviço confere a configuração a cada minuto e só cria snapshot após o intervalo escolhido. O destino deve ser gravável pelo usuário `aetherdesk`, fora dos volumes dos usuários, com capacidade para bancos e arquivos. Cada snapshot contém cópias SQLite, tar de cada volume e manifesto SHA-256. A cópia de arquivos que mudam durante o tar é best-effort; para consistência atômica sob escrita intensa, o host deve oferecer snapshot do armazenamento ou janela operacional quiescente. Confirmar capacidade e política de retenção antes de ativar.

```bash
sudo --preserve-env=AETHERDESK_BOOTSTRAP_TOKEN,AETHERDESK_DATA_DIR,AETHERDESK_RUNTIME_IMAGE -u aetherdesk /opt/aetherdesk/.venv/bin/python -m apps.AetherDesk.backup.cli run-now --destination /var/backups/aetherdesk --retention days --days 7
/opt/aetherdesk/.venv/bin/python -m apps.AetherDesk.backup.cli verify /var/backups/aetherdesk/aetherdesk-EXEMPLO
```

Para restauração, **parar o serviço**, fazer cópia de segurança do estado atual, usar destino descartável, verificar hashes, restaurar bancos e volumes, reiniciar o serviço e testar login, permissões, preferências, `/persist` de duas contas e isolamento. Exemplo de ensaio:

```bash
sudo systemctl stop aetherdesk
sudo /opt/aetherdesk/.venv/bin/python -m apps.AetherDesk.backup.cli restore /var/backups/aetherdesk/aetherdesk-EXEMPLO --data-dir /var/lib/aetherdesk-restaurado --confirm-offline
```

O CLI **não** apaga arquivos antigos de volumes já existentes; restaurar em host/volumes descartáveis para o ensaio. Em recuperação real, planejar substituição de volumes e bancos separadamente, com reversão testada. Os segredos do arquivo `/etc/aetherdesk/aetherdesk.env` não entram no snapshot e devem ser custodiados fora dos ambientes dos usuários.

## Atualização e reversão

Antes da atualização, executar `run-now`, `verify` e registrar hashes de dois arquivos de contas distintas. Guardar pacote anterior e imagem Docker anterior. Parar `aetherdesk`, instalar pacote novo em diretório de versão separado, instalar dependências fixadas, construir imagem nova com tag de versão, executar migrações em cópia de dados e testar a jornada em homologação. Alternar `/opt/aetherdesk` para a versão nova só após aprovação técnica; reiniciar e verificar `/healthz`, login, arquivo, PTY e métricas. Em falha, parar versão nova, voltar código/imagens anteriores e restaurar snapshot apenas se a migração de dados exigir. Não executar reversão cega sobre arquivos novos sem decidir política de perda.

## Risco de privilégio

O serviço precisa controlar o Docker Engine; pertencer ao grupo `docker` equivale a amplo controle do host. Antes de produção, substituir essa integração por um broker de operações restritas ou Docker rootless com isolamento equivalente e testar a fronteira. A homologação deve revisar também caminhos/symlinks, negação via PTY, origem/CSRF, revogação em conexão aberta e limites de recursos. Este runbook não declara a instalação aprovada sem essas provas.
