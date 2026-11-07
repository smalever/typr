$Errors = $null
$null = [System.Management.Automation.Language.Parser]::ParseFile('D:\@home\sma\programming\typr\scripts\windows\TyprInstaller.ps1', [ref]$null, [ref]$Errors)
Write-Host 'TyprInstaller.ps1 ParseFile errors: ' $Errors.Count
if ($Errors.Count -gt 0) {
    $Errors | ForEach-Object { Write-Host ("Line " + $_.StartLineNumber + ": " + $_.Message) }
} else {
    Write-Host 'TYPRINSTALLER PARSED OK'
}
$Error2 = $null
$null = [System.Management.Automation.Language.Parser]::ParseFile('D:\@home\sma\programming\typr\scripts\windows\Install.ps1', [ref]$null, [ref]$Error2)
Write-Host 'Install.ps1 ParseFile errors: ' $Error2.Count
if ($Error2.Count -gt 0) {
    $Error2 | ForEach-Object { Write-Host ("Line " + $_.StartLineNumber + ": " + $_.Message) }
} else {
    Write-Host 'INSTALL PARSED OK'
}
# show bytes of line 350 correctly
$Text = [System.Text.Encoding]::UTF8.GetString([System.IO.File]::ReadAllBytes('D:\@home\sma\programming\typr\scripts\windows\TyprInstaller.ps1'))
$Lines = $Text -split '\r?\n'
$Line350 = $Lines[349]
Write-Host 'Line350 text: ' $Line350
# find start offset of line 350 in the text
$StartOffset = 0
for ($i = 0; $i -lt 349; $i++) { $StartOffset += $Lines[$i].Length + 2 }
$Bytes350 = [System.Text.Encoding]::UTF8.GetBytes($Line350)
$FileBytes = [System.IO.File]::ReadAllBytes('D:\@home\sma\programming\typr\scripts\windows\TyprInstaller.ps1')
$Hex = @()
for ($j = 0; $j -lt $Bytes350.Length; $j++) {
    $Hex += ("{0}:{1:X2}:{2}" -f $j, $FileBytes[$StartOffset + $j], $Line350[$j])
}
Write-Host 'Line350 hex:'
Write-Host ($Hex -join ' ')
