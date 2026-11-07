$Path = 'D:\@home\sma\programming\typr\scripts\windows\TyprInstaller.ps1'
$Text = [System.IO.File]::ReadAllText($Path, [System.Text.UTF8Encoding]::new($false))
$Old = '"$Root\r'
$New = '"$Root\\r'
$Count = ($Text -split [regex]::Escape($Old)).Count - 1
Write-Host 'matches=' $Count
if ($Count -gt 0) {
    $NewText = $Text.Replace($Old, $New)
    [System.IO.File]::WriteAllText($Path, $NewText, [System.Text.UTF8Encoding]::new($false))
    Write-Host 'fixed'
    # verify
    $V = [System.IO.File]::ReadAllBytes($Path)
    $Ver = [System.Text.Encoding]::UTF8.GetString($V)
    Write-Host 'verify ' ($Ver.IndexOf('"$Root\r')) ' and ' ($Ver.IndexOf('"$Root\\r'))
}
