$root = 'D:\@home\sma\programming\typr'
$files = @('scripts\windows\TyprInstaller.ps1')
foreach ($f in $files) {
    $s = [System.IO.File]::ReadAllText($root + '\\' + $f, [System.Text.UTF8Encoding]::new($false))
    $hits = @()
    $inStr = $false; $strChar = ''
    for ($i = 0; $i -lt $s.Length - 1; $i++) {
        $c = $s[$i]
        if ($c -eq '\'' -or $c -eq '"') {
            if (-not $inStr) { $inStr = $true; $strChar = $c }
            elseif ($c -eq $strChar) { $inStr = $false }
        }
        elseif ($inStr -and $c -eq '\' -and $i + 1 -lt $s.Length) {
            $n = $s[$i + 1]
            if ($n -in 'r','n','t','0') {
                # найти номер строки
                $ln = ($s.Substring(0,$i) -split '\r?\n').Length
                $hits += "line $ln : $($s.Substring([Math]::Max(0,$i-40),80) | ForEach-Object { if ($_ -in 'A'..'Z','a'..'z','0'..'9') { $_ } else { '[' + [int][char]$_ + ']' } })"
            }
        }
    }
    Write-Host "=== $f"; if ($hits) { $hits } else { 'no escaped chars' }
}
