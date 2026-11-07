$Bytes = [System.IO.File]::ReadAllBytes('D:\@home\sma\programming\typr\scripts\windows\TyprInstaller.ps1')
$Text = [System.Text.Encoding]::UTF8.GetString($Bytes)
$Idx = $Text.IndexOf('Foreign')
Write-Host 'Foreign index=' $Idx
Write-Host ('context: ' + $Text.Substring([Math]::Max(0,$Idx-100), 200))
Write-Host '---hex of chars around Foreign---'
$Hex = @()
for ($i = $Idx - 60; $i -lt $Idx + 60; $i++) {
    if ($i -ge 0 -and $i -lt $Text.Length) {
        $Hex += ("{0:X2}" -f $Bytes[$i])
    }
}
Write-Host ($Hex -join ' ')
$Non = @()
for ($i = $Idx - 60; $i -lt $Idx + 60; $i++) {
    if ($i -ge 0 -and $i -lt $Text.Length -and $Bytes[$i] -gt 127) {
        $Non += ("pos" + ($i - $Idx + 1)); Write-Host 'non-ascii at offset' ($i-$Idx) $Bytes[$i]
    }
}
Write-Host 'non-ascii count:' $Non.Count
