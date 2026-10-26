# Router selection only: no service startup, credential access or data deletion.
function Resolve-RouterInstallation {
    param([string]$OverridePath = '', [string[]]$GlobalPrefixes = @())
    $candidates = @()
    if ($OverridePath) {
        if (-not (Test-Path -LiteralPath $OverridePath -PathType Leaf)) {
            throw "Khong tim thay RouterCliPath: $OverridePath"
        }
        $candidates = @($OverridePath)
    } else {
        if ($GlobalPrefixes.Count -eq 0) {
            $npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
            if ($npm) {
                $prefixOutput = & $npm.Source config get prefix
                if ($LASTEXITCODE -eq 0) {
                    $GlobalPrefixes += @($prefixOutput | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | ForEach-Object { $_.Trim() })
                }
            }
            if ($env:APPDATA) { $GlobalPrefixes += Join-Path $env:APPDATA 'npm' }
            $command = Get-Command 9router.cmd -ErrorAction SilentlyContinue
            if ($command) { $GlobalPrefixes += Split-Path -Parent $command.Source }
        }
        foreach ($prefix in $GlobalPrefixes) {
            $candidates += Join-Path $prefix 'node_modules/9router/cli.js'
        }
    }
    foreach ($candidate in $candidates) {
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
        $cli = (Resolve-Path -LiteralPath $candidate).ProviderPath
        $packagePath = Join-Path (Split-Path -Parent $cli) 'package.json'
        if (-not (Test-Path -LiteralPath $packagePath -PathType Leaf)) { continue }
        $package = Get-Content -LiteralPath $packagePath -Raw | ConvertFrom-Json
        if ($package.name -ne '9router' -or -not $package.version) { continue }
        return [PSCustomObject]@{ CliPath = $cli; Version = $package.version; ExplicitOverride = [bool]$OverridePath }
    }
    throw 'Khong tim thay 9Router global. Chay npm i -g 9router@latest --prefer-online. Khong tu dong dung/cai ban local cu.'
}

function Assert-RunningRouterSource {
    param([string]$CliPath, [object[]]$Listeners, [hashtable]$Processes)
    if ($Listeners.Count -eq 0) { throw 'Router HTTP phan hoi nhung khong xac dinh duoc tien trinh cong 20128.' }
    $root = Split-Path -Parent $CliPath
    $entries = @($CliPath, (Join-Path $root 'app/server.js'), (Join-Path $root 'app/custom-server.js'))
    foreach ($listener in $Listeners) {
        $process = $Processes[[int]$listener.OwningProcess]
        $matchesSource = $false
        if ($process -and $process.Name -eq 'node.exe') {
            $command = ([string]$process.CommandLine).Replace('/', '\')
            foreach ($entry in $entries) {
                $pattern = [regex]::Escape($entry.Replace('/', '\')) + '(?="|\s|$)'
                if ($command -match $pattern) { $matchesSource = $true; break }
            }
        }
        if (-not $matchesSource) {
            throw 'Cong 20128 dang dung router/ung dung khac, co the la ban local cu. Khong tu dong dung lai. Chay stop_web roi run_web khi san sang; du lieu van duoc giu.'
        }
    }
}
