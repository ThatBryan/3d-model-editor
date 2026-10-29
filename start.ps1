<#
.SYNOPSIS
Start the 3D model editor: the API server (port 8787) and the web app (http://localhost:5173).

.DESCRIPTION
Checks the prerequisites, starts the server, waits until it answers, reports what it found
(Blender, MPFB2, the Claude login, Unreal), then runs the web app in this window and opens the
browser. Ctrl+C stops both. Setup is described in AGENTS.md, section "Windows".

.EXAMPLE
.\start.ps1              # server + web app
.\start.ps1 -Mock        # web app only, on canned data (no server, Blender or AI)
.\start.ps1 -NoBrowser   # do not open the browser
#>
param([switch]$Mock, [switch]$NoBrowser)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$web = Join-Path $root 'web'
$python = Join-Path $root 'server\.venv\Scripts\python.exe'
$vite = Join-Path $web 'node_modules\vite\bin\vite.js'
$server = $null

function Test-Port([int]$port) {
    [bool](Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
}

try {
    # Node: Vite 7 needs 20.19 or newer.
    if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
        throw 'Node.js not found. Install Node 22: nvm install 22.23.4; nvm use 22.23.4'
    }
    $nodeVersion = [version](node --version).TrimStart('v')
    if ($nodeVersion -lt [version]'20.19') {
        throw "Node $nodeVersion is too old for this app. Switch to Node 22: nvm use 22.23.4"
    }
    if (-not (Test-Path $vite)) {
        Write-Host 'Installing web dependencies (npm ci)...'
        Push-Location $web
        try { npm ci --no-audit --no-fund } finally { Pop-Location }
        if ($LASTEXITCODE) { throw 'npm ci failed; see the messages above.' }
    }
    if (Test-Port 5173) { throw 'Port 5173 is already in use. Is the editor already running?' }

    if (-not $Mock) {
        if (-not (Test-Path $python)) {
            throw ('server\.venv not found. Create it: py -3.11 -m venv server\.venv; ' +
                   'server\.venv\Scripts\python -m pip install -r server\requirements.txt')
        }
        if (Test-Port 8787) { throw 'Port 8787 is already in use. Is the editor already running?' }

        Write-Host 'Starting the API server on http://127.0.0.1:8787 ...'
        $server = Start-Process -FilePath $python -WorkingDirectory $root -NoNewWindow -PassThru `
            -ArgumentList '-m', 'uvicorn', 'app.main:app', '--port', '8787', '--app-dir', 'server'

        $health = $null
        $deadline = (Get-Date).AddSeconds(30)
        while (-not $health) {
            if ($server.HasExited) { throw "The API server stopped (exit code $($server.ExitCode)); see the messages above." }
            if ((Get-Date) -gt $deadline) { throw 'The API server did not answer within 30 seconds.' }
            try { $health = Invoke-RestMethod 'http://127.0.0.1:8787/api/health' -TimeoutSec 2 }
            catch { Start-Sleep -Milliseconds 500 }
        }
        $checks = [ordered]@{
            blender = 'Blender 5.2 (builds ships and crew)'
            mpfb    = 'MPFB2 (crew bodies)'
            ai      = 'Claude Code login (the AI)'
            unreal  = 'Unreal 5.8 (optional: import test, macOS only)'
        }
        foreach ($key in $checks.Keys) {
            if ($health.$key) { Write-Host "  [ok]      $($checks[$key])" -ForegroundColor Green }
            else { Write-Host "  [missing] $($checks[$key])" -ForegroundColor Yellow }
        }
    }

    $viteArgs = @($vite)
    if ($Mock) { $viteArgs += '--mode', 'mock' }
    if (-not $NoBrowser) { $viteArgs += '--open' }
    Write-Host 'Starting the web app on http://localhost:5173 (Ctrl+C stops everything) ...'
    Push-Location $web
    try { node @viteArgs } finally { Pop-Location }
}
catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
finally {
    if ($server -and -not $server.HasExited) {
        Stop-Process -Id $server.Id -Force
        Write-Host 'API server stopped.'
    }
}
