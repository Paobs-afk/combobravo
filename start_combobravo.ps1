$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Join-Path $projectRoot "backend"
$frontendDir = Join-Path $projectRoot "frontend"

Write-Host "=== ComboBravo Launcher ===" -ForegroundColor Red

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  throw "Python is not installed or not in PATH."
}

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
  throw "Node.js/npm is not installed or not in PATH."
}

Write-Host "[1/5] Checking backend dependencies..." -ForegroundColor Yellow
$backendDepsReady = $false
try {
  Push-Location $backendDir
  python -c "import fastapi, pandas, mlxtend, scipy, numpy, multipart, supabase, dotenv" | Out-Null
  $backendDepsReady = $true
} catch {
  $backendDepsReady = $false
} finally {
  Pop-Location
}

if (-not $backendDepsReady) {
  Write-Host "Installing backend requirements..." -ForegroundColor Yellow
  Push-Location $backendDir
  python -m pip install -r requirements.txt
  Pop-Location
}

Write-Host "[2/5] Checking frontend dependencies..." -ForegroundColor Yellow
if (-not (Test-Path (Join-Path $frontendDir "node_modules"))) {
  Write-Host "Installing frontend packages..." -ForegroundColor Yellow
  Push-Location $frontendDir
  npm install
  Pop-Location
}

Write-Host "[3/5] Generating latest iteration outputs..." -ForegroundColor Yellow
Push-Location $backendDir
try {
  python -c "from mba_engine import run_all_datasets; run_all_datasets(3)"
} catch {
  Write-Host "Training skipped. Import or upload your datasets to Supabase first." -ForegroundColor DarkYellow
}
Pop-Location

Write-Host "[4/5] Launching backend..." -ForegroundColor Yellow
$backendCmd = "cd `"$backendDir`"; python main.py"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendCmd | Out-Null

Write-Host "[5/5] Launching frontend..." -ForegroundColor Yellow
$frontendCmd = "cd `"$frontendDir`"; npm run dev"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontendCmd | Out-Null

Start-Sleep -Seconds 3
Start-Process "http://localhost:5173" | Out-Null

Write-Host "ComboBravo is starting." -ForegroundColor Green
Write-Host "Frontend: http://localhost:5173" -ForegroundColor Cyan
Write-Host "Backend:  http://127.0.0.1:8000" -ForegroundColor Cyan
