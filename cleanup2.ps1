$files = Get-ChildItem "D:\@home\sma\programming\typr" -File -ErrorAction SilentlyContinue | Where-Object {
    $_.Name -match '^(check_|test_|run_|bytes_|balance_|nonascii_|debug_|git_|cleanup_)'
}
Write-Output "Files to remove: $($files.Count)"
foreach ($f in $files) {
    try {
        Remove-Item -LiteralPath $f.FullName -Force -ErrorAction Stop
        Write-Output "REMOVED $($f.Name)"
    } catch {
        Write-Output "FAILED $($f.Name): $($_.Exception.Message)"
    }
}
