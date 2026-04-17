Param(
  [string]$ProjectRoot = "C:\Users\maksi\projects\vizard-arctic"
)

$ErrorActionPreference = "Stop"

Write-Host "[1/6] Entering project root: $ProjectRoot"
Set-Location $ProjectRoot

Write-Host "[2/6] Python venv setup"
if (!(Test-Path ".venv")) {
  py -3.11 -m venv .venv
}

& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\pip.exe" install -r .\backend\requirements.txt

Write-Host "[3/6] Install ML deps (PyTorch)"
try {
  & ".\.venv\Scripts\pip.exe" install torch torchvision --index-url https://download.pytorch.org/whl/cu121
} catch {
  Write-Host "CUDA wheel install failed, fallback to default PyPI torch package"
  & ".\.venv\Scripts\pip.exe" install torch torchvision
}

Write-Host "[4/6] Frontend deps"
Set-Location "$ProjectRoot\frontend"
npm install

Write-Host "[5/6] Ensure storage dirs"
Set-Location $ProjectRoot
New-Item -ItemType Directory -Path ".\storage\layers" -Force | Out-Null
New-Item -ItemType Directory -Path ".\backend\checkpoints" -Force | Out-Null

Write-Host "[6/6] Done."
Write-Host "Run backend:"
Write-Host "  cd $ProjectRoot\backend"
Write-Host "  ..\.venv\Scripts\python.exe run.py"
Write-Host "Run frontend:"
Write-Host "  cd $ProjectRoot\frontend"
Write-Host "  npm run dev -- --host 0.0.0.0 --port 8080"
