<#
.SYNOPSIS
    Standardized Mu2e control-room start script (PowerShell port of
    start-mu2edaq-bigredbox.sh) for the Big Red Box / DAQ Alert listener.

.DESCRIPTION
    Starts the UDP alert listener in the background. Port precedence:
    $env:CRS_PORT_UDP > built-in default (37020, matching apps.yaml). The
    listener writes its PID to %TEMP%\daq_alert.pid (matching config.py, which
    derives the default from tempfile.gettempdir() on Windows).
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

if (-not $env:CRS_PORT_UDP) { $env:CRS_PORT_UDP = '37020' }
$Port    = [int]$env:CRS_PORT_UDP
$PidFile = Join-Path $env:TEMP 'daq_alert.pid'
$LogFile = Join-Path $env:TEMP 'daq_alert.log'

function Test-ProcessAlive([int]$ProcId) {
    return [bool](Get-Process -Id $ProcId -ErrorAction SilentlyContinue)
}

# Fast path: a listener this script started is recorded in the pid file.
if (Test-Path $PidFile) {
    $oldPid = (Get-Content $PidFile -Raw).Trim()
    if ($oldPid -match '^\d+$' -and (Test-ProcessAlive ([int]$oldPid))) {
        Write-Host "DAQ Alert listener already running (PID $oldPid)."
        exit 0
    }
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
}

# Pick the interpreter / entry point.
$VenvPy     = Join-Path $ScriptDir 'venv\Scripts\python.exe'
$VenvLaunch = Join-Path $ScriptDir 'venv\Scripts\mu2edaq-bigredbox.exe'
if (Test-Path $VenvPy) { $Py = $VenvPy } else { $Py = 'python' }

# Authoritative check: ask the UDP port itself. A listener started by hand (or
# orphaned when the pid file was removed) still owns the port even though the
# pid-file check above cannot see it. Use SO_EXCLUSIVEADDRUSE so a busy port
# raises on Windows (SO_REUSEADDR would let the bind succeed and hide the clash).
$probe = @'
import socket, sys
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
    s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
else:
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
try:
    s.bind(("", int(sys.argv[1])))
except OSError:
    sys.exit(1)
finally:
    s.close()
'@
& $Py -c $probe $Port
if ($LASTEXITCODE -ne 0) {
    Write-Error "UDP port $Port is already in use -- a DAQ Alert listener is already running (its pid file may have been removed). Stop it with .\stop-mu2edaq-bigredbox.ps1."
    exit 1
}

if (Test-Path $VenvLaunch)      { $LaunchExe = $VenvLaunch; $LaunchArgs = @() }
elseif (Get-Command mu2edaq-bigredbox -ErrorAction SilentlyContinue) { $LaunchExe = 'mu2edaq-bigredbox'; $LaunchArgs = @() }
else { $LaunchExe = $Py; $LaunchArgs = @((Join-Path $ScriptDir 'daq_alert.py')) }

Write-Host "Starting Big Red Box / DAQ Alert listener (udp=$Port)"
$proc = Start-Process -FilePath $LaunchExe -ArgumentList $LaunchArgs `
    -RedirectStandardOutput $LogFile -RedirectStandardError "$LogFile.err" `
    -WindowStyle Hidden -PassThru
Start-Sleep -Seconds 1
if (-not (Test-ProcessAlive $proc.Id)) {
    Write-Error "DAQ Alert listener failed to start; see $LogFile"
    if (Test-Path $LogFile) { Get-Content $LogFile -Tail 3 | Write-Host }
    exit 1
}
Write-Host "DAQ Alert listener started (PID $($proc.Id)); log: $LogFile"
