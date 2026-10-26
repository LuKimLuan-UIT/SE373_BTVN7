# Router selection only: no service startup, credential access or data deletion.
function Resolve-RouterInstallation {
    param([string]$OverridePath = '', [string[]]$GlobalPrefixes = @(), [switch]$Diagnostics)
    $candidates = New-Object 'System.Collections.Generic.List[string]'
    $problems = New-Object 'System.Collections.Generic.List[string]'
    function Normalize-RouterPath([string]$Value) {
        $clean = [regex]::Replace($Value, '\x1b\[[0-9;]*[A-Za-z]', '').Trim().Trim('"')
        return [Environment]::ExpandEnvironmentVariables($clean)
    }
    if ($OverridePath) {
        [void]$candidates.Add((Normalize-RouterPath $OverridePath))
    } else {
        $prefixes = @($GlobalPrefixes)
        # Explicit test/caller prefixes are isolated from discovery, including an empty list.
        if (-not $PSBoundParameters.ContainsKey('GlobalPrefixes')) {
            $npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
            if ($npm) {
                try {
                    $output = @(& $npm.Source config get prefix 2>$null)
                    if ($LASTEXITCODE -eq 0) { $prefixes += $output }
                    $roots = @(& $npm.Source root -g 2>$null)
                    if ($LASTEXITCODE -eq 0) {
                        foreach ($root in $roots) {
                            $clean = Normalize-RouterPath ([string]$root)
                            if ($clean) { [void]$candidates.Add((Join-Path $clean '9router/cli.js')) }
                        }
                    }
                } catch {
                    if ($Diagnostics) { Write-Host 'npm discovery failed; checking standard global directories.' }
                }
            }
            if ($env:NPM_CONFIG_PREFIX) { $prefixes += $env:NPM_CONFIG_PREFIX }
            if ($env:APPDATA) { $prefixes += Join-Path $env:APPDATA 'npm' }
            if ($env:USERPROFILE) { $prefixes += Join-Path $env:USERPROFILE 'AppData/Roaming/npm' }
            $knownAppData = [Environment]::GetFolderPath([Environment+SpecialFolder]::ApplicationData)
            if ($knownAppData) { $prefixes += Join-Path $knownAppData 'npm' }
            foreach ($command in @(Get-Command 9router.cmd -All -ErrorAction SilentlyContinue)) {
                if ($command.Source) { $prefixes += Split-Path -Parent $command.Source }
            }
            if ($Diagnostics) {
                Write-Host "Router discovery: APPDATA=$env:APPDATA; USERPROFILE=$env:USERPROFILE"
            }
        }
        foreach ($prefix in $prefixes) {
            $clean = Normalize-RouterPath ([string]$prefix)
            if ($clean) { [void]$candidates.Add((Join-Path $clean 'node_modules/9router/cli.js')) }
        }
    }
    $seen = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    foreach ($candidate in $candidates) {
        try { $cli = [IO.Path]::GetFullPath((Normalize-RouterPath $candidate)) }
        catch { [void]$problems.Add("Invalid path: $candidate"); continue }
        if (-not $seen.Add($cli)) { continue }
        $reason = ''
        if (-not [IO.File]::Exists($cli)) { $reason = 'cli.js not found or not readable' }
        else {
            $packagePath = [IO.Path]::Combine([IO.Path]::GetDirectoryName($cli), 'package.json')
            if (-not [IO.File]::Exists($packagePath)) { $reason = 'package.json not found or not readable' }
            else {
                try {
                    $package = [IO.File]::ReadAllText($packagePath) | ConvertFrom-Json
                    if ($package.name -ne '9router') { $reason = 'package name is not 9router' }
                    elseif (-not $package.version) { $reason = 'package version is missing' }
                    else {
                        if ($Diagnostics) { Write-Host "FOUND: $cli (version $($package.version))" }
                        return [PSCustomObject]@{CliPath=$cli;Version=$package.version;ExplicitOverride=[bool]$OverridePath}
                    }
                } catch { $reason = 'cannot read/parse package.json' }
            }
        }
        [void]$problems.Add("$cli => $reason")
        if ($Diagnostics) { Write-Host "SKIP: $cli => $reason" }
    }
    $details = if ($problems.Count) { $problems -join "`n" } else { 'No global candidate paths discovered.' }
    throw "Khong nhan dien duoc 9Router global.`n$details`nKhong tu dung ban local cu. Co the chi dinh -RouterCliPath voi duong dan global."
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
