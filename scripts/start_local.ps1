param(
    [string]$CondaEnv = 'SE373',
    [int]$AppPort = 8000,
    [string]$RouterCliPath = ''
)

$ErrorActionPreference = 'Stop'
$projectDir = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $env:USERPROFILE "miniconda3/envs/$CondaEnv/python.exe"
if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "Khong tim thay Python cua Conda env $CondaEnv tai $pythonExe"
}
$nodeExe = (Get-Command node.exe -ErrorAction Stop).Source
$logDir = Join-Path $projectDir 'data/service-logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Test-LocalHttp([string]$Url) {
    try {
        $response = Invoke-WebRequest -Uri $Url -TimeoutSec 3 -UseBasicParsing
        return $response.StatusCode -eq 200
    } catch { return $false }
}

# A running router can be reused even if its original installation has moved.
$routerReady = Test-LocalHttp 'http://127.0.0.1:20128/v1/models'
if (-not $routerReady) {
$localRouterDir = Join-Path $projectDir 'data/local-router'
$localRouterCli = Join-Path $localRouterDir 'node_modules/9router/cli.js'
$routerCandidates = @($localRouterCli)
if ($RouterCliPath) {
    if (-not (Test-Path -LiteralPath $RouterCliPath -PathType Leaf)) {
        throw "Khong tim thay file RouterCliPath: $RouterCliPath"
    }
    $routerCandidates += $RouterCliPath
}
$routerCommand = Get-Command 9router.cmd -ErrorAction SilentlyContinue
if ($routerCommand) {
    $routerCandidates += Join-Path (Split-Path -Parent $routerCommand.Source) 'node_modules/9router/cli.js'
}
if ($env:APPDATA) {
    $routerCandidates += Join-Path $env:APPDATA 'npm/node_modules/9router/cli.js'
}
if ($env:USERPROFILE) {
    $routerCandidates += Join-Path $env:USERPROFILE 'AppData/Roaming/npm/node_modules/9router/cli.js'
}
$routerCli = $routerCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
if (-not $routerCli) {
    $npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if ($npmCommand) {
        $npmOutput = & $npmCommand.Source config get prefix
        if ($LASTEXITCODE -eq 0) {
            foreach ($prefixLine in $npmOutput) {
                if ([string]::IsNullOrWhiteSpace($prefixLine)) { continue }
                $candidate = Join-Path $prefixLine.Trim() 'node_modules/9router/cli.js'
                if (Test-Path -LiteralPath $candidate -PathType Leaf) {
                    $routerCli = $candidate
                    break
                }
            }
        }
    }
}
if (-not $routerCli) {
    $npmCommand = Get-Command npm.cmd -ErrorAction Stop
    Write-Output "Khong thay 9Router global. Dang cai ban rieng cho du an tai $localRouterDir ..."
    & $npmCommand.Source install --prefix $localRouterDir --no-audit --no-fund '9router@0.5.104'
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $localRouterCli -PathType Leaf)) {
        throw 'Cai 9Router cho du an that bai. Xem loi npm o tren va kiem tra ket noi mang.'
    }
    $routerCli = $localRouterCli
}

    Write-Output "9Router CLI: $routerCli"
    Start-Process -FilePath $nodeExe -ArgumentList @(
        ('"{0}"' -f $routerCli), '--host', '127.0.0.1', '--port', '20128',
        '--tray', '--skip-update', '--no-browser', '--log'
    ) -WorkingDirectory $projectDir -WindowStyle Hidden `
      -RedirectStandardOutput (Join-Path $logDir '9router.out.log') `
      -RedirectStandardError (Join-Path $logDir '9router.err.log') | Out-Null
    $routerReady = $false
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        if (Test-LocalHttp 'http://127.0.0.1:20128/v1/models') {
            $routerReady = $true
            break
        }
        Start-Sleep -Seconds 1
    }
    if (-not $routerReady) { throw "9Router chua san sang. Xem log tai $logDir" }
}

$env:PYTHONPATH = Join-Path $projectDir 'src'
$env:PYTHONIOENCODING = 'utf-8'
$appUrl = "http://127.0.0.1:$AppPort"
if (-not (Test-LocalHttp "$appUrl/api/health")) {
    Start-Process -FilePath $pythonExe -ArgumentList @(
        '-m', 'uvicorn', 'memory_agent.ui.app:app', '--host', '127.0.0.1',
        '--port', "$AppPort"
    ) -WorkingDirectory $projectDir -WindowStyle Hidden `
      -RedirectStandardOutput (Join-Path $logDir 'memory-agent.out.log') `
      -RedirectStandardError (Join-Path $logDir 'memory-agent.err.log') | Out-Null
    $appReady = $false
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        if (Test-LocalHttp "$appUrl/api/health") {
            $appReady = $true
            break
        }
        Start-Sleep -Seconds 1
    }
    if (-not $appReady) { throw "Ung dung chua san sang. Xem log tai $logDir" }
}
$health = Invoke-RestMethod -Uri "$appUrl/api/health" -TimeoutSec 10
if (-not $health.ok) { throw "Ung dung bao thieu cau hinh: $($health.detail)" }
Write-Output "9Router: http://127.0.0.1:20128/dashboard"
Write-Output "Memory Agent (Conda $CondaEnv): $appUrl"
Write-Output "Logs: $logDir"
