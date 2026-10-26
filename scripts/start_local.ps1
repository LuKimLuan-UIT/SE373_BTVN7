param(
    [string]$CondaEnv = 'SE373',
    [int]$AppPort = 8000,
    [string]$RouterCliPath = '',
    [switch]$CheckRouterOnly
)

$ErrorActionPreference = 'Stop'
$projectDir = Split-Path -Parent $PSScriptRoot
function Test-LocalHttp([string]$Url) {
    try {
        $response = Invoke-WebRequest -Uri $Url -TimeoutSec 3 -UseBasicParsing
        return $response.StatusCode -eq 200
    } catch { return $false }
}

# Select the installed global package before checking a running server.
. (Join-Path $PSScriptRoot 'router_selection.ps1')
$router = Resolve-RouterInstallation -OverridePath $RouterCliPath -Diagnostics:$CheckRouterOnly
$routerCli = $router.CliPath
Write-Output "9Router CLI: $routerCli"
Write-Output "9Router installed version: $($router.Version)"
$routerReady = Test-LocalHttp 'http://127.0.0.1:20128/v1/models'
if ($routerReady) {
    $listeners = @(Get-NetTCPConnection -State Listen | Where-Object LocalPort -eq 20128)
    $processes = @{}
    foreach ($process in Get-CimInstance Win32_Process) { $processes[[int]$process.ProcessId] = $process }
    Assert-RunningRouterSource -CliPath $routerCli -Listeners $listeners -Processes $processes
    Write-Output '9Router dang chay: duong dan tien trinh khop ban da chon.'
}
if ($CheckRouterOnly) {
    Write-Output "Router running: $routerReady. Check only; no services started/stopped."
    return
}
$pythonExe = Join-Path $env:USERPROFILE "miniconda3/envs/$CondaEnv/python.exe"
if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "Khong tim thay Python cua Conda env $CondaEnv tai $pythonExe"
}
$nodeExe = (Get-Command node.exe -ErrorAction Stop).Source
$logDir = Join-Path $projectDir 'data/service-logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
if (-not $routerReady) {
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
