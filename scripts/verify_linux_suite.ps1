# Regressão Linux descartável: executa os testes Unix e Docker legados sem alterar o host.
param([string[]]$TestNames = @())
$ErrorActionPreference = 'Stop'
$workspace = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$image = 'aetherdesk-w002-broker-fixture:local'
$builtImage = $false
$testArgs = if ($TestNames.Count) { @('-B', '-m', 'unittest') + $TestNames } `
    else { @('-B', '-m', 'unittest', 'discover', '-v') }
try {
    $availableImages = @(& docker image ls --format '{{.Repository}}:{{.Tag}}')
    if ($LASTEXITCODE -ne 0) { throw 'Falhou ao consultar imagens Docker' }
    if ($availableImages -notcontains $image) {
        & docker build --file (Join-Path $workspace 'deploy/Dockerfile.broker-fixture') `
            --tag $image (Join-Path $workspace 'deploy') | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Falhou ao construir imagem da regressão Linux' }
        $builtImage = $true
    }
    & docker run --rm --network none --read-only --cap-drop ALL `
        --tmpfs /tmp:rw,nosuid,nodev,size=256m `
        --mount "type=bind,source=$workspace,target=/src,readonly" `
        --mount 'type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock' `
        --env PYTHONPATH=/src --env PYTHONDONTWRITEBYTECODE=1 `
        --env AETHERDESK_DOCKER_TEST=1 --workdir /src `
        $image python @testArgs
    if ($LASTEXITCODE -ne 0) { throw 'Regressão Linux falhou' }
}
finally {
    if ($builtImage) { & docker image rm $image 2>$null | Out-Null }
}
