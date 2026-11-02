[CmdletBinding()]
param([switch]$Portable)
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path $PSScriptRoot -Parent
$Runtime = Join-Path $ProjectRoot '.envs\video-tech'
$env:PATH = "$Runtime;$Runtime\Library\bin;$Runtime\Scripts;$env:PATH"
$env:CONDA_PREFIX = $Runtime
$Arguments = @((Join-Path $PSScriptRoot 'run_tests.py'))
if ($Portable) { $Arguments += '--portable' }
Push-Location $ProjectRoot
try { & "$Runtime\python.exe" @Arguments; $Result = $LASTEXITCODE }
finally { Pop-Location }
exit $Result
