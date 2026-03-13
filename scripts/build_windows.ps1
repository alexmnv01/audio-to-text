Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

Write-Host "Building AudioToText for Windows with PyInstaller..."

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    throw "Virtual environment not found. Create it first: python -m venv .venv"
}

$Python = Resolve-Path ".venv\Scripts\python.exe"

& $Python -m pip install --upgrade pip
& $Python -m pip install -r requirements.txt

if (Test-Path "build") {
    Remove-Item "build" -Recurse -Force
}
if (Test-Path "dist") {
    Remove-Item "dist" -Recurse -Force
}

& $Python -m PyInstaller --clean --noconfirm audio_to_text.spec

Write-Host ""
Write-Host "Build completed."
Write-Host "Executable folder: $ProjectRoot\dist\AudioToText"
Write-Host "Main executable: $ProjectRoot\dist\AudioToText\AudioToText.exe"
Write-Host ""
Write-Host "Important:"
Write-Host "- ffmpeg must still be installed and available in PATH on the target machine."
Write-Host "- The first transcription run may take longer because the Whisper small model must initialize."
