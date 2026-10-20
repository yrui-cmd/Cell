#requires -Version 5.1
[CmdletBinding()]
param(
    [switch]$Relaunch,
    [string]$EntryScript,
    [string]$ParametersFile
)

function Invoke-CellSu8UpdateGate {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$EntryScript,
        [Parameter(Mandatory = $true)][System.Collections.IDictionary]$BoundParameters
    )
    $ErrorActionPreference = 'Stop'
    $updaterPath = Join-Path $PSScriptRoot 'auto_update.py'
    if (-not (Test-Path -LiteralPath $updaterPath -PathType Leaf)) {
        throw 'The required Skill updater is missing; processing stopped before authentication or upload.'
    }
    $pythonCommand = Get-Command py -ErrorAction SilentlyContinue
    $pythonPrefix = @('-3', '-X', 'utf8', '-B')
    if (-not $pythonCommand) {
        $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
        $pythonPrefix = @('-X', 'utf8', '-B')
    }
    if (-not $pythonCommand) { throw 'Python is required for the Skill update check; processing stopped.' }
    try {
        $raw = & $pythonCommand.Source @pythonPrefix $updaterPath
        $updateExit = $LASTEXITCODE
        $jsonText = $raw -join [Environment]::NewLine
        if ($jsonText.Length -gt 1048576 -or -not $jsonText.TrimStart().StartsWith('{')) {
            throw 'Invalid updater output.'
        }
        $update = $jsonText | ConvertFrom-Json
    }
    catch { throw 'The Skill update check failed; processing stopped before authentication or upload.' }
    if ($updateExit -ne 0 -or $update.status -isnot [string] -or $update.status -notin @('up_to_date', 'updated')) {
        throw 'The latest Skill version could not be confirmed; processing stopped before authentication or upload.'
    }
    if ($update.status -eq 'up_to_date') { return $null }
    $restartCount = 0
    if ($env:CELL_SU8_UPDATE_RESTARTS) {
        if (-not [int]::TryParse($env:CELL_SU8_UPDATE_RESTARTS, [ref]$restartCount)) {
            throw 'Invalid Skill restart state; processing stopped without uploading.'
        }
    }
    if ($restartCount -lt 0 -or $restartCount -ge 2) {
        throw 'The Skill changed repeatedly during this workflow; processing stopped without uploading.'
    }
    $records = @()
    foreach ($name in $BoundParameters.Keys) {
        $value = $BoundParameters[$name]
        if ($value -is [System.Management.Automation.SwitchParameter]) {
            $records += @{ name = [string]$name; kind = 'switch'; value = [bool]$value }
        }
        elseif ($null -eq $value -or $value -is [string] -or $value -is [uri] -or $value -is [enum] -or
                $value -is [int] -or $value -is [long] -or $value -is [double] -or $value -is [bool]) {
            if ($value -is [uri]) { $value = $value.OriginalString }
            if ($value -is [enum]) { $value = [string]$value }
            $records += @{ name = [string]$name; kind = 'value'; value = $value }
        }
        else { throw 'An unsupported argument type prevented a safe Skill restart.' }
    }
    $parameterPath = [IO.Path]::GetTempFileName()
    $savedCount = $env:CELL_SU8_UPDATE_RESTARTS
    try {
        $payload = ConvertTo-Json -InputObject @($records) -Depth 5 -Compress
        [IO.File]::WriteAllText($parameterPath, $payload, (New-Object Text.UTF8Encoding($true)))
        $env:CELL_SU8_UPDATE_RESTARTS = [string]($restartCount + 1)
        $hostName = if ($PSVersionTable.PSEdition -eq 'Core') { 'pwsh.exe' } else { 'powershell.exe' }
        $hostPath = Join-Path $PSHOME $hostName
        & $hostPath -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'update_gate.ps1') `
            -Relaunch -EntryScript $EntryScript -ParametersFile $parameterPath |
            ForEach-Object { [Console]::Out.WriteLine([string]$_) }
        return [int]$LASTEXITCODE
    }
    finally {
        if ($null -eq $savedCount) { Remove-Item Env:CELL_SU8_UPDATE_RESTARTS -ErrorAction SilentlyContinue }
        else { $env:CELL_SU8_UPDATE_RESTARTS = $savedCount }
        if (Test-Path -LiteralPath $parameterPath -PathType Leaf) {
            Remove-Item -LiteralPath $parameterPath -Force
        }
    }
}

if ($Relaunch) {
    $ErrorActionPreference = 'Stop'
    try {
        $records = Get-Content -LiteralPath $ParametersFile -Encoding UTF8 -Raw | ConvertFrom-Json
        $forwarded = @{}
        foreach ($record in $records) {
            if ($record.kind -eq 'switch') {
                $forwarded[$record.name] = [System.Management.Automation.SwitchParameter]([bool]$record.value)
            }
            else { $forwarded[$record.name] = $record.value }
        }
        & $EntryScript @forwarded
        $entrySucceeded = $?
        if ($null -ne $LASTEXITCODE -and $LASTEXITCODE -ne 0) { exit [int]$LASTEXITCODE }
        if (-not $entrySucceeded) { exit 1 }
        exit 0
    }
    catch {
        Write-Error 'The updated Skill could not continue; processing stopped.'
        exit 1
    }
}
