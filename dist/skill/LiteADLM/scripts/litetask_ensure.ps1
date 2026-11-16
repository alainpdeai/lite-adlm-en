# LiteTask server watchdog / launcher.
#
# Registered as a Windows scheduled task so the board survives the lifecycle of
# any shell that happens to start it (a process spawned from an agent command is
# reaped together with that command's process group; a process spawned by the
# task scheduler is owned by the OS instead).
#
# Contract:
#   - Idempotent: if <Port> already answers, do nothing and exit 0.
#     Two scheduled triggers (at-logon + every 5 min) therefore cannot stack
#     duplicate servers, and this never clobbers a healthy instance.
#   - Self-healing: if <Port> is silent, launch `node server.js` in <Root> and
#     poll until it answers (exit 0) or 10s expire (exit 1).
#
# Usage:
#   powershell -NoProfile -ExecutionPolicy Bypass -File litetask_ensure.ps1
#   powershell -NoProfile -ExecutionPolicy Bypass -File litetask_ensure.ps1 -Port 45731 -DataDir <tmp> -BackupDir <tmp>
param(
    [int]$Port = 3000,
    [string]$Root = "",
    [string]$Log = "$env:TEMP/litetask_watchdog.log",
    # Optional isolation: both empty by default, i.e. the real board.
    # The grader passes throwaway dirs so it can exercise launch/self-heal
    # WITHOUT touching production data/ (a second real instance would run the
    # startup backup and rotate away old snapshots).
    [string]$DataDir = "",
    [string]$BackupDir = ""
)

# Resolve the repository root from this script's own location. LITETASK_REPO
# overrides it when the watchdog must supervise another checkout.
if (-not $Root) {
    if ($env:LITETASK_REPO) { $Root = $env:LITETASK_REPO }
    else { $Root = Split-Path -Parent $PSScriptRoot }
}

function Test-Port {
    param([int]$P)
    $c = New-Object System.Net.Sockets.TcpClient
    try {
        $c.Connect("127.0.0.1", $P)
        return $true
    } catch {
        return $false
    } finally {
        $c.Dispose()
    }
}

# Raw TCP probe on 127.0.0.1: no HTTP proxy is involved, so the verdict is the
# real state of the port (the ambient http_proxy=127.0.0.1:52671 has previously
# produced fake 502s that looked like "server is down").
if (Test-Port $Port) { exit 0 }

$env:PORT = "$Port"
if ($DataDir) { $env:LITETASK_DATA_DIR = $DataDir }
if ($BackupDir) { $env:LITETASK_BACKUP_DIR = $BackupDir }

$nodeExe = (Get-Command node -ErrorAction SilentlyContinue).Source
if (-not $nodeExe) { exit 1 }

# Start through .NET rather than Start-Process: this machine exports BOTH
# http_proxy and HTTP_PROXY, and Start-Process copies the environment into a
# case-insensitive dictionary -> ArgumentException ("key already added").
# An unpopulated ProcessStartInfo lets the child inherit the parent environment
# via CreateProcess, which has no dictionary to collide on.
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $nodeExe
$psi.Arguments = "server.js"
$psi.WorkingDirectory = $Root
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $true
$proc = [System.Diagnostics.Process]::Start($psi)

try {
    $line = "{0} launched pid={1} port={2} root={3}`n" -f `
        (Get-Date -Format "yyyy-MM-ddTHH:mm:ss"), $proc.Id, $Port, $Root
    [System.IO.File]::AppendAllText($Log, $line)
} catch {}

for ($i = 0; $i -lt 20; $i++) {
    Start-Sleep -Milliseconds 500
    if (Test-Port $Port) { exit 0 }
}
exit 1
