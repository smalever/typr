$Path = 'D:\@home\sma\programming\typr\scripts\windows\TyprInstaller.ps1'
$Bytes = [System.IO.File]::ReadAllBytes($Path)
$Text = [System.Text.Encoding]::UTF8.GetString($Bytes)
$Idx = $Text.IndexOf('\runtime\pythonw.exe')
Write-Host 'index=' $Idx
$Start = [Math]::Max(0, $Idx - 15)
for ($i = $Start; $i -lt $Idx + 18; $i++) {
    Write-Host (('byte {0} hex {1:X2} char {2}' -f $i, $Bytes[$i], $Text[$i]))
}
