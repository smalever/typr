$Errors = $null
$null = [System.Management.Automation.Language.Parser]::ParseFile('D:\@home\sma\programming\typr\scripts\windows\TyprInstaller.ps1', [ref]$null, [ref]$Errors)
if ($Errors.Count -gt 0) {
    $Errors | ForEach-Object { Write-Host ("Line {0}: {1}" -f $_.StartLineNumber, $_.Message) }
} else {
    Write-Host 'TYPRINSTALLER.PS1 PARSED OK'
}
$Error2 = $null
$null = [System.Management.Automation.Language.Parser]::ParseFile('D:\@home\sma\programming\typr\scripts\windows\Install.ps1', [ref]$null, [ref]$Error2)
if ($Error2.Count -gt 0) {
    $Error2 | ForEach-Object { Write-Host ("Install.ps1 Line {0}: {1}" -f $_.StartLineNumber, $_.Message) }
} else {
    Write-Host 'INSTALL.PS1 PARSED OK'
}
