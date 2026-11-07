$null = [System.Management.Automation.Language.Parser]::ParseFile('scripts\windows\TyprInstaller.ps1', [ref]$null, [ref]$errors)
if ($errors) {
    $errors | ForEach-Object { Write-Host ("ERR line {0}: {1}" -f $_.StartLineNumber, $_.Message) }
} else {
    Write-Host 'PARSED OK'
}
