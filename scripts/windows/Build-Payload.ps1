# Build on Windows x64 using an explicit CPython 3.15.2 build interpreter.
# Wheelhouse must contain all binary dependency wheels, pip and build tooling.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$BuildPython,
    [Parameter(Mandatory=$true)][string]$EmbedZip,
    [Parameter(Mandatory=$true)][ValidatePattern('^[a-fA-F0-9]{64}$')][string]$EmbedSha256,
    [Parameter(Mandatory=$true)][string]$Wheelhouse,
    [Parameter(Mandatory=$true)][string]$WheelhouseManifest,
    [Parameter(Mandatory=$true)][string]$OutputZip,
    [switch]$DownloadEmbed
)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\TyprInstaller.ps1"
Assert-TyprPlatform

function Invoke-BuildPython([string[]]$Arguments) {
    & $BuildPython @Arguments
    if ($LASTEXITCODE -ne 0) { throw 'Build Python failed.' }
}

function Expand-VerifiedEmbed([string]$Archive, [string]$Destination) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [IO.Compression.ZipFile]::OpenRead($Archive)
    try {
        $names = @{}
        foreach ($entry in $zip.Entries) {
            if ($entry.FullName.EndsWith('/')) { continue }
            $path = Join-TyprSafe $Destination $entry.FullName
            if ($names.ContainsKey($path)) { throw 'Duplicate archive path.' }
            $names[$path] = $true
            $null = New-Item -ItemType Directory -Path (Split-Path -Parent $path) -Force
            [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $path, $false)
        }
    } finally { $zip.Dispose() }
}

Assert-TyprPath $EmbedZip
Assert-TyprPath $Wheelhouse
Assert-TyprPath $OutputZip
if (Test-Path -LiteralPath $OutputZip) { throw 'Output ZIP already exists; choose a new destination.' }
if (-not (Test-Path -LiteralPath (Split-Path -Parent ([IO.Path]::GetFullPath($OutputZip))) -PathType Container)) { throw 'Output parent must exist.' }
Invoke-BuildPython @('-I','-c',"import sys,platform; assert sys.version_info[:3] == (3,15,2); assert sys.platform == 'win32'; assert platform.machine() == 'AMD64'")
if (-not (Test-Path -LiteralPath $EmbedZip)) {
    if (-not $DownloadEmbed) { throw 'Supply official python-3.15.2-embed-amd64.zip or explicitly use -DownloadEmbed.' }
    if (-not (Confirm-Typr 'Download CPython 3.15.2 embeddable amd64 ZIP from python.org? Supplied SHA256 will be required.')) { throw 'Download declined.' }
    if (-not (Test-Path -LiteralPath (Split-Path -Parent ([IO.Path]::GetFullPath($EmbedZip))) -PathType Container)) { throw 'Embed ZIP parent must exist.' }
    Invoke-WebRequest -UseBasicParsing -Uri 'https://www.python.org/ftp/python/3.15.2/python-3.15.2-embed-amd64.zip' -OutFile $EmbedZip
}
if ((Get-FileHash -LiteralPath $EmbedZip -Algorithm SHA256).Hash -ine $EmbedSha256) { throw 'CPython archive SHA256 mismatch.' }
$wheelManifest = Read-TyprJson $WheelhouseManifest
Assert-TyprInventory $wheelManifest
foreach ($f in $wheelManifest.files) {
    if ($f.path -notmatch '^[^\\/]+\.whl$') { throw 'Wheelhouse manifest must list wheels only.' }
    $p = Join-TyprSafe $Wheelhouse $f.path
    if ((Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash -ine $f.sha256) { throw 'Wheel SHA256 mismatch.' }
}
foreach ($item in Get-ChildItem -LiteralPath $Wheelhouse -Force) {
    Assert-TyprPath $item.FullName
    if ($item.PSIsContainer -or @($wheelManifest.files.path) -inotcontains $item.Name) { throw 'Unverified wheelhouse entry.' }
}
$work = Join-Path ([IO.Path]::GetTempPath()) ('typr-build-' + [guid]::NewGuid().ToString('N'))
Assert-TyprPath $work
$null = New-Item -ItemType Directory -Path $work
try {
    $payload = Join-Path $work 'Typr'
    $runtime = Join-Path $payload 'runtime'
    $wheels = Join-Path $work 'current-wheel'
    $null = New-Item -ItemType Directory -Path $runtime
    $null = New-Item -ItemType Directory -Path $wheels
    Expand-VerifiedEmbed $EmbedZip $runtime
    if (-not (Test-Path -LiteralPath "$runtime\python315._pth")) { throw 'Unexpected embedded Python minor.' }
    [IO.File]::WriteAllText("$runtime\python315._pth", "python315.zip`n.`nLib\site-packages`nimport site`n", [Text.Encoding]::ASCII)
    $repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
    # Always rebuild the checked-out source, never accept a pre-existing typr wheel.
    Invoke-BuildPython @('-I','-m','pip','wheel','--no-index','--no-deps','--no-build-isolation',
        '--wheel-dir',$wheels,$repo)
    $current = @(Get-ChildItem -LiteralPath $wheels -Filter 'typr-*.whl')
    if ($current.Count -ne 1) { throw 'Expected exactly one fresh Typr wheel.' }
    $site = Join-Path $runtime 'Lib\site-packages'
    Invoke-BuildPython @('-I','-m','pip','install','--no-index','--only-binary=:all:','--no-compile',
        '--find-links',$Wheelhouse,'--target',$site,$current[0].FullName,'pip')
    $python = Join-Path $runtime 'python.exe'
    & $python -B -c "import sys,platform; assert sys.version_info[:3] == (3,15,2); assert platform.machine() == 'AMD64'"
    if ($LASTEXITCODE -ne 0) { throw 'Embedded runtime version check failed.' }
    & $python -B -m pip check
    if ($LASTEXITCODE -ne 0) { throw 'Embedded dependency validation failed.' }
    Copy-Item -LiteralPath "$PSScriptRoot\Verify-Runtime.py" -Destination "$work\verify.py"
    & $python -B "$work\verify.py"
    if ($LASTEXITCODE -ne 0) { throw 'Offline runtime imports failed.' }
    foreach ($name in @('Install.bat','Uninstall.bat','Install.ps1','TyprInstaller.ps1','Initialize-Config.py')) {
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination (Join-Path $payload $name)
    }
    Copy-Item -LiteralPath (Join-Path $repo 'LICENSE') -Destination (Join-Path $payload 'LICENSE')
    $files = @(Get-ChildItem -LiteralPath $payload -File -Recurse | Sort-Object FullName | ForEach-Object {
        [ordered]@{ path = $_.FullName.Substring($payload.Length + 1); sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant() }
    })
    $payloadJson = Join-Path $payload 'payload.json'
    Write-TyprJson $payloadJson ([ordered]@{
        schema = 1; python = '3.15.2'; qualification = 'OPEN'; embed_sha256 = $EmbedSha256;
        wheelhouse = $wheelManifest.files; files = $files
    })
    # Stable entry order/timestamps; upstream wheels/ZIP and build tooling still affect reproducibility.
    Write-TyprPayloadZip $payload $OutputZip
    $final = Get-FileHash -LiteralPath $payloadJson -Algorithm SHA256
    if ((Get-FileHash -LiteralPath (Join-Path $OutputZip 'payload.json') -Algorithm SHA256).Hash -ine $final.Hash) { throw 'payload.json not included in ZIP.' }
    Write-Host 'Payload built; release qualification for CPython 3.15.2 remains OPEN. Test on a clean Windows 11 x64 machine before release.'
} finally {
    # Only our random build workspace, never caller inputs.
    Assert-TyprPath $work
    Remove-Item -LiteralPath $work -Recurse -Force
}
