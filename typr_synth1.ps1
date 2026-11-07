$f = "D:\@home\sma\programming\typr\scripts\windows\TyprInstaller.ps1"
$code = Get-Content $f -Raw -ErrorAction Stop
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseInput($code, [ref]$null, [ref]$errors)
Write-Output "errors count: $("$errors".Count)"
if ($errors) { "ERROR ${f}:"; $errors | ForEach-Object { Write-Output $_ } }
else { "OK ${f}" }
