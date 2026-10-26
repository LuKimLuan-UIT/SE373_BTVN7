"""Router selection uses fake installations/processes; never touches a running service."""
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


@pytest.mark.skipif(sys.platform != "win32", reason="Windows PowerShell launcher")
def test_global_selection_and_running_source_guard(tmp_path):
    helper = Path(__file__).resolve().parents[1] / "scripts/router_selection.ps1"
    script = tmp_path / "check-router.ps1"
    script.write_text(r'''
param([string]$Helper,[string]$Root)
$ErrorActionPreference='Stop'
. $Helper
function Install-Fake([string]$Prefix,[string]$Version) {
    $dir=Join-Path $Prefix 'node_modules/9router'
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    Set-Content -LiteralPath (Join-Path $dir 'cli.js') -Value '// test only'
    @{name='9router';version=$Version} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $dir 'package.json')
    return Join-Path $dir 'cli.js'
}
$globalPrefix=Join-Path $Root 'global with spaces'
$globalCli=Install-Fake $globalPrefix '0.5.111'
$localCli=Install-Fake (Join-Path $Root 'data/local-router') '0.5.104'
$chosen=Resolve-RouterInstallation -GlobalPrefixes @($globalPrefix)
if ($chosen.Version -ne '0.5.111' -or $chosen.CliPath -ne $globalCli) { throw 'Global not selected' }
$env:TEST_ROUTER_PREFIX=$globalPrefix
$quoted=Resolve-RouterInstallation -GlobalPrefixes @('"%TEST_ROUTER_PREFIX%"')
if ($quoted.CliPath -ne $globalCli) { throw 'Quoted/environment prefix was not normalized' }
$badPrefix=Join-Path $Root 'bad-package'
$badCli=Install-Fake $badPrefix '0.5.110'
Set-Content -LiteralPath (Join-Path (Split-Path $badCli) 'package.json') -Value 'not JSON'
$fallback=Resolve-RouterInstallation -GlobalPrefixes @($badPrefix,$globalPrefix)
if ($fallback.CliPath -ne $globalCli) { throw 'Bad metadata must not prevent checking the next candidate' }
$missing=Join-Path $Root 'missing-global'
$refused=$false
try { Resolve-RouterInstallation -GlobalPrefixes @($missing) | Out-Null } catch {
    $refused=$true
    if ($_.Exception.Message -notlike '*cli.js not found*' -or $_.Exception.Message -notlike ('*'+$missing+'*')) { throw 'Missing diagnostic reason/path' }
}
if (-not $refused) { throw 'Local fallback must not happen' }
$override=Resolve-RouterInstallation -OverridePath $localCli
if ($override.Version -ne '0.5.104' -or -not $override.ExplicitOverride) { throw 'Explicit override broken' }
$listeners=@([PSCustomObject]@{OwningProcess=100})
$processes=@{100=[PSCustomObject]@{Name='node.exe';CommandLine=('node.exe "'+(Join-Path (Split-Path $globalCli) 'app/custom-server.js')+'"')}}
Assert-RunningRouterSource -CliPath $globalCli -Listeners $listeners -Processes $processes
$processes[100].CommandLine='node.exe "'+(Join-Path (Split-Path $localCli) 'app/server.js')+'"'
$refused=$false
try { Assert-RunningRouterSource -CliPath $globalCli -Listeners $listeners -Processes $processes } catch { $refused=$true }
if (-not $refused) { throw 'Old running local router must be rejected' }
$processes[100].CommandLine='node.exe "'+$globalCli+'.other"'
$refused=$false
try { Assert-RunningRouterSource -CliPath $globalCli -Listeners $listeners -Processes $processes } catch { $refused=$true }
if (-not $refused) { throw 'Partial path match must be rejected' }
# A stale APPDATA / unavailable npm in an activated terminal must still find the
# standard global install under USERPROFILE. No real global folder is modified.
$fakeProfile=Join-Path $Root 'profile'
$profilePrefix=Join-Path $fakeProfile 'AppData/Roaming/npm'
$profileCli=Install-Fake $profilePrefix '0.5.111'
$env:APPDATA=Join-Path $Root 'stale-appdata'
$env:USERPROFILE=$fakeProfile
$env:NPM_CONFIG_PREFIX=Join-Path $Root 'stale-prefix'
function Get-Command { param($Name,[switch]$All,$ErrorAction) return $null }
$profileFound=Resolve-RouterInstallation
if ($profileFound.CliPath -ne $profileCli) { throw 'USERPROFILE global fallback not used' }
'Global priority, missing-global refusal, explicit override and running-source guard: PASS'
''', encoding="utf-8")
    result = subprocess.run(
        [shutil.which("powershell.exe"), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
         str(script), "-Helper", str(helper), "-Root", str(tmp_path)],
        capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
