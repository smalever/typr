$files = @("verify_final.ps1","debug_contract.ps1","debug_contract2.ps1","debug_in.ps1",
    "run_harness_final.ps1","check_gitdir.ps1","cleanup3.ps1","proc_cwd.ps1","git_config.ps1",
    "git_debug.ps1","git_final.ps1","git_final2.ps1","git_final3.ps1","git_procs.ps1")
$count = 0
foreach ($f in $files) {
    $path = "D:\@home\sma\programming\typr\$f"
    try {
        if (Test-Path $path) {
            Remove-Item -LiteralPath $path -Force -ErrorAction Stop
            Write-Output "REMOVED ${f}"
            $count++
        }
    } catch {
        Write-Output "SKIP ${f}: $($_.Exception.Message)"
    }
}
Write-Output "Cleaned $count files"
# clean harness sandbox
$sandbox = "C:\Users\smale\AppData\Local\Temp\typr_harness*"
Get-ChildItem -LiteralPath ${sandbox} -Force -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Write-Output "sandbox cleaned"
