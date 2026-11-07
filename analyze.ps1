$Path = 'scripts\windows\TyprInstaller.ps1'
$bytes = [System.IO.File]::ReadAllBytes($Path)
Write-Host ("FileBytes=" $bytes.Length)
$text = [System.Text.Encoding]::UTF8.GetString($bytes)
Write-Host ("TextLength=" $text.Length)

$codepoints = @{}
for ($i = 0; $i -lt $text.Length; $i++) {
    $c = $text[$i]
    $cp = [int][char]$c
    if ($cp -gt 127) {
        $key = "U+$('{0:X4}' -f $cp)"
        $codepoints[$key] = ($codepoints[$key] ?? 0) + 1
    }
}
if ($codepoints.Count -eq 0) {
    Write-Host 'All ASCII'
} else {
    $codepoints | Format-Table Key, Value
}

# Show bytes around 'Installation declined'
$idx = [System.String]::IndexOf($text, 'Installation declined')
Write-Host ("Index=" $idx)
$start = [Math]::Max(0, $idx - 400)
$chunk = $text.Substring($start, [Math]::Min(400, $text.Length - $start))
for ($i = 0; $i -lt $chunk.Length; $i++) {
    $cp = [int][char]$chunk[$i]
    if ($cp -gt 127) {
        Write-Host ("pos=$($start+$i) U+$('{0:X4}' -f $cp)")
    }
}
