<#
.SYNOPSIS
    Set up the Python virtual environment for mu2edaq-bigredbox (the PyQt6 DAQ
    alert daemon) and install/update its dependencies. PowerShell port of
    bootstrap.sh for Windows.

.DESCRIPTION
    Creates venv\ next to this script and installs the package (editable).
    mu2edaq-discovery is best-effort: a sibling checkout is preferred, then a
    GitHub install; the app degrades gracefully to no discovery when absent.

.PARAMETER Dev
    Also install the [dev] extras (pytest, pytest-qt).

.EXAMPLE
    .\bootstrap.ps1
    .\bootstrap.ps1 -Dev
#>
[CmdletBinding()]
param(
    [switch]$Dev
)

$ErrorActionPreference = 'Stop'
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Venv = Join-Path $Here 'venv'

# Prefer 'python'; fall back to the py launcher. ('python3' on a stock Windows
# install is the Microsoft Store alias stub, so it is not used here.)
$Python = $env:PYTHON
if (-not $Python) {
    if (Get-Command python -ErrorAction SilentlyContinue) { $Python = 'python' }
    elseif (Get-Command py -ErrorAction SilentlyContinue) { $Python = 'py' }
    else { Write-Error 'Python 3.9+ not found on PATH. Install it first.'; exit 1 }
}

$pyver = & $Python -c 'import sys; print("%d.%d" % sys.version_info[:2])'
& $Python -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)'
if ($LASTEXITCODE -ne 0) { Write-Error "Python >= 3.9 required, found $pyver"; exit 1 }
Write-Host "Using Python $pyver ($Python)"

if (-not (Test-Path $Venv)) {
    Write-Host "Creating virtual environment in $Venv"
    & $Python -m venv $Venv
}

$VenvPy = Join-Path $Venv 'Scripts\python.exe'
& $VenvPy -m pip install --upgrade pip | Out-Null

# mu2edaq-discovery (auto-discovery protocol) -- best effort.
& $VenvPy -c 'import mu2edaq_discovery' 2>$null
if ($LASTEXITCODE -ne 0) {
    $sibling = Join-Path $Here '..\mu2edaq-discovery'
    if (Test-Path $sibling) {
        & $VenvPy -m pip install -e $sibling
        if ($LASTEXITCODE -eq 0) { Write-Host 'Installed mu2edaq-discovery from sibling checkout' }
    } else {
        & $VenvPy -m pip install 'git+https://github.com/Mu2e/mu2edaq-discovery' 2>$null
        if ($LASTEXITCODE -eq 0) { Write-Host 'Installed mu2edaq-discovery from GitHub' }
        else { Write-Host 'note: mu2edaq-discovery not installed; auto-discovery disabled' }
    }
}

if ($Dev) {
    Write-Host 'Installing mu2edaq-bigredbox (editable) with dev extras'
    & $VenvPy -m pip install -e "$Here[dev]"
} else {
    Write-Host 'Installing mu2edaq-bigredbox (editable)'
    & $VenvPy -m pip install -e $Here
}

Write-Host ''
Write-Host 'Bootstrap complete.'
Write-Host '  Start the alert daemon with:  .\start-mu2edaq-bigredbox.ps1'
Write-Host '  Send a test alert with:       venv\Scripts\mu2edaq-bigredbox-send.exe'
