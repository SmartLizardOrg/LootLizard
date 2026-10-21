<#
Run only on an isolated Windows GitHub-hosted runner. Uses the real frozen
bootstrap and SDK, without Tk, capture, hotkeys, or the public update source.
Fixtures and installed binaries stay beneath RUNNER_TEMP. Synthetic user data
stays in the separate normal per-user data directory and must survive uninstall.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Payload,
    [Parameter(Mandatory = $true)][string]$Feed,
    [Parameter(Mandatory = $true)][string]$Vpk,
    [string]$Python = 'python'
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if (-not $IsWindows -or $env:GITHUB_ACTIONS -cne 'true' -or
    $env:LOOTLIZARD_INSTALL_TEST -cne '1' -or -not $env:RUNNER_TEMP) {
    throw 'Installer integration is restricted to explicitly enabled isolated Windows GitHub Actions runners.'
}
$runnerRoot = [IO.Path]::GetFullPath($env:RUNNER_TEMP).TrimEnd('\', '/')
$testRoot = Join-Path $runnerRoot ('lootlizard-install-' + [Guid]::NewGuid().ToString('N'))
if (-not $testRoot.StartsWith($runnerRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'The resolved installer test directory is outside RUNNER_TEMP.'
}
[IO.Directory]::CreateDirectory($testRoot) | Out-Null
$Payload = (Resolve-Path -LiteralPath $Payload).Path
$Feed = (Resolve-Path -LiteralPath $Feed).Path
$Vpk = (Resolve-Path -LiteralPath $Vpk).Path
$info = Get-Content -Raw -LiteralPath (Join-Path $Payload 'BUILD_INFO.json') | ConvertFrom-Json
$targetVersion = [string]$info.application_version
if ([version]$targetVersion -le [version]'0.7.99') { throw 'The production version must be newer than the stable CI fixture.' }
$steps = [Collections.Generic.List[string]]::new()
$localFeed = Join-Path $testRoot 'target-feed'
[IO.Directory]::CreateDirectory($localFeed) | Out-Null
Get-ChildItem -LiteralPath $Feed -File | Where-Object { $_.Name -eq 'releases.win.json' -or $_.Name.EndsWith('-full.nupkg') } | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $localFeed
}
$Feed = $localFeed

function Invoke-Checked([string]$File, [string[]]$Arguments, [int]$TimeoutSeconds = 180) {
    $start = [Diagnostics.ProcessStartInfo]::new()
    $start.FileName = $File
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.WindowStyle = [Diagnostics.ProcessWindowStyle]::Hidden
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    foreach ($argument in $Arguments) { $start.ArgumentList.Add($argument) }
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $start
    [void]$process.Start()
    $stdout = $process.StandardOutput.ReadToEndAsync()
    $stderr = $process.StandardError.ReadToEndAsync()
    if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
        $process.Kill($true)
        throw "Process timed out: $File"
    }
    $out = $stdout.GetAwaiter().GetResult()
    $err = $stderr.GetAwaiter().GetResult()
    if ($out) { Write-Host $out }
    if ($err) { Write-Host $err }
    if ($process.ExitCode -ne 0) { throw "Process failed ($($process.ExitCode)): $File" }
}

function Assert-NoApp {
    if (Get-Process -Name LootLizard -ErrorAction SilentlyContinue) {
        throw 'A LootLizard process was unexpectedly launched or left running.'
    }
}

$userData = Join-Path $env:LOCALAPPDATA 'LootLizard'
if (Test-Path -LiteralPath $userData) { throw 'An isolated runner must not contain existing LootLizard user data.' }
[IO.Directory]::CreateDirectory((Join-Path $userData 'profiles/installer-fixture')) | Out-Null
$sentinels = @{
    'settings.json' = '{"language":"hu","automatic_map_updates":false,"installer_fixture":"preserve-me"}'
    'maps-cache.json' = '{"installer_fixture":"preserve-cache-byte-for-byte"}'
    'profiles/installer-fixture/profile.json' = '{"installer_fixture":"preserve-profile-byte-for-byte"}'
}
$hashes = @{}
foreach ($entry in $sentinels.GetEnumerator()) {
    $path = Join-Path $userData $entry.Key
    [IO.File]::WriteAllText($path, $entry.Value)
    $hashes[$entry.Key] = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash
}
function Assert-UserData {
    foreach ($entry in $hashes.GetEnumerator()) {
        $path = Join-Path $userData $entry.Key
        if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or
            (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -cne $entry.Value) {
            throw "The installer changed or removed user data: $($entry.Key)"
        }
    }
}

$fixturePayload = Join-Path $testRoot 'fixture-payload'
Copy-Item -LiteralPath $Payload -Destination $fixturePayload -Recurse
[IO.File]::WriteAllText((Join-Path $fixturePayload 'installer-old-fixture.txt'), 'This file must disappear during a full update.')
$fixtureOutput = Join-Path $testRoot 'fixture-release'
Invoke-Checked $Python @((Join-Path $PSScriptRoot 'build_installer.py'), '--payload', $fixturePayload,
    '--output', $fixtureOutput, '--vpk', $Vpk, '--version', '0.7.99', '--ci-fixture') 300
$installRoot = Join-Path $testRoot 'installed'
$exe = Join-Path $installRoot 'current/LootLizard.exe'
$updateExe = Join-Path $installRoot 'Update.exe'
Assert-NoApp
Invoke-Checked (Join-Path $fixtureOutput 'LootLizard-Setup.exe') @('--silent', '--installto', $installRoot,
    '--log', (Join-Path $testRoot 'install.log')) 180
if (-not (Test-Path -LiteralPath $exe -PathType Leaf) -or -not (Test-Path -LiteralPath $updateExe -PathType Leaf)) {
    throw 'Silent installation did not create the expected current executable and Update.exe.'
}
Assert-NoApp
Assert-UserData
$steps.Add('silent-install-and-bootstrap-hooks')

function Invoke-Probe([string]$Name, [string[]]$Options = @()) {
    $path = Join-Path $testRoot ($Name + '.json')
    Invoke-Checked $exe (@('--update-probe', '--report', $path) + $Options) 180
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "The installed headless probe did not report: $Name" }
    return Get-Content -Raw -LiteralPath $path | ConvertFrom-Json
}
$initial = Invoke-Probe 'initial'
if (-not $initial.installed -or $initial.current_version -ne '0.7.99' -or $initial.pending_version) {
    throw 'The installed bootstrap/SDK did not report a clean 0.7.99 fixture.'
}
$steps.Add('installed-sdk-current-version')
$download = Invoke-Probe 'download' @('--ci-update-source', $Feed, '--download')
if ($download.status -ne 'ready' -or $download.current_version -ne '0.7.99' -or
    $download.available_version -ne $targetVersion -or $download.pending_version -ne $targetVersion -or $download.apply_scheduled) {
    throw 'The real installed client did not download and stage the expected target without applying it.'
}
Assert-NoApp
Assert-UserData
$pending = Invoke-Probe 'pending-after-relaunch'
if ($pending.current_version -ne '0.7.99' -or $pending.pending_version -ne $targetVersion) {
    throw 'Pending updates were lost or incorrectly applied by startup bootstrap.'
}
$steps.Add('download-only-pending-survives-relaunch')
$apply = Invoke-Probe 'apply-on-exit' @('--ci-update-source', $Feed, '--download', '--apply-on-exit')
if (-not $apply.apply_scheduled -or $apply.current_version -ne '0.7.99') {
    throw 'The installed SDK did not schedule an exit-only update.'
}
# Update.exe waits for the probe process to exit. Wait for the replacement's
# manifest and removal of the old-only file before probing the new executable.
$deadline = [DateTime]::UtcNow.AddSeconds(180)
$manifest = Join-Path $installRoot 'current/sq.version'
do {
    Start-Sleep -Milliseconds 500
    $manifestText = if (Test-Path -LiteralPath $manifest) { Get-Content -Raw -LiteralPath $manifest -ErrorAction SilentlyContinue } else { '' }
    $updated = $manifestText -match ('<version>' + [regex]::Escape($targetVersion) + '</version>') -and
        -not (Test-Path -LiteralPath (Join-Path $installRoot 'current/installer-old-fixture.txt'))
} until ($updated -or [DateTime]::UtcNow -ge $deadline)
if (-not $updated) { throw 'The exit-only updater did not install the target version before timeout.' }
Start-Sleep -Seconds 2
Assert-NoApp
$final = Invoke-Probe 'updated'
if ($final.current_version -ne $targetVersion -or $final.pending_version) {
    throw 'The updated installed SDK reported the wrong version or retained pending state.'
}
foreach ($file in @('source/scripts/test_installer.ps1', 'source/.github/workflows/release.yml',
                    'LICENSES/Velopack/THIRD_PARTY_NOTICES.md', 'THIRD_PARTY_NOTICES.md')) {
    if (-not (Test-Path -LiteralPath (Join-Path $installRoot ('current/' + $file)) -PathType Leaf)) {
        throw "The installed update omitted source or license material: $file"
    }
}
Assert-NoApp
Assert-UserData
$steps.Add('apply-on-exit-no-restart-and-source-notices')

# Match by installation location rather than relying on an undocumented key name.
$uninstallRoot = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall'
$registryEntries = @(Get-ChildItem -LiteralPath $uninstallRoot -ErrorAction SilentlyContinue | ForEach-Object {
    $entry = Get-ItemProperty -LiteralPath $_.PSPath
    if ($entry.PSObject.Properties['InstallLocation'] -and $entry.InstallLocation -and
        [IO.Path]::GetFullPath([string]$entry.InstallLocation).TrimEnd('\', '/') -eq $installRoot.TrimEnd('\', '/')) { $_.PSPath }
})
if ($registryEntries.Count -lt 1) { throw 'No per-user uninstall registration was created for this installation.' }
$shortcutLocations = @([Environment]::GetFolderPath('DesktopDirectory'), [Environment]::GetFolderPath('Programs'))
$shortcuts = @($shortcutLocations | ForEach-Object { Join-Path $_ 'LootLizard.lnk' } | Where-Object { Test-Path -LiteralPath $_ })
if ($shortcuts.Count -lt 1) { throw 'The configured desktop/Start Menu shortcut was not created.' }
Invoke-Checked $updateExe @('--silent', 'uninstall') 180
$deadline = [DateTime]::UtcNow.AddSeconds(30)
while ((Test-Path -LiteralPath $updateExe) -and [DateTime]::UtcNow -lt $deadline) { Start-Sleep -Milliseconds 500 }
if ((Test-Path -LiteralPath $exe) -or (Test-Path -LiteralPath $updateExe)) { throw 'Uninstall left installed executables behind.' }
foreach ($entry in $registryEntries) { if (Test-Path -LiteralPath $entry) { throw 'Uninstall left its per-user registry entry behind.' } }
foreach ($shortcut in $shortcuts) { if (Test-Path -LiteralPath $shortcut) { throw 'Uninstall left an application shortcut behind.' } }
Assert-NoApp
Assert-UserData
$steps.Add('silent-uninstall-preserves-user-settings-profiles-cache')
$report = @{ status = 'passed'; fixture_version = '0.7.99'; target_version = $targetVersion;
             steps = @($steps); user_data_preserved = $true; restart_launched = $false }
$reportPath = Join-Path $testRoot 'integration-report.json'
$report | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $reportPath -Encoding utf8
Write-Host "Installer integration PASS: $reportPath"
if ($env:GITHUB_OUTPUT) { "report=$reportPath" | Out-File -FilePath $env:GITHUB_OUTPUT -Append -Encoding utf8 }
