# Athena Voice Studio — Windows setup
# Run from PowerShell: powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

function Require-Command([string]$Command, [string]$Hint) {
    if (-not (Get-Command $Command -ErrorAction SilentlyContinue)) {
        Write-Host "[Missing] $Command. $Hint" -ForegroundColor Yellow
        return $false
    }
    return $true
}

if (-not (Require-Command "py" "Install Python 3.12 from https://www.python.org/downloads/windows/ and enable the Python launcher.")) {
    exit 1
}

if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Host "Installing FFmpeg with winget..." -ForegroundColor Cyan
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install --id Gyan.FFmpeg.Shared --exact --accept-source-agreements --accept-package-agreements
    } else {
        Write-Host "FFmpeg is required. Install it manually, add it to PATH, then rerun this script." -ForegroundColor Yellow
        exit 1
    }
}

if (-not (Test-Path ".venv")) {
    Write-Host "Creating a Python 3.12 virtual environment..." -ForegroundColor Cyan
    $python312 = $null
    try { $python312 = (& py -3.12 -c "import sys; print(sys.executable)" 2>$null | Select-Object -Last 1) } catch {}
    if (-not $python312 -and (Test-Path "$env:USERPROFILE\anaconda3\python.exe")) {
        $candidate = "$env:USERPROFILE\anaconda3\python.exe"
        $version = & $candidate -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
        if ($version -eq "3.12") { $python312 = $candidate }
    }
    if (-not $python312) {
        Write-Host "Python 3.12 was not found. Install it, then rerun setup." -ForegroundColor Yellow
        exit 1
    }
    & $python312 -m venv .venv
}

$python = Join-Path $root ".venv\Scripts\python.exe"
& $python -m pip install --upgrade pip wheel setuptools

$nvidiaSmi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
$cudaReady = $false
if ($nvidiaSmi) {
    $gpuQuery = & $nvidiaSmi.Source --query-gpu=name,driver_version,compute_cap --format=csv,noheader 2>$null
    $cudaReady = $LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace(($gpuQuery -join ""))
}
if ($cudaReady) {
    Write-Host "Compatible NVIDIA driver detected: $gpuQuery" -ForegroundColor Green
    Write-Host "Installing the tested CUDA 12.8 PyTorch build..." -ForegroundColor Green
    & $python -m pip install --upgrade torch torchaudio --index-url https://download.pytorch.org/whl/cu128
} else {
    Write-Host "No usable NVIDIA CUDA runtime detected. Installing official CPU PyTorch..." -ForegroundColor Yellow
    & $python -m pip install --upgrade torch torchaudio --index-url https://download.pytorch.org/whl/cpu
}

Write-Host "Installing Athena Voice Studio backend packages..." -ForegroundColor Cyan
& $python -m pip install --upgrade -r backend\requirements.txt

if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
    Write-Host "npm is required. Install Node.js 20 or newer, then rerun setup." -ForegroundColor Yellow
    exit 1
}

Write-Host "Installing frontend packages..." -ForegroundColor Cyan
Push-Location frontend
npm.cmd install
Pop-Location

Copy-Item -Path ".env.example" -Destination ".env" -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "Setup complete. Run start.bat to launch Athena Voice Studio." -ForegroundColor Green
Write-Host "The first real synthesis downloads the selected Qwen3-TTS model into the local Hugging Face cache." -ForegroundColor DarkGray
