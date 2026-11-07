$Bytes = [System.IO.File]::ReadAllBytes('D:\@home\sma\programming\typr\scripts\windows\TyprInstaller.ps1')
$Text = [System.Text.Encoding]::UTF8.GetString($Bytes)
$Line367 = ($Text -split '\r?\n')[366]
Write-Host ('len=' + $Line367.Length)
$NonAscii = @()
for ($i = 0; $i -lt $Line367.Length; $i++) {
    $cp = [int][char]$Line367[$i]
    if ($cp -gt 127) {
        $NonAscii += ("char {0} U+{1:X4}" -f $i, $cp)
    }
}
if ($NonAscii.Count -eq 0) { Write-Host 'all ASCII' } else { $NonAscii }
Write-Host '---'
Write-Host $Line367
