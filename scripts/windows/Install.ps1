[CmdletBinding()]
param([switch]$Check, [switch]$Uninstall, [switch]$RemoveModels,
    [ValidateSet('Ask','Parakeet','GigaSTT','Both','Skip')][string]$STT = 'Ask')
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\TyprInstaller.ps1"
try {
    Invoke-TyprInstaller -Payload $PSScriptRoot -Check:$Check -Uninstall:$Uninstall -RemoveModels:$RemoveModels -STT $STT
    exit 0
} catch {
    Write-Error $_ -ErrorAction Continue
    exit 1
}
