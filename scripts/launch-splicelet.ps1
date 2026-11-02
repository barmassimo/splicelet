param([string]$Source, [switch]$Muted, [switch]$SmokeTest)
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path $PSScriptRoot -Parent
$Runtime = Join-Path $ProjectRoot '.envs\video-tech'
$env:PATH = "$Runtime;$Runtime\Library\bin;$Runtime\Scripts;$env:PATH"
$env:CONDA_PREFIX = $Runtime
if ($SmokeTest -and -not $Source) {
    $FixtureOutput = @(& "$Runtime\python.exe" (Join-Path $PSScriptRoot 'test_fixture.py'))
    if ($LASTEXITCODE -ne 0) { throw 'Synthetic smoke fixture generation failed.' }
    $Source = $FixtureOutput[-1]
    $FixtureOutput | Select-Object -SkipLast 1 | Write-Output
}
$Arguments = @('-m', 'splicelet')
if ($Source) { $Arguments += (Resolve-Path -LiteralPath $Source).Path }
if ($Muted) { $Arguments += '--muted' }
if ($SmokeTest) { $Arguments += '--smoke-test' }
Push-Location $ProjectRoot
try { & "$Runtime\python.exe" @Arguments; $Result = $LASTEXITCODE }
finally { Pop-Location }
exit $Result
