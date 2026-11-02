param([string]$CondaPython)
$ErrorActionPreference = 'Stop'

function Resolve-CondaPython {
    param([string]$ExplicitPath)

    if ($ExplicitPath) {
        if (-not (Test-Path -LiteralPath $ExplicitPath -PathType Leaf)) {
            throw 'The -CondaPython file does not exist. Specify the Python executable from your Conda installation.'
        }
        return (Resolve-Path -LiteralPath $ExplicitPath).Path
    }

    $Candidates = @()
    if ($env:CONDA_PYTHON_EXE) { $Candidates += $env:CONDA_PYTHON_EXE }
    $CondaExecutables = @($env:CONDA_EXE)
    $CondaExecutables += @(Get-Command -Name conda.exe,conda.bat -CommandType Application -ErrorAction SilentlyContinue | ForEach-Object { $_.Source })
    foreach ($CondaExecutable in $CondaExecutables) {
        if (-not $CondaExecutable) { continue }
        $CondaDirectory = Split-Path -Path $CondaExecutable -Parent
        $Candidates += Join-Path $CondaDirectory 'python.exe'
        $Candidates += Join-Path (Split-Path -Path $CondaDirectory -Parent) 'python.exe'
    }
    foreach ($InstallRoot in @($env:USERPROFILE,$env:LOCALAPPDATA,$env:ProgramData)) {
        if (-not $InstallRoot) { continue }
        foreach ($InstallName in @('miniconda3','anaconda3')) {
            $Candidates += Join-Path (Join-Path $InstallRoot $InstallName) 'python.exe'
        }
    }
    foreach ($Candidate in ($Candidates | Select-Object -Unique)) {
        if (Test-Path -LiteralPath $Candidate -PathType Leaf) {
            return (Resolve-Path -LiteralPath $Candidate).Path
        }
    }
    throw 'Conda was not found. Install Anaconda or Miniconda, or pass -CondaPython with the Python executable from an existing Conda installation.'
}

$CondaPython = Resolve-CondaPython -ExplicitPath $CondaPython
& $CondaPython -m conda --version
if ($LASTEXITCODE -ne 0) {
    throw 'The selected Python cannot run Conda. Pass -CondaPython with the Python executable from your base Conda installation.'
}
$ProjectRoot = Split-Path $PSScriptRoot -Parent
$env:CONDA_NO_PLUGINS = $null
$env:CONDA_PKGS_DIRS = Join-Path $ProjectRoot '.conda-pkgs'
$env:CONDA_ENVS_PATH = Join-Path $ProjectRoot '.envs'
$LockFile = Join-Path $ProjectRoot 'environment-win-64.lock'
if (Test-Path -LiteralPath $LockFile) {
    & $CondaPython -m conda create --prefix (Join-Path $ProjectRoot '.envs\video-tech') --file $LockFile --yes
} else {
    & $CondaPython -m conda env create --prefix (Join-Path $ProjectRoot '.envs\video-tech') --file (Join-Path $ProjectRoot 'environment.yml') --solver libmamba
}
if ($LASTEXITCODE -ne 0) { throw 'Environment creation failed' }
