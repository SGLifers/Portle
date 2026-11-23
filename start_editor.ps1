$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    $portlePython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $portlePython)) {
        throw 'Create the environment first: python -m venv .venv'
    }
    & $portlePython -m portle editor --port 8742
    if ($LASTEXITCODE -ne 0) { throw "Portle exited with code $LASTEXITCODE" }
} finally {
    Pop-Location
}
