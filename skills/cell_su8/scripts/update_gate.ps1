#requires -Version 5.1
# Compatibility hook. Updates are manual via auto_update.py.
function Invoke-CellSu8UpdateGate {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$EntryScript,
        [Parameter(Mandatory = $true)][System.Collections.IDictionary]$BoundParameters
    )
    # Continue with the installed version; no network check or restart.
    return $null
}
