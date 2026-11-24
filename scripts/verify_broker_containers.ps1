# Ensaio W002: dois processos Linux descartáveis, Docker socket só no broker.
param([switch]$BenchmarkDataset, [switch]$BenchmarkLoad, [switch]$PtyPressure, [switch]$AuditRotation, [switch]$UpdatedAgent)
$ErrorActionPreference = 'Stop'
$workspace = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$suffix = [guid]::NewGuid().ToString('N').Substring(0, 10)
$brokerName = "aetherdesk-w002-broker-$suffix"
$webName = "aetherdesk-w002-web-$suffix"
$ipcVolume = "aetherdesk-w002-ipc-$suffix"
$dataVolume = "aetherdesk-w002-data-$suffix"
$auditVolume = "aetherdesk-w002-audit-$suffix"
$environmentIds = [System.Collections.Generic.List[string]]::new()
$image = 'aetherdesk-w002-broker-fixture:local'
$builtImage = $false
$runtimeImage = if ($UpdatedAgent) { "aetherdesk-files:w002-fixture-$suffix" } else { 'aetherdesk-files:w003' }
$builtRuntimeImage = $false
$secret = [Convert]::ToBase64String([System.Security.Cryptography.RandomNumberGenerator]::GetBytes(48))
$bootstrap = [Convert]::ToBase64String([System.Security.Cryptography.RandomNumberGenerator]::GetBytes(36))
$csrf = [Convert]::ToBase64String([System.Security.Cryptography.RandomNumberGenerator]::GetBytes(36))
$common = @(
    '--env', "AETHERDESK_BROKER_SECRET_B64=$secret",
    '--env', "AETHERDESK_BOOTSTRAP_TOKEN=$bootstrap",
    '--env', "AETHERDESK_CSRF_SECRET=$csrf",
    '--env', 'AETHERDESK_DATA_DIR=/data',
    '--env', 'AETHERDESK_BROKER_SOCKET=/ipc/broker.sock',
    '--env', "AETHERDESK_RUNTIME_IMAGE=$runtimeImage",
    '--env', 'PYTHONPATH=/src',
    '--env', 'PYTHONDONTWRITEBYTECODE=1'
)
$auditPolicy = @()
if ($AuditRotation) { $auditPolicy = @('--env', 'AETHERDESK_BROKER_AUDIT_MAX_BYTES=1048576',
                                     '--env', 'AETHERDESK_BROKER_AUDIT_BACKUPS=1') }

function Assert-DockerExit($step) {
    if ($LASTEXITCODE -ne 0) { throw "Falhou: $step (docker exit $LASTEXITCODE)" }
}

try {
    if ($UpdatedAgent) {
        & docker build --file (Join-Path $workspace 'apps/AetherDesk/files/Dockerfile') `
            --tag $runtimeImage $workspace | Out-Null
        Assert-DockerExit 'construir imagem descartável do agente atualizado'
        $builtRuntimeImage = $true
    }
    $availableImages = @(& docker image ls --format '{{.Repository}}:{{.Tag}}')
    Assert-DockerExit 'consultar imagens Docker'
    if ($availableImages -notcontains $image) {
        & docker build --file (Join-Path $workspace 'deploy/Dockerfile.broker-fixture') `
            --tag $image (Join-Path $workspace 'deploy') | Out-Null
        Assert-DockerExit 'construir imagem descartável da fixture'
        $builtImage = $true
    }
    & docker volume create $ipcVolume | Out-Null
    Assert-DockerExit 'criar volume IPC'
    & docker volume create $dataVolume | Out-Null
    Assert-DockerExit 'criar volume de dados'
    & docker volume create $auditVolume | Out-Null
    Assert-DockerExit 'criar volume de auditoria'
    & docker run --rm --network none --mount "type=volume,source=$ipcVolume,target=/ipc" `
        --mount "type=volume,source=$dataVolume,target=/data" `
        --mount "type=volume,source=$auditVolume,target=/audit" $image sh -c `
        'chown 10002:10001 /ipc && chmod 0710 /ipc && chown 10001:10001 /data && chmod 0770 /data && chown 10002:10001 /audit && chmod 0700 /audit' | Out-Null
    Assert-DockerExit 'preparar volumes'

    & docker run --detach --name $brokerName --network none --read-only --cap-drop ALL `
        --tmpfs /tmp:rw,nosuid,nodev,size=16m --user 10002:10001 --group-add 0 `
        --mount "type=bind,source=$workspace,target=/src,readonly" `
        --mount 'type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock' `
        --mount "type=volume,source=$ipcVolume,target=/ipc" `
        --mount "type=volume,source=$dataVolume,target=/data" `
        --mount "type=volume,source=$auditVolume,target=/audit" `
        @common @auditPolicy --env AETHERDESK_BROKER_AUDIT_LOG=/audit/audit.log $image sh -c `
        'umask 0077; exec python -m apps.AetherDesk.runtime.broker_main' | Out-Null
    Assert-DockerExit 'iniciar broker'
    $ready = $false
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        & docker exec $brokerName sh -c 'test -S /ipc/broker.sock' 2>$null
        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
        Start-Sleep -Seconds 1
    }
    if (-not $ready) {
        & docker logs --tail 60 $brokerName
        throw 'Socket do broker não iniciou'
    }

    & docker run --detach --name $webName --network none --read-only --cap-drop ALL `
        --tmpfs /tmp:rw,nosuid,nodev,size=16m --user 10001:10001 `
        --mount "type=bind,source=$workspace,target=/src,readonly" `
        --mount "type=volume,source=$ipcVolume,target=/ipc" `
        --mount "type=volume,source=$dataVolume,target=/data" `
        @common --env AETHERDESK_ALLOW_INSECURE_LOCAL_HTTP=1 $image sh -c `
        'umask 0007; exec python -m uvicorn launch:create_app --factory --host 127.0.0.1 --port 8174 --no-access-log' | Out-Null
    Assert-DockerExit 'iniciar web'
    $ready = $false
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        & docker exec $webName python -c `
            "import urllib.request; assert urllib.request.urlopen('http://127.0.0.1:8174/healthz', timeout=2).status == 200" 2>$null
        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
        if ((& docker inspect --format '{{.State.Running}}' $webName) -eq 'false') { break }
        Start-Sleep -Seconds 1
    }
    if (-not $ready) {
        & docker exec $brokerName sh -c 'stat -c "%u:%g %a %n" /data /data/identity.sqlite3 /data/identity.sqlite3-wal /data/identity.sqlite3-shm 2>/dev/null'
        & docker logs --tail 60 $webName
        & docker logs --tail 60 $brokerName
        throw 'Web não iniciou'
    }

    $result = & docker exec $webName python -B scripts/verify_broker_container.py 2>&1
    $testExit = $LASTEXITCODE
    $result | ForEach-Object { Write-Output $_ }
    foreach ($line in $result) {
        if ([string]$line -match '^AETHERDESK_FIXTURE_ENV=([0-9a-f-]{36})$') {
            if (-not $environmentIds.Contains($Matches[1])) { $environmentIds.Add($Matches[1]) }
        }
    }
    if ($testExit -ne 0) {
        & docker logs --tail 70 $brokerName
        & docker logs --tail 30 $webName
        throw "Falhou: ensaio integrado (docker exit $testExit)"
    }
    if ($environmentIds.Count -ne 2) { throw 'Ensaio não informou dois ambientes descartáveis' }
    if ($BenchmarkDataset) {
        & docker exec $brokerName python -B scripts/benchmark_broker_dataset.py
        Assert-DockerExit 'benchmark direto/broker com dataset de arquivos'
    }
    if ($BenchmarkLoad) {
        if (-not $UpdatedAgent) { throw 'BenchmarkLoad requer UpdatedAgent' }
        $loadResult = & docker exec $webName python -B scripts/benchmark_broker_load.py 2>&1
        $loadExit = $LASTEXITCODE
        $loadResult | ForEach-Object { Write-Output $_ }
        foreach ($line in $loadResult) {
            if ([string]$line -match '^AETHERDESK_FIXTURE_ENV=([0-9a-f-]{36})$' -and
                -not $environmentIds.Contains($Matches[1])) { $environmentIds.Add($Matches[1]) }
        }
        if ($loadExit -ne 0) { throw "Falhou: benchmark 20/8 (docker exit $loadExit)" }
    }
    if ($PtyPressure) {
        & docker exec $webName python -B scripts/verify_broker_pty_pressure.py
        Assert-DockerExit 'backpressure PTY com daemon real'
    }
    foreach ($environmentId in $environmentIds) {
        $runtimeName = "aetherdesk-e-$($environmentId.Replace('-', ''))"
        $runtimeMountsJson = & docker container inspect --format '{{json .Mounts}}' $runtimeName
        Assert-DockerExit 'inspecionar mounts do ambiente pessoal'
        $runtimeMounts = $runtimeMountsJson | ConvertFrom-Json
        if ($runtimeMounts | Where-Object { $_.Destination -match 'docker\.sock$' -or $_.Source -match 'docker\.sock$' }) {
            throw 'Ambiente pessoal recebeu socket Docker'
        }
        & docker exec $runtimeName sh -c 'test ! -e /var/run/docker.sock && test ! -e /run/docker.sock'
        Assert-DockerExit 'verificar ausência do socket Docker no ambiente pessoal'
    }
    & docker restart $brokerName | Out-Null
    Assert-DockerExit 'reiniciar broker'
    & docker exec $brokerName python -c `
        "from pathlib import Path; import stat,sqlite3; p=Path('/audit/audit.log'); n=Path('/audit/nonces.sqlite3'); t=p.read_text(); assert stat.S_IMODE(p.stat().st_mode) == 0o600; assert stat.S_IMODE(n.stat().st_mode) == 0o600; assert sqlite3.connect(n).execute('SELECT COUNT(*) FROM broker_nonces').fetchone()[0] > 0; assert 'operation=' in t and 'result=ok' in t and 'fixture-password' not in t and 'broker fixture' not in t; print('AETHERDESK_AUDIT_AND_NONCES_PERSISTED=ok')"
    Assert-DockerExit 'auditoria durável após restart'
    $reconciled = & docker exec $webName python -B scripts/verify_broker_container.py --reconcile 2>&1
    $reconcileExit = $LASTEXITCODE
    $reconciled | ForEach-Object { Write-Output $_ }
    if ($reconcileExit -ne 0) {
        & docker logs --tail 70 $brokerName
        throw "Falhou: reconciliação após restart (docker exit $reconcileExit)"
    }
    if ($AuditRotation) {
        & docker exec $webName python -B scripts/verify_broker_audit_rotation.py
        Assert-DockerExit 'forçar rotação de auditoria com HMAC inválido'
        & docker exec $brokerName python -c `
            "from pathlib import Path; import stat; p=Path('/audit/audit.log'); old=Path('/audit/audit.log.1'); assert old.exists(); assert all(stat.S_IMODE(q.stat().st_mode)==0o600 for q in (p,old)); assert 'UNAUTHENTICATED' in p.read_text() and 'UNAUTHENTICATED' in old.read_text(); print('AETHERDESK_AUDIT_ROTATED=ok')"
        Assert-DockerExit 'auditoria rotativa privada'
    }
    & docker stop --time 10 $brokerName | Out-Null
    Assert-DockerExit 'parar broker para testar rollback restrito'
    & docker exec $webName python -B scripts/verify_broker_container.py --broker-down
    Assert-DockerExit 'web mantém login/preferências e isola arquivo sem broker'
    & docker start $brokerName | Out-Null
    Assert-DockerExit 'restaurar broker'
    $ready = $false
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        & docker exec $brokerName sh -c 'test -S /ipc/broker.sock' 2>$null
        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
        Start-Sleep -Seconds 1
    }
    if (-not $ready) { throw 'Broker não retomou após rollback restrito' }
    & docker exec $webName python -B scripts/verify_broker_container.py --broker-up
    Assert-DockerExit 'web retoma arquivos após broker voltar'
}
finally {
    if ($webName -match '^aetherdesk-w002-web-[0-9a-f]{10}$') {
        $candidates = & docker exec $webName python -B scripts/verify_broker_container.py --lookup-env 2>$null
        foreach ($candidate in $candidates) {
            if ([string]$candidate -match '^[0-9a-f]{8}-[0-9a-f-]{27,}$' -and
                -not $environmentIds.Contains(([string]$candidate).Trim())) {
                $environmentIds.Add(([string]$candidate).Trim())
            }
        }
    }
    foreach ($environmentId in $environmentIds) {
        $compact = $environmentId.Replace('-', '')
        $runtimeName = "aetherdesk-e-$compact"
        $runtimeVolume = "aetherdesk-v-$compact"
        $containerLabelsJson = & docker container inspect --format '{{json .Config.Labels}}' $runtimeName 2>$null
        if ($LASTEXITCODE -eq 0 -and $containerLabelsJson) {
            $containerLabels = $containerLabelsJson | ConvertFrom-Json
            if ($containerLabels.'aetherdesk.environment_id' -eq $environmentId) {
                & docker container rm --force $runtimeName | Out-Null
            }
        }
        $volumeLabelsJson = & docker volume inspect --format '{{json .Labels}}' $runtimeVolume 2>$null
        if ($LASTEXITCODE -eq 0 -and $volumeLabelsJson) {
            $volumeLabels = $volumeLabelsJson | ConvertFrom-Json
            if ($volumeLabels.'aetherdesk.environment_id' -eq $environmentId) {
                & docker volume rm $runtimeVolume | Out-Null
            }
        }
    }
    if ($webName -match '^aetherdesk-w002-web-[0-9a-f]{10}$') { & docker container rm --force $webName 2>$null | Out-Null }
    if ($brokerName -match '^aetherdesk-w002-broker-[0-9a-f]{10}$') { & docker container rm --force $brokerName 2>$null | Out-Null }
    if ($ipcVolume -match '^aetherdesk-w002-ipc-[0-9a-f]{10}$') { & docker volume rm $ipcVolume 2>$null | Out-Null }
    if ($dataVolume -match '^aetherdesk-w002-data-[0-9a-f]{10}$') { & docker volume rm $dataVolume 2>$null | Out-Null }
    if ($auditVolume -match '^aetherdesk-w002-audit-[0-9a-f]{10}$') { & docker volume rm $auditVolume 2>$null | Out-Null }
    if ($builtImage) { & docker image rm $image 2>$null | Out-Null }
    if ($builtRuntimeImage -and $runtimeImage -match '^aetherdesk-files:w002-fixture-[0-9a-f]{10}$') {
        & docker image rm $runtimeImage 2>$null | Out-Null
    }
}
