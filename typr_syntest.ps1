$files = @(
    "D:\@home\sma\programming\typr\scripts\windows\TyprInstaller.ps1",
    "D:\@home\sma\programming\typr\scripts\windows\Build-Payload.ps1",
    "D:\@home\sma\programming\typr\scripts\windows\Install.ps1",
    "D:\@home\sma\programming\typr\scripts\windows\Initialize-Config.py",
    "D:\@home\sma\programming\typr\scripts\windows\Verify-Runtime.py",
    "D:\@home\sma\programming\typr\scripts\windows\Install.bat",
    "D:\@home\sma\programming\typr\scripts\windows\Uninstall.bat"
)
foreach ($f in $files) {
    try {
        $code = Get-Content $f -Raw -ErrorAction Stop
        $errors = $null
        $ast = [System.Management.Automation.Language.Parser]::ParseInput($code, [ref]$null, [ref]$errors)
        if ($errors) { "ERROR ${f}:"; $errors | ForEach-Object { Write-Output $_ } }
        else { "OK ${f}" }
    } catch {
        "ERR-UNEXPECTED ${f}: $_"
    }
}
