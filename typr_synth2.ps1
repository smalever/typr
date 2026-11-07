$f = "D:\@home\sma\programming\typr\scripts\windows\TyprInstaller.ps1"
$code = Get-Content $f -Raw -ErrorAction Stop
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseInput($code, [ref]$null, [ref]$errors)
"errors count: $($errors.Count)"
foreach ($e in $errors) {
    "Type: $($e.GetType().Name)"
    "Message: $($e.ToString())"
    "Extent: $($e.Extent.Text)"
    "StartOffset: $($e.Extent.StartOffset), EndOffset: $($e.Extent.EndOffset)"
    "StartLineNumber: $($e.Extent.StartLineNumber)"
}
