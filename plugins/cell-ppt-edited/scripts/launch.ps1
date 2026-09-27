$ErrorActionPreference = 'Stop'
$binaryPath = Join-Path $PSScriptRoot '..\bin\cell-ppt-edited.exe'
if (-not (Test-Path -LiteralPath $binaryPath -PathType Leaf)) {
    [Console]::Error.WriteLine('Portable runtime missing. Download the Windows release ZIP and run Install.cmd, or build it from source first.')
    exit 1
}
& $binaryPath
exit $LASTEXITCODE
