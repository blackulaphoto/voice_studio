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
    py -3.12 -m venv .venv
}

$python = Join-Path $root ".venv\Scripts\python.exe"
& $python -m pip install --upgrade pip wheel setuptools

$hasNvidia = $null -ne (Get-Command nvidia-smi -ErrorAction SilentlyContinue)
if ($hasNvidia) {
    Write-Host "NVIDIA GPU detected. Installing CUDA 12.8 PyTorch wheels..." -ForegroundColor Green
    & $python -m pip install --upgrade torch torchaudio --index-url https://download.pytorch.org/whl/cu128
} else {
    Write-Host "No NVIDIA CUDA runtime detected. Installing CPU PyTorch (synthesis will be slower)..." -ForegroundColor Yellow
    & $python -m pip install --upgrade torch torchaudio --index-url https://download.pytorch.org/whl/cpu
}

Write-Host "Installing Athena Voice Studio backend packages..." -ForegroundColor Cyan
& $python -m pip install --upgrade -r backend\requirements.txt

if (-not (Get-Command pnpm -ErrorAction SilentlyContinue)) {
    Write-Host "Installing pnpm through Corepack..." -ForegroundColor Cyan
    corepack enable
    corepack prepare pnpm@latest --activate
}

Write-Host "Installing frontend packages..." -ForegroundColor Cyan
Push-Location frontend
pnpm install
Pop-Location

Copy-Item -Path ".env.example" -Destination ".env" -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "Setup complete. Run start.bat to launch Athena Voice Studio." -ForegroundColor Green
Write-Host "The first real synthesis downloads the selected Qwen3-TTS model into the local Hugging Face cache." -ForegroundColor DarkGray
