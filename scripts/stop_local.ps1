[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [ValidateRange(1, 65535)][int]$AppPort = 8000,
    [ValidateRange(1, 65535)][int]$RouterPort = 20128
)

$ErrorActionPreference = 'Stop'

function Test-WebProcess($Process) {
    return $Process.Name -like 'python*.exe' -and
        $Process.CommandLine -match '(?i)(?:^|\s)-m\s+uvicorn\s+memory_agent\.ui\.app:app(?:\s|$)'
}

function Test-RouterProcess($Process) {
    return $Process.Name -eq 'node.exe' -and
        $Process.CommandLine -match '(?i)[\\/]9router[\\/](?:cli\.js|app[\\/](?:custom-server|server)\.js)(?:"|\s|$)'
}

function Test-RouterCli($Process) {
    return (Test-RouterProcess $Process) -and
        $Process.CommandLine -match '(?i)[\\/]9router[\\/]cli\.js(?:"|\s|$)'
}

function Get-RouterRoot($Process, $Processes) {
    # The CLI supervises/restarts the server and owns the tray. Stop its whole tree.
    $root = $Process
    $seen = @{}
    while ($root -and -not $seen.ContainsKey([int]$root.ProcessId)) {
        $seen[[int]$root.ProcessId] = $true
        $parent = $Processes[[int]$root.ParentProcessId]
        if (-not $parent -or -not (Test-RouterProcess $parent)) { break }
        # Windows can recycle a parent PID after it exits.
        if ($parent.CreationDate -gt $root.CreationDate) { break }
        $root = $parent
    }
    return $root
}

try {
    $processes = @{}
    foreach ($process in Get-CimInstance Win32_Process) {
        $processes[[int]$process.ProcessId] = $process
    }
    $listeners = @(Get-NetTCPConnection -State Listen)
    $failed = $false
    $services = @(
        @{ Name = 'Memory Agent'; Port = $AppPort; Router = $false },
        @{ Name = '9Router'; Port = $RouterPort; Router = $true }
    )

    foreach ($service in $services) {
        $targets = @{}
        $owners = @($listeners | Where-Object LocalPort -eq $service.Port |
            Select-Object -ExpandProperty OwningProcess -Unique)
        foreach ($owner in $owners) {
            $process = $processes[[int]$owner]
            $matchesService = if ($service.Router) { Test-RouterProcess $process } else { Test-WebProcess $process }
            if (-not $matchesService) {
                Write-Warning "Cong $($service.Port) thuoc tien trinh khac (PID $owner); khong dung tien trinh nay."
                $failed = $true
                continue
            }
            if ($service.Router) { $process = Get-RouterRoot $process $processes }
            $targets[[int]$process.ProcessId] = $process
        }

        if ($service.Router) {
            # Also find a tray/supervisor whose server has already stopped.
            foreach ($process in $processes.Values) {
                if (-not (Test-RouterCli $process)) { continue }
                $portMatch = [regex]::Match($process.CommandLine, '(?i)(?:^|\s)(?:--port|-p)(?:\s+|=)(\d+)(?=\s|$)')
                $cliPort = if ($portMatch.Success) { [int]$portMatch.Groups[1].Value } else { 20128 }
                if ($cliPort -eq $RouterPort) {
                    $root = Get-RouterRoot $process $processes
                    $targets[[int]$root.ProcessId] = $root
                }
            }
        }

        if ($targets.Count -eq 0) {
            if ($owners.Count -eq 0) { Write-Output "$($service.Name): da dung / khong chay." }
            continue
        }

        foreach ($target in $targets.Values) {
            $processId = [int]$target.ProcessId
            if (-not $PSCmdlet.ShouldProcess("$($service.Name), PID $processId, cong $($service.Port)", 'Dung cay tien trinh')) { continue }
            $current = Get-CimInstance Win32_Process -Filter "ProcessId = $processId"
            if (-not $current) { continue }
            if ($current.CreationDate -ne $target.CreationDate) {
                Write-Warning "PID $processId da duoc tai su dung; khong dung tien trinh nay."
                $failed = $true
                continue
            }
            & "$env:SystemRoot\System32\taskkill.exe" /PID $processId /T /F
            if ($LASTEXITCODE -ne 0 -and (Get-Process -Id $processId -ErrorAction SilentlyContinue)) {
                Write-Warning "Khong dung duoc $($service.Name), PID $processId."
                $failed = $true
            }
        }

        if (-not $WhatIfPreference) {
            $remaining = @()
            for ($attempt = 0; $attempt -lt 20; $attempt++) {
                $remaining = @(Get-NetTCPConnection -State Listen | Where-Object LocalPort -eq $service.Port)
                if ($remaining.Count -eq 0) { break }
                Start-Sleep -Milliseconds 200
            }
            if ($remaining.Count -gt 0) {
                Write-Warning "Cong $($service.Port) van dang mo."
                $failed = $true
            } else {
                Write-Output "$($service.Name): da dung."
            }
        }
    }

    Write-Output 'Memory, lich su, checkpoint va cac file du lieu duoc giu nguyen.'
    if ($failed) { exit 1 }
} catch {
    Write-Error "Khong the dung dich vu: $($_.Exception.Message)" -ErrorAction Continue
    exit 1
}
