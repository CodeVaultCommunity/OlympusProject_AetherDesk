# AetherDesk

Desktop web privado com ambientes Linux individuais, shell personalizável, Explorador, IDE Monaco/Git, Bash/PTY reconectável, monitor, administração, workloads e IA/MCP governada. O projeto adota a organização Vulcan Stable-v1.0.0 sem declarar conformidade formal com Minerva. A evolução segue o [plano WOP](.wop/plans/2026_11_23_18_33_07-evolucao_aetherdesk_desktop_ide_containers_ia/README.md).

**Estado em 24/11/2026:** W001–W006 passaram nos portões técnicos. A matriz W006 do ZIP SHA-256 `9f6d75022c942993d9ff4d3a9543ffd1bc3230785389e51e4e2538a4f1514db2` recebeu aceite do responsável **somente para homologação Docker local descartável com dados sintéticos**. Consulte [portão W006](docs/L3_Vulcan/evolution/gate-W006.md), [relatório de homologação](docs/L3_Vulcan/evolution/homologation-W006.md) e [matriz R001–R028/L001–L032](docs/L3_Vulcan/evolution/traceability-W006.md). Distribuição e produção exigem aprovação separada, inclusive host Linux independente, backup/chaves off-host, domínio/TLS/registry, capacidade e nova decisão sobre vulnerabilidades residuais.

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

HTTP inseguro só é permitido em `127.0.0.1` para desenvolvimento. O primeiro administrador pode ser criado uma vez pela rota `/api/v1/bootstrap` ou pelo CLI `python -m apps.AetherDesk.identity.cli bootstrap --username admin`, com variáveis de ambiente carregadas. Operações de arquivos/PTY/workloads requerem o broker separado descrito no [runbook](docs/L3_Vulcan/operations.md). O modo visual `?fixture=1` só existe em `pnpm dev`.

## Verificações locais

```powershell
$env:AETHERDESK_DOCKER_TEST='1'
uv run python -m unittest apps.AetherDesk.composition.test_scenarios_local apps.AetherDesk.backup.test_service -v
uv run python -m unittest apps.AetherDesk.identity.test_service apps.AetherDesk.identity.test_http apps.AetherDesk.composition.test_http_integrated apps.AetherDesk.files.test_gateway apps.AetherDesk.files.test_http apps.AetherDesk.terminal.test_service apps.AetherDesk.terminal.test_http apps.AetherDesk.monitor.test_service apps.AetherDesk.administration.test_service -v
```

Os testes Docker usam contêineres e volumes descartáveis. Para a instalação planejada, consulte [operação Linux](docs/L3_Vulcan/operations.md), [arquitetura](docs/L3_Vulcan/architecture.md), [contratos](docs/L3_Vulcan/contracts-v1.md) e [evidência W003](docs/L3_Vulcan/gate-W003.md).
