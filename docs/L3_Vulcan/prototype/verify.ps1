$ErrorActionPreference = 'Stop'
$suffix = [guid]::NewGuid().ToString('N').Substring(0, 12)
$oldImage = "aetherdesk-w001-alpine:$suffix"
$newImage = "aetherdesk-w001-busybox:$suffix"
$aliceVolume = "aetherdesk-w001-alice-$suffix"
$bobVolume = "aetherdesk-w001-bob-$suffix"

function Run-Docker {
    param([string[]]$DockerArgs)
    & docker @DockerArgs
    if ($LASTEXITCODE -ne 0) { throw "docker $($DockerArgs[0]) falhou: $LASTEXITCODE" }
}

function Run-Account {
    param([string]$Image, [string]$Volume, [string]$Command)
    Run-Docker -DockerArgs @('run', '--rm', '--network', 'none', '--read-only',
        '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
        '--pids-limit', '64', '--memory', '128m', '--cpus', '0.5',
        '--mount', "type=volume,source=$Volume,target=/persist",
        $Image, 'sh', '-ceu', $Command)
}

try {
    Run-Docker -DockerArgs @('build', '--network', 'none', '-f', "$PSScriptRoot\Dockerfile.alpine", '-t', $oldImage, $PSScriptRoot)
    Run-Docker -DockerArgs @('build', '--network', 'none', '-f', "$PSScriptRoot\Dockerfile.busybox", '-t', $newImage, $PSScriptRoot)
    Run-Docker -DockerArgs @('volume', 'create', $aliceVolume)
    Run-Docker -DockerArgs @('volume', 'create', $bobVolume)
    Run-Docker -DockerArgs @('run', '--rm', '--mount', "type=volume,source=$aliceVolume,target=/persist", 'alpine:3.20', 'chown', '10001:10001', '/persist')
    Run-Docker -DockerArgs @('run', '--rm', '--mount', "type=volume,source=$bobVolume,target=/persist", 'alpine:3.20', 'chown', '10001:10001', '/persist')
    Write-Output 'FASE 1: contas separadas na mesma imagem'
    Run-Account $oldImage $aliceVolume 'cd /; printf alice > /dados.txt; test "$(pwd)" = /; test "$(cat /dados.txt)" = alice; test "$(id -u)" = 10001; printf "alice pwd=%s arquivo=%s uid=%s\n" "$(pwd)" "$(cat /dados.txt)" "$(id -u)"'
    Run-Account $oldImage $bobVolume 'cd /; printf bob > /dados.txt; test "$(pwd)" = /; test "$(cat /dados.txt)" = bob; test "$(id -u)" = 10001; printf "bob pwd=%s arquivo=%s uid=%s\n" "$(pwd)" "$(cat /dados.txt)" "$(id -u)"'
    Write-Output 'FASE 2: reabertura preserva arquivos distintos'
    Run-Account $oldImage $aliceVolume 'cd /; test "$(cat /dados.txt)" = alice; awk "{ print \$0 }" /dados.txt'
    Run-Account $oldImage $bobVolume 'cd /; test "$(cat /dados.txt)" = bob; awk "{ print \$0 }" /dados.txt'
    Write-Output 'FASE 3: imagem base substituida, volume preservado'
    Run-Account $newImage $aliceVolume 'cd /; test "$(cat /dados.txt)" = alice; printf "alice apos atualizacao=%s\n" "$(cat /dados.txt)"'
    Run-Account $newImage $bobVolume 'cd /; test "$(cat /dados.txt)" = bob; printf "bob apos atualizacao=%s\n" "$(cat /dados.txt)"'
    Write-Output 'RESULTADO: PASSOU'
}
finally {
    & docker volume rm $aliceVolume $bobVolume | Out-Null
    & docker image rm $oldImage $newImage | Out-Null
}
