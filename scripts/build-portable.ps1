param([switch]$NoPause)
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path $PSScriptRoot -Parent
$Runtime = Join-Path $ProjectRoot '.envs\video-tech'
$env:PATH = "$Runtime;$Runtime\Library\bin;$Runtime\Scripts;$env:PATH"
$env:CONDA_PREFIX = $Runtime
Push-Location $ProjectRoot
try {
    & "$Runtime\python.exe" scripts/build-icon.py
    if ($LASTEXITCODE -ne 0) { throw 'App icon generation failed.' }
    & "$Runtime\python.exe" -m PyInstaller --noconfirm --distpath artifacts/portable --workpath artifacts/pyinstaller scripts/Splicelet.spec
    if ($LASTEXITCODE -ne 0) { throw 'Portable build failed.' }
} finally { Pop-Location }
