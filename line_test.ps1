$Text = [System.IO.File]::ReadAllText('D:\@home\sma\programming\typr\scripts\windows\TyprInstaller.ps1', [System.Text.UTF8Encoding]::new($false))
$Lines = $Text -split '\r?\n'
for ($ln = 1; $ln -le $Lines.Length; $ln++) {
    $L = $Lines[$ln-1]
    $Err = $null
    $null = [System.Management.Automation.Language.Parser]::ParseInput($L, [ref]$null, [ref]$Err)
    if ($Err.Count -gt 0) {
        Write-Host ("LINE {0}: {1} : {2}" -f $ln, $L.Substring(0,[Math]::Min(60,$L.Length)), $Err[0].Message)
    }
}
Write-Host 'done'
