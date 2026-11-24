param()
$ErrorActionPreference = 'Stop'
$workspace = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$fixtureImage = 'aetherdesk-w003-watcher-fixture:local'
try {
    & docker build --file (Join-Path $workspace 'deploy/Dockerfile.broker-fixture') `
        --tag $fixtureImage (Join-Path $workspace 'deploy') | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Falhou ao construir a fixture do watcher' }
    & docker run --rm --network none --read-only --cap-drop ALL `
        --pids-limit 128 --memory 512m --cpus 1 `
        --tmpfs /tmp:rw,nosuid,nodev,size=256m `
        --mount "type=bind,source=$workspace,target=/src,readonly" `
        --env PYTHONPATH=/src --workdir /src `
        $fixtureImage python -m scripts.benchmark_watcher
    if ($LASTEXITCODE -ne 0) { throw 'Benchmark do watcher falhou' }
}
finally {
    & docker image rm $fixtureImage 2>$null | Out-Null
}
