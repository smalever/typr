$lines = Get-Content -Path "D:\@home\sma\programming\typr\scripts\windows\TyprInstaller.ps1" -Encoding UTF8
$idx = 349
$line = $lines[$idx]
Write-Output ("Line " + ($idx+1) + " len " + $line.Length + ":")
for ($j = 0; $j -lt $line.Length; $j++) {
    $c = [int]$line[$j]
    if ($c -eq 96) { Write-Output ("pos " + ${j} + ": BACKTICK") }
    elseif ($c -eq 92) { Write-Output ("pos " + ${j} + ": BACKSLASH") }
}
