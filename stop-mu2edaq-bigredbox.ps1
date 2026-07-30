<#
.SYNOPSIS
    Standardized Mu2e control-room stop script (PowerShell port of
    stop-mu2edaq-bigredbox.sh). Stops the DAQ Alert listener via its pid file
    (graceful CloseMainWindow/Stop, then a forced kill after a timeout).

.PARAMETER PidFile
    Path to the pid file. Defaults to %TEMP%\daq_alert.pid.
#>
[CmdletBinding()]
param(
    [string]$PidFile = (Join-Path $env:TEMP 'daq_alert.pid')
)

$ErrorActionPreference = 'Stop'
$Timeout = if ($env:CRS_STOP_TIMEOUT) { [int]$env:CRS_STOP_TIMEOUT } else { 10 }
$Port    = if ($env:CRS_PORT_UDP)     { [int]$env:CRS_PORT_UDP }     else { 37020 }

function Test-ProcessAlive([int]$ProcId) {
    return [bool](Get-Process -Id $ProcId -ErrorAction SilentlyContinue)
}

# A listener started by hand, or one whose pid file was deleted, still owns the
# UDP port. Fall back to the port holder so such an orphan can still be stopped
# -- but only if it is actually our application, never an unrelated holder.
function Find-Orphan {
    try {
        $conns = Get-NetUDPEndpoint -LocalPort $Port -ErrorAction SilentlyContinue
    } catch { return $null }
    foreach ($c in $conns) {
        $proc = Get-Process -Id $c.OwningProcess -ErrorAction SilentlyContinue
        if ($proc -and ($proc.Path -match 'python' -or $proc.ProcessName -match 'mu2edaq[-_]bigredbox')) {
            # Confirm the command line references our app before touching it.
            $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$($proc.Id)" -ErrorAction SilentlyContinue).CommandLine
            if ($cmd -match 'mu2edaq[-_]bigredbox|daq_alert') { return $proc.Id }
        }
    }
    return $null
}

if (-not (Test-Path $PidFile)) {
    $orphan = Find-Orphan
    if ($orphan) {
        Write-Host "No pid file ($PidFile), but a DAQ Alert listener holds UDP $Port (pid $orphan)."
        $ProcId = $orphan
    } else {
        Write-Host "DAQ Alert listener not running (no pid file: $PidFile)"
        exit 0
    }
} else {
    $ProcId = [int]((Get-Content $PidFile -Raw).Trim())
}

if (-not (Test-ProcessAlive $ProcId)) {
    Write-Host "DAQ Alert listener not running (stale pid $ProcId); cleaning up"
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    exit 0
}

Write-Host "Stopping DAQ Alert listener (pid $ProcId)..."
$proc = Get-Process -Id $ProcId -ErrorAction SilentlyContinue
if ($proc) { $proc.CloseMainWindow() | Out-Null }
for ($i = 0; $i -lt $Timeout; $i++) {
    if (-not (Test-ProcessAlive $ProcId)) { break }
    Start-Sleep -Seconds 1
}
if (Test-ProcessAlive $ProcId) {
    Write-Host "did not exit within ${Timeout}s; forcing"
    Stop-Process -Id $ProcId -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
}
Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
Write-Host 'DAQ Alert listener stopped'
