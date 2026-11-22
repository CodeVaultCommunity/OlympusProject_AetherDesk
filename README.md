# AetherDesk

Desktop web privado com ambientes Linux individuais, Explorador, editor Monaco, Bash/PTY reconectável, monitor e administração. O projeto adota a organização Vulcan Stable-v1.0.0 sem declarar conformidade formal com Minerva. A execução segue o [plano WOP](.wop/plans/2026_11_22_14_35_53-aetherdesk_vulcan/README.md).

**Estado:** W001–W003 passaram tecnicamente. W004 tem implementação e testes locais em andamento, mas o portão final depende de host Linux de homologação, TLS/boot, revisão de segurança e aceite funcional. O usuário informou que ainda não há host Linux. Não instalar em produção neste estágio.

## Construir e executar localmente

```powershell
uv sync
docker build -t aetherdesk-runtime:w002 apps/AetherDesk/runtime
docker build -t aetherdesk-terminal:w003 apps/AetherDesk/terminal
docker build -f apps/AetherDesk/files/Dockerfile -t aetherdesk-files:w003 .
cd web
pnpm install --frozen-lockfile
pnpm build
cd ..
$env:AETHERDESK_BOOTSTRAP_TOKEN='<token-aleatorio-com-16-ou-mais-caracteres>'
$env:AETHERDESK_CSRF_SECRET='<segredo-aleatorio-com-32-ou-mais-caracteres>'
$env:AETHERDESK_DATA_DIR='.local'
$env:AETHERDESK_ALLOW_INSECURE_LOCAL_HTTP='1'
uv run uvicorn launch:create_app --factory --host 127.0.0.1 --port 8174
```

HTTP inseguro só é permitido em `127.0.0.1` para desenvolvimento. O primeiro administrador pode ser criado uma vez pela rota `/api/v1/bootstrap` ou pelo CLI `python -m apps.AetherDesk.identity.cli bootstrap --username admin`, com variáveis de ambiente carregadas. O modo visual `?fixture=1` só existe em `pnpm dev`.

## Verificações locais

```powershell
$env:AETHERDESK_DOCKER_TEST='1'
uv run python -m unittest apps.AetherDesk.composition.test_scenarios_local apps.AetherDesk.backup.test_service -v
uv run python -m unittest apps.AetherDesk.identity.test_service apps.AetherDesk.identity.test_http apps.AetherDesk.composition.test_http_integrated apps.AetherDesk.files.test_gateway apps.AetherDesk.files.test_http apps.AetherDesk.terminal.test_service apps.AetherDesk.terminal.test_http apps.AetherDesk.monitor.test_service apps.AetherDesk.administration.test_service -v
```

Os testes Docker usam contêineres e volumes descartáveis. Para a instalação planejada, consulte [operação Linux](docs/L3_Vulcan/operations.md), [arquitetura](docs/L3_Vulcan/architecture.md), [contratos](docs/L3_Vulcan/contracts-v1.md) e [evidência W003](docs/L3_Vulcan/gate-W003.md).
