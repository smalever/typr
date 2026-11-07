# Windows PowerShell 5.1. Dot-sourcing defines functions only; no installer actions.
Set-StrictMode -Version 2

function Confirm-Typr([string]$Message) {
    $answer = Read-Host "$Message [y/N]"
    return [string]::IsNullOrEmpty($answer) -eq $false -and $answer -ieq 'y'
}

function Assert-TyprPlatform {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if ($principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Run the per-user Typr installer without elevation.' }
    if (-not [Environment]::Is64BitOperatingSystem -or -not [Environment]::Is64BitProcess -or
        $env:PROCESSOR_ARCHITECTURE -ne 'AMD64') { throw 'Windows 11 x64 / 64-bit PowerShell required.' }
    $os = Get-CimInstance Win32_OperatingSystem
    if ($os.ProductType -ne 1 -or [int]$os.BuildNumber -lt 22000) { throw 'Windows 11 required.' }
}

function Get-TyprOwner { return [Security.Principal.WindowsIdentity]::GetCurrent().User.Value }

function Assert-TyprPath([string]$Path) {
    $current = [IO.Path]::GetFullPath($Path)
    while ($current) {
        if (Test-Path -LiteralPath $current) {
            $item = Get-Item -LiteralPath $current -Force
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Reparse point refused: $current" }
        }
        $parent = Split-Path -Parent $current
        if ($parent -eq $current) { break }
        $current = $parent
    }
}

function Join-TyprSafe([string]$Root, [string]$Relative) {
    if (-not $Relative -or $Relative -match '(^[\\/]|:|(^|[\\/])\.\.?([\\/]|$))' -or
        $Relative -match '[<>"|?*\x00-\x1f]' -or $Relative -match '(^|[\\/])[^\\/]*[ .]([\\/]|$)' -or
        $Relative -match '(?i)(^|[\\/])(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\.[^\\/]*)?([\\/]|$)') { throw 'Unsafe manifest path.' }
    $full = [IO.Path]::GetFullPath((Join-Path $Root $Relative))
    $prefix = [IO.Path]::GetFullPath($Root).TrimEnd('\') + '\'
    if (-not $full.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) { throw 'Path escapes installation.' }
    Assert-TyprPath $full
    return $full
}

function Read-TyprJson([string]$Path) {
    Assert-TyprPath $Path
    try {
        $bytes = [IO.File]::ReadAllBytes($Path)
        $text = [System.Text.UTF8Encoding]::new($false).GetString($bytes)
        if (-not $text) { throw "Empty manifest: $Path" }
        return $text | ConvertFrom-Json
    } catch { throw "Invalid manifest: $Path" }
}

function Assert-TyprInventory($Manifest) {
    if ($Manifest.schema -ne 1 -or @($Manifest.files).Count -lt 1) { throw 'Invalid inventory schema.' }
    $seen = @{}
    foreach ($f in $Manifest.files) {
        $null = Join-TyprSafe ([IO.Path]::GetTempPath()) $f.path
        if ($f.sha256 -notmatch '^[a-fA-F0-9]{64}$' -or $seen.ContainsKey($f.path) -or
            $f.path -ieq 'ownership.json') { throw 'Invalid inventory entry.' }
        $seen[$f.path] = $true
    }
}

function Assert-TyprFiles([string]$Root, $Manifest, [switch]$AllowMissing, [switch]$PartialTransaction) {
    Assert-TyprPath $Root
    Assert-TyprInventory $Manifest
    $expected = @{'ownership.json' = $true}
    $directories = @{}
    foreach ($f in $Manifest.files) {
        $path = Join-TyprSafe $Root $f.path
        $expected[$f.path] = $true
        $parent = Split-Path -Parent ($f.path.Replace('/','\'))
        while ($parent) { $directories[$parent] = $true; $parent = Split-Path -Parent $parent }
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            if ($AllowMissing) { continue }
            throw "Missing payload file: $($f.path)"
        }
        if (-not $PartialTransaction -and (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ine $f.sha256) { throw "Modified file refused: $($f.path)" }
    }
    if (Test-Path -LiteralPath $Root) {
        # Do not recurse through junctions, even inside an otherwise owned tree.
        $queue = New-Object 'System.Collections.Generic.Queue[string]'
        $queue.Enqueue($Root)
        while ($queue.Count) {
            $dir = $queue.Dequeue()
            foreach ($item in Get-ChildItem -LiteralPath $dir -Force) {
                Assert-TyprPath $item.FullName
                $rel = $item.FullName.Substring($Root.TrimEnd('\').Length + 1)
                if ($item.PSIsContainer) {
                    if (-not $directories.ContainsKey($rel)) { throw "Unowned directory refused: $rel" }
                    $queue.Enqueue($item.FullName); continue
                }
                if (-not $expected.ContainsKey($rel)) { throw "Unowned file refused: $rel" }
            }
        }
    }
}

function Write-TyprJson([string]$Path, $Value) {
    Assert-TyprPath $Path
    # Keep crash leftovers outside the managed directory/inventory. Same-volume
    # sibling-parent placement retains atomic rename without adopting stale files.
    $scratch = Split-Path -Parent (Split-Path -Parent ([IO.Path]::GetFullPath($Path)))
    if (-not $scratch) { throw 'JSON destination requires an existing parent scratch directory.' }
    Assert-TyprPath $scratch
    $tmp = Join-Path $scratch ([guid]::NewGuid().ToString('N') + '.json-tmp')
    $bytes = [Text.Encoding]::UTF8.GetBytes(($Value | ConvertTo-Json -Depth 15))
    $stream = [IO.File]::Open($tmp, 'CreateNew', 'Write', 'None')
    try {
        try { $stream.Write($bytes, 0, $bytes.Length); $stream.Flush($true) } finally { $stream.Dispose() }
        if (Test-Path -LiteralPath $Path) { [IO.File]::Replace($tmp, $Path, [System.Management.Automation.Language.NullString]::Value, $true) }
        else { [IO.File]::Move($tmp, $Path) }
    } finally { if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Force } }
}

function Write-TyprPayloadZip([string]$Payload, [string]$OutputZip) {
    Assert-TyprPath $OutputZip
    $temporary = Join-Path (Split-Path -Parent ([IO.Path]::GetFullPath($OutputZip))) ([guid]::NewGuid().ToString('N') + '.zip-tmp')
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    try {
        $zip = [IO.Compression.ZipFile]::Open($temporary, 'Create')
        try {
            foreach ($file in Get-ChildItem -LiteralPath $Payload -File -Recurse | Sort-Object FullName) {
                Assert-TyprPath $file.FullName
                $entry = $zip.CreateEntry(('Typr/' + $file.FullName.Substring($Payload.Length + 1).Replace('\','/')), 'Optimal')
                $entry.LastWriteTime = [DateTimeOffset]::Parse('2020-01-01T00:00:00Z')
                $inputStream = [IO.File]::OpenRead($file.FullName)
                try {
                    $outputStream = $entry.Open()
                    try { $inputStream.CopyTo($outputStream) } finally { $outputStream.Dispose() }
                } finally { $inputStream.Dispose() }
            }
        } finally { $zip.Dispose() }
        [IO.File]::Move($temporary, [IO.Path]::GetFullPath($OutputZip))
    } finally { if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force } }
}

function Read-TyprTransaction([string]$Path, [string]$Root, [string]$Owner, [string]$Kind) {
    $t = Read-TyprJson $Path
    if ($t.schema -ne 1 -or $t.kind -cne $Kind -or $t.path -ine $Root -or $t.manifest.owner -cne $Owner -or
        $t.manifest.product -cne 'Typr.Windows') { throw 'Invalid transaction receipt; preserved for inspection.' }
    Assert-TyprInventory $t.manifest
    if ($Kind -eq 'delete' -and (Test-Path -LiteralPath $Root)) {
        if (-not $t.PSObject.Properties['directory_id'] -or $t.directory_id -cne (Get-TyprDirectoryIdentity $Root)) {
            throw 'Deletion directory identity mismatch; resource preserved.'
        }
        $inside = Join-Path $Root 'ownership.json'
        if (Test-Path -LiteralPath $inside) {
            $owned = Read-TyprJson $inside
            if (($owned | ConvertTo-Json -Depth 15 -Compress) -cne ($t.manifest | ConvertTo-Json -Depth 15 -Compress)) {
                throw 'Conflicting in-tree deletion ownership; resource preserved.'
            }
        }
    }
    return $t.manifest
}

function Get-TyprDirectoryIdentity([string]$Path) {
    Assert-TyprPath $Path
    if (-not ('TyprInstaller.DirectoryIdentity' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;
namespace TyprInstaller {
    public static class DirectoryIdentity {
        [StructLayout(LayoutKind.Sequential)]
        struct FileInfo {
            public uint Attributes;
            public System.Runtime.InteropServices.ComTypes.FILETIME Created, Accessed, Written;
            public uint Volume, SizeHigh, SizeLow, Links, IndexHigh, IndexLow;
        }
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        static extern SafeFileHandle CreateFile(string name, uint access, uint share,
            IntPtr security, uint disposition, uint flags, IntPtr template);
        [DllImport("kernel32.dll", SetLastError = true)]
        static extern bool GetFileInformationByHandle(SafeFileHandle handle, out FileInfo info);
        public static string Read(string path) {
            using (var handle = CreateFile(path, 0, 7, IntPtr.Zero, 3, 0x02200000, IntPtr.Zero)) {
                if (handle.IsInvalid) throw new Win32Exception(Marshal.GetLastWin32Error());
                FileInfo info;
                if (!GetFileInformationByHandle(handle, out info))
                    throw new Win32Exception(Marshal.GetLastWin32Error());
                if ((info.Attributes & 0x400) != 0 || (info.Attributes & 0x10) == 0)
                    throw new InvalidOperationException("Not a plain directory");
                return string.Format("{0:X8}:{1:X8}{2:X8}:{3:X8}{4:X8}", info.Volume,
                    info.IndexHigh, info.IndexLow, info.Created.dwHighDateTime, info.Created.dwLowDateTime);
            }
        }
    }
}
'@
    }
    return [TyprInstaller.DirectoryIdentity]::Read([IO.Path]::GetFullPath($Path))
}

function Read-TyprOwnership([string]$Root, [string]$Owner) {
    if (-not (Test-Path -LiteralPath (Join-Path $Root 'ownership.json')) -and (Test-Path -LiteralPath "$Root.delete.json")) {
        $m = Read-TyprTransaction "$Root.delete.json" $Root $Owner 'delete'
    } else { $m = Read-TyprJson (Join-Path $Root 'ownership.json') }
    Assert-TyprInventory $m
    if ($m.owner -cne $Owner -or $m.root -ine [IO.Path]::GetFullPath($Root) -or
        $m.product -cne 'Typr.Windows') { throw 'Foreign installation ownership.' }
    return $m
}

function Assert-TyprNotRunning([string]$Root) {
    foreach ($p in Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'") {
        if (-not $p.ExecutablePath) { throw 'Cannot verify running Python process; close Python applications and rerun.' }
        if ($p.ExecutablePath.StartsWith($Root.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
            throw 'Typr is running. Exit it from its tray menu and rerun.'
        }
    }
}

function Remove-TyprEmptyDirectory([string]$Path) { [IO.Directory]::Delete($Path) }

function Remove-TyprTree([string]$Root, $Manifest, [switch]$PartialTransaction) {
    $receipt = "$Root.delete.json"
    if ($PartialTransaction) {
        $proven = Read-TyprTransaction "$Root.transaction.json" $Root $Manifest.owner 'stage'
        if (($proven.files | ConvertTo-Json -Compress) -cne ($Manifest.files | ConvertTo-Json -Compress)) { throw 'Stage receipt conflict.' }
        $inside = Join-Path $Root 'ownership.json'
        if (Test-Path -LiteralPath $inside) {
            $owned = Read-TyprJson $inside
            if (($owned | ConvertTo-Json -Depth 15 -Compress) -cne ($proven | ConvertTo-Json -Depth 15 -Compress)) {
                throw 'Corrupt/conflicting in-tree transaction ownership.'
            }
        }
    }
    if (Test-Path -LiteralPath $receipt) {
        $proven = Read-TyprTransaction $receipt $Root $Manifest.owner 'delete'
        if (($proven | ConvertTo-Json -Depth 15 -Compress) -cne ($Manifest | ConvertTo-Json -Depth 15 -Compress)) { throw 'Deletion receipt conflict.' }
        if (-not (Test-Path -LiteralPath $Root)) {
            Remove-Item -LiteralPath $receipt -Force
            return
        }
    }
    Assert-TyprFiles $Root $Manifest -AllowMissing -PartialTransaction:$PartialTransaction
    if (-not (Test-Path -LiteralPath $receipt)) {
        Write-TyprJson $receipt @{ schema = 1; kind = 'delete'; path = $Root; manifest = $Manifest;
            directory_id = (Get-TyprDirectoryIdentity $Root) }
    }
    foreach ($f in $Manifest.files) {
        $p = Join-TyprSafe $Root $f.path
        if (Test-Path -LiteralPath $p) { Remove-Item -LiteralPath $p -Force }
    }
    $ownership = Join-Path $Root 'ownership.json'
    if (Test-Path -LiteralPath $ownership) { Remove-Item -LiteralPath $ownership -Force }
    # Empty directories only; never recursively delete unknown content.
    Get-ChildItem -LiteralPath $Root -Directory -Recurse -Force | Sort-Object { $_.FullName.Length } -Descending |
        ForEach-Object { Remove-TyprEmptyDirectory $_.FullName }
    Remove-TyprEmptyDirectory $Root
    Remove-Item -LiteralPath $receipt -Force
}

function Install-TyprPayload([string]$Payload, [string]$Root, [string]$Owner) {
    Assert-TyprNotRunning $Root
    Assert-TyprPath $Root
    $payloadJson = Join-Path $Payload 'payload.json'
    if (Test-Path -LiteralPath $payloadJson) {
        $incoming = Read-TyprJson $payloadJson
        # payload.json itself is the inventory envelope, not a self-hashed file.
        Assert-TyprInventory $incoming
    } else {
        $files = @(Get-ChildItem -LiteralPath $Payload -File -Recurse | Sort-Object FullName | ForEach-Object {
            [ordered]@{ path = $_.FullName.Substring($Payload.Length + 1); sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant() }
        })
        $incoming = [PSCustomObject]@{ schema = 1; files = $files }
    }
      foreach ($required in @('runtime\pythonw.exe','runtime\python.exe','runtime\python315._pth',
            'runtime\Lib\site-packages\typr\__main__.py','Install.ps1','TyprInstaller.ps1','Uninstall.bat')) {
          if (-not (@($incoming.files.path) -icontains $required)) { throw "Incomplete payload: $required" }
      }
    foreach ($f in $incoming.files) {
        $p = Join-TyprSafe $Payload $f.path
        if ((Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash -ine $f.sha256) { throw 'Payload checksum failure.' }
    }
    $stage = "$Root.stage"
    $backup = "$Root.backup"
    $null = New-Item -ItemType Directory -Path (Split-Path -Parent $Root) -Force
    foreach ($path in @($stage, $backup)) { Assert-TyprPath $path }
    foreach ($path in @($Root, $backup, $stage)) {
        if (Test-Path -LiteralPath "$path.delete.json") {
            $deleting = Read-TyprTransaction "$path.delete.json" $path $Owner 'delete'
            if (Test-Path -LiteralPath $path) { Remove-TyprTree $path $deleting -PartialTransaction:($path -eq $stage) }
            else { Remove-Item -LiteralPath "$path.delete.json" }
        }
    }
    if (Test-Path -LiteralPath $backup) {
        # Manifests carry the final root, including while staged/backed up.
        $old = Read-TyprJson (Join-Path $backup 'ownership.json')
        if ($old.owner -cne $Owner -or $old.root -ine $Root -or $old.product -cne 'Typr.Windows') { throw 'Foreign backup.' }
        Assert-TyprFiles $backup $old -AllowMissing
        if (-not (Test-Path -LiteralPath $Root)) { Move-Item -LiteralPath $backup -Destination $Root }
        else {
            $live = Read-TyprOwnership $Root $Owner
            Assert-TyprFiles $Root $live
            Remove-TyprTree $backup $old
        }
    }
    if (Test-Path -LiteralPath $Root) {
        $old = Read-TyprOwnership $Root $Owner
        Assert-TyprFiles $Root $old -AllowMissing
        Assert-TyprShortcutReceipt $old $Root
    }
    $manifest = [ordered]@{ schema = 1; product = 'Typr.Windows'; owner = $Owner;
        root = $Root; files = @($incoming.files); shortcuts = @() }
    if (Test-Path -LiteralPath $Root) { $manifest.shortcuts = @($old.shortcuts) }
    if (Test-Path -LiteralPath "$stage.transaction.json") {
        $staged = Read-TyprTransaction "$stage.transaction.json" $stage $Owner 'stage'
        if (Test-Path -LiteralPath $stage) { Remove-TyprTree $stage $staged -PartialTransaction }
        Remove-Item -LiteralPath "$stage.transaction.json"
    }
    if (Test-Path -LiteralPath $stage) { throw 'Unowned staging directory; preserved for inspection.' }
    Write-TyprJson "$stage.transaction.json" @{ schema = 1; kind = 'stage'; path = $stage; manifest = $manifest }
    $null = New-Item -ItemType Directory -Path $stage
    # Receipt precedes copies, allowing safe cleanup/resume of partial staging.
    Write-TyprJson (Join-Path $stage 'ownership.json') $manifest
    foreach ($f in $incoming.files) {
        $target = Join-TyprSafe $stage $f.path
        $null = New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force
        Copy-Item -LiteralPath (Join-TyprSafe $Payload $f.path) -Destination $target
    }
    Assert-TyprFiles $stage $manifest
    try {
        if (Test-Path -LiteralPath $Root) { Move-Item -LiteralPath $Root -Destination $backup }
        Move-Item -LiteralPath $stage -Destination $Root
        Remove-Item -LiteralPath "$stage.transaction.json"
    } catch {
        if (-not (Test-Path -LiteralPath $Root) -and (Test-Path -LiteralPath $backup)) {
            Move-Item -LiteralPath $backup -Destination $Root
        }
        throw
    }
    if (Test-Path -LiteralPath $backup) { Remove-TyprTree $backup $old }
}

function Get-TyprShellFolder([string]$Name) { return [Environment]::GetFolderPath($Name) }

function Get-TyprShortcutSpecs([string]$Root, [switch]$Startup) {
    $menu = Get-TyprShellFolder 'Programs'
    if (-not $menu) { throw 'Start menu folder unavailable.' }
    $specs = @(
        [pscustomobject]@{ path = (Join-Path $menu 'Typr.lnk'); target = "${Root}\\runtime\\pythonw.exe"; arguments = '-B -m typr' },
        [pscustomobject]@{ path = (Join-Path $menu 'Uninstall Typr.lnk'); target = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe";
            arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$Root\Uninstall.bat`"" }
    )
    if ($Startup) {
        $specs += [pscustomobject]@{ path = (Join-Path (Get-TyprShellFolder 'Startup') 'Typr.lnk');
            target = "${Root}\\runtime\\pythonw.exe"; arguments = '-B -m typr' }
    }
    return $specs
}

function Assert-TyprShortcut($Spec, [string]$Root) {
    Assert-TyprPath $Spec.path
    if (-not (Test-Path -LiteralPath $Spec.path)) { return }
    $shell = New-Object -ComObject WScript.Shell
    $link = $shell.CreateShortcut($Spec.path)
    if ($link.TargetPath -ine $Spec.target -or $link.Arguments -cne $Spec.arguments -or $link.WorkingDirectory -ine $Root) {
        throw "Foreign/modified shortcut: $($Spec.path)"
    }
}

function Set-TyprShortcuts([string]$Root, [string]$Owner, [switch]$Startup) {
    $m = Read-TyprOwnership $Root $Owner
    $specs = @(Get-TyprShortcutSpecs $Root -Startup:$Startup)
    foreach ($s in $specs) {
        if (Test-Path -LiteralPath $s.path) {
            if (-not (@($m.shortcuts) | Where-Object { $_.path -ieq $s.path })) { throw 'Unowned shortcut exists.' }
            Assert-TyprShortcut $s $Root
        }
    }
    # Keep prior explicitly opted-in Startup registration on repair.
    $all = @($m.shortcuts)
    foreach ($s in $specs) { if (-not ($all | Where-Object { $_.path -ieq $s.path })) { $all += $s } }
    $m.shortcuts = $all
    Write-TyprJson (Join-Path $Root 'ownership.json') $m
    foreach ($s in $specs) {
        Assert-TyprPath $s.path
        $shell = New-Object -ComObject WScript.Shell
        $link = $shell.CreateShortcut($s.path)
        $link.TargetPath = $s.target; $link.Arguments = $s.arguments; $link.WorkingDirectory = $Root
        $link.Save()
    }
}

function Assert-TyprShortcutReceipt($Manifest, [string]$Root) {
    $allowed = @(Get-TyprShortcutSpecs $Root -Startup)
    foreach ($s in $Manifest.shortcuts) {
        $match = @($allowed | Where-Object { $_.path -ieq $s.path -and $_.target -ieq $s.target -and $_.arguments -ceq $s.arguments })
        if ($match.Count -ne 1) { throw 'Invalid shortcut receipt.' }
        Assert-TyprShortcut $s $Root
    }
}

function Get-TyprDockerEndpoint {
    if ($env:DOCKER_HOST -and $env:DOCKER_HOST -notin @('npipe:////./pipe/dockerDesktopLinuxEngine','npipe:////./pipe/docker_engine')) {
        throw 'Remote/custom DOCKER_HOST refused.'
    }
    # No ambient context is used for daemon commands, even after context switches.
    return 'npipe:////./pipe/dockerDesktopLinuxEngine'
}

function Invoke-TyprDocker([string[]]$Arguments, [switch]$AllowFailure) {
    $endpoint = Get-TyprDockerEndpoint
    $previous = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $records = @(& docker --host $endpoint @Arguments 2>&1)
        $exitCode = $LASTEXITCODE
    } finally { $ErrorActionPreference = $previous }
    $output = @($records | Where-Object { $_ -isnot [Management.Automation.ErrorRecord] })
    foreach ($record in $records) { if ($record -is [Management.Automation.ErrorRecord]) { Write-Verbose $record.ToString() } }
    if ($exitCode -ne 0) {
        if ($AllowFailure) { return $null }
        throw 'Docker command failed. Start Docker Desktop in Linux containers mode and rerun.'
    }
    return ($output -join "`n")
}

function Assert-TyprDocker {
    $null = Get-TyprDockerEndpoint
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker Desktop missing.' }
    $info = Invoke-TyprDocker @('info','--format','{{json .}}') | ConvertFrom-Json
    if ($info.OSType -cne 'linux' -or $info.Architecture -notin @('x86_64','amd64')) { throw 'Local Linux/amd64 Docker engine required.' }
}

function Assert-TyprDockerSignature([string]$Path) {
    $sig = Get-AuthenticodeSignature -LiteralPath $Path
    if ($sig.Status -ne 'Valid' -or -not $sig.SignerCertificate -or
        $sig.SignerCertificate.Subject -notmatch '(?:^|,\s*)O=(?:"Docker Inc"|Docker Inc)(?:,|$)') {
        throw 'Docker installer signature rejected (requires Valid, organization Docker Inc).'
    }
}

function Install-TyprDockerDesktop {
    # Never reinstall an existing (including stopped) Desktop installation.
    if ((Get-Command docker -ErrorAction SilentlyContinue) -or
        (Test-Path -LiteralPath "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe") -or
        (Test-Path -LiteralPath "$env:LOCALAPPDATA\Programs\DockerDesktop\Docker Desktop.exe")) {
        throw 'Docker Desktop exists. Start it, select Linux containers, then rerun; reboot if required.'
    }
    if (-not (Confirm-Typr 'Download official Docker Desktop installer (large download)?')) { throw 'Docker download declined.' }
    $dir = Join-Path ([IO.Path]::GetTempPath()) ([guid]::NewGuid().ToString('N'))
    Assert-TyprPath $dir
    $null = New-Item -ItemType Directory -Path $dir
    $file = Join-Path $dir 'Docker Desktop Installer.exe'
    try {
        Invoke-WebRequest -UseBasicParsing -Uri 'https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe' -OutFile $file
        Assert-TyprDockerSignature $file
        if (-not (Confirm-Typr 'Launch signed Docker Desktop installer with UAC? Review WSL/system changes yourself.')) { throw 'Docker launch declined.' }
        Assert-TyprDockerSignature $file
        $null = Start-Process -FilePath $file -Verb RunAs -Wait -PassThru
    } finally {
        if (Test-Path -LiteralPath $file) { Remove-Item -LiteralPath $file -Force }
        [IO.Directory]::Delete($dir)
    }
    throw 'Docker installer finished. Reboot if requested, start Docker Desktop, then rerun Typr installer.'
}

function Get-TyprSTTSpec([ValidateSet('Parakeet','GigaSTT')][string]$Kind, [string]$Owner) {
    $suffix = $Owner.ToLowerInvariant() -replace '[^a-z0-9-]', ''
    $name = "typr-win-$suffix-$($Kind.ToLowerInvariant())"
    if ($Kind -eq 'GigaSTT') {
        return [pscustomobject]@{ kind = $Kind; owner = $Owner; name = $name; volume = "$name-models";
            image = 'ghcr.io/ekhodzitsky/gigastt@sha256:ac7f7ccb7d5b9628d9e16cc361f29e61beedd8e1df8b0927b4a17921b7ec2f35'; port = 9876; mount = '/home/gigastt/.gigastt/models';
            env = @('GIGASTT_MODEL_VARIANT=rnnt'); command = @('serve','--port','9876','--host','0.0.0.0','--bind-all','--pool-size','1') }
    }
    return [pscustomobject]@{ kind = $Kind; owner = $Owner; name = $name; volume = "$name-models";
        image = 'parakeet-tdt:cpu'; port = 5092; mount = '/app/models';
        env = @('PARAKEET_USE_GPU=false','PARAKEET_DEFAULT_MODEL=parakeet-tdt-0.6b-v3','PARAKEET_BATCHED=0'); command = @() }
}

function Build-TyprParakeet {
    if (-not (Confirm-Typr 'Download pinned Parakeet source and build CPU image? Docker base images/dependencies/models may use multiple GB.')) { throw 'Parakeet build declined.' }
    $commit = '06464cd06a0f75426ce46e94c2d04ee7e26f48c0'
    $sha = 'fa58716020a9a95d4b6695f6b0a5466f064d1b3719dd6db071f058fc3ffbbc90'
    $dir = Join-Path ([IO.Path]::GetTempPath()) ('typr-parakeet-' + [guid]::NewGuid().ToString('N'))
    Assert-TyprPath $dir
    $null = New-Item -ItemType Directory -Path $dir
    try {
        $archive = Join-Path $dir 'source.zip'
        Invoke-WebRequest -UseBasicParsing -Uri "https://codeload.github.com/groxaxo/parakeet-tdt-0.6b-v3-fastapi-openai/zip/$commit" -OutFile $archive
        if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ine $sha) { throw 'Parakeet source SHA256 mismatch.' }
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $zip = [IO.Compression.ZipFile]::OpenRead($archive)
        try {
            $seen = @{}
            foreach ($entry in $zip.Entries) {
                if ($entry.FullName.EndsWith('/')) { continue }
                $path = Join-TyprSafe $dir $entry.FullName
                if ($seen.ContainsKey($path)) { throw 'Duplicate archive entry.' }
                $seen[$path] = $true
                $null = New-Item -ItemType Directory -Path (Split-Path -Parent $path) -Force
                [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $path, $false)
            }
        } finally { $zip.Dispose() }
        $source = Join-Path $dir "parakeet-tdt-0.6b-v3-fastapi-openai-$commit"
        if (-not (Test-Path -LiteralPath "$source\Dockerfile.cpu" -PathType Leaf)) { throw 'Pinned archive lacks Dockerfile.cpu.' }
        $null = Invoke-TyprDocker @('build','--platform','linux/amd64','--file',"$source\Dockerfile.cpu",'--tag','parakeet-tdt:cpu',$source)
    } finally {
        Assert-TyprPath $dir
        Remove-Item -LiteralPath $dir -Recurse -Force
    }
}

function Assert-TyprLabels($Labels, $Spec) {
    if (-not $Labels -or $Labels.'io.typr.owner' -cne $Spec.owner -or $Labels.'io.typr.windows' -cne '1' -or
        $Labels.'io.typr.stt' -cne $Spec.kind) { throw 'Foreign Docker resource; never adopted.' }
}

function Get-TyprDockerObject([string]$Type, [string]$Name) {
    # Listing first distinguishes absence from an inspect/daemon error.
    if ($Type -eq 'container') { $names = Invoke-TyprDocker @('container','ls','--all','--format','{{.Names}}') }
    else { $names = Invoke-TyprDocker @($Type,'ls','--format','{{.Name}}') }
    if (($names -split "`n") -ccontains $Name) {
        return @(Invoke-TyprDocker @($Type,'inspect',$Name) | ConvertFrom-Json)[0]
    }
    return $null
}

function Assert-TyprContainer($Container, $Spec, [string]$ImageId, $ImageConfig = $null) {
    Assert-TyprLabels $Container.Config.Labels $Spec
    $bindings = @($Container.HostConfig.PortBindings.PSObject.Properties)
    $binding = $Container.HostConfig.PortBindings."$($Spec.port)/tcp"
    $mounts = @($Container.Mounts)
    if ($Container.Config.Image -cne $Spec.image -or $Container.Image -cne $ImageId -or
        $Container.HostConfig.NetworkMode -notin @('default','bridge') -or
        $Container.HostConfig.RestartPolicy.Name -cne 'no' -or $Container.HostConfig.Privileged -or
        @($Container.HostConfig.Binds).Count -ne 1 -or
        $Container.HostConfig.Binds[0] -cne "$($Spec.volume):$($Spec.mount)" -or
        $bindings.Count -ne 1 -or @($binding).Count -ne 1 -or
        $binding[0].HostIp -cne '127.0.0.1' -or $binding[0].HostPort -cne [string]$Spec.port -or
        $mounts.Count -ne 1 -or $mounts[0].Type -cne 'volume' -or $mounts[0].Name -cne $Spec.volume -or
        $mounts[0].Destination -cne $Spec.mount -or -not $mounts[0].RW) { throw 'Docker container spec conflict; resource preserved.' }
    foreach ($e in $Spec.env) { if (@($Container.Config.Env) -cnotcontains $e) { throw 'Container environment conflict.' } }
    if ($Spec.command.Count -and (($Container.Config.Cmd | ConvertTo-Json -Compress) -cne ($Spec.command | ConvertTo-Json -Compress))) {
        throw 'Container command conflict.'
    }
    if ($ImageConfig) {
        if (($Container.Config.Entrypoint | ConvertTo-Json -Compress) -cne ($ImageConfig.Entrypoint | ConvertTo-Json -Compress) -or
            (-not $Spec.command.Count -and ($Container.Config.Cmd | ConvertTo-Json -Compress) -cne ($ImageConfig.Cmd | ConvertTo-Json -Compress))) {
            throw 'Container entrypoint/default command conflict.'
        }
        foreach ($property in @('CapAdd','Devices','DeviceRequests','ExtraHosts','VolumesFrom')) {
            if ($Container.HostConfig.$property) { throw "Unexpected container host option: $property" }
        }
        if ($Container.HostConfig.PidMode -or $Container.HostConfig.IpcMode -notin @('private','')) { throw 'Unexpected container namespace sharing.' }
    }
}

function Get-TyprRunArguments($Spec) {
    $a = @('run','--detach','--pull','never','--name',$Spec.name,'--restart','no',
        '--label',"io.typr.owner=$($Spec.owner)",'--label','io.typr.windows=1','--label',"io.typr.stt=$($Spec.kind)",
        '--publish',"127.0.0.1:$($Spec.port):$($Spec.port)",'--volume',"$($Spec.volume):$($Spec.mount)")
    foreach ($e in $Spec.env) { $a += @('--env',$e) }
    return $a + @($Spec.image) + @($Spec.command)
}

function Get-TyprLoopbackJson([string]$Uri) {
    if ($Uri -notmatch '^http://127\.0\.0\.1:(5092|9876)/(healthz|health|ready|v1/models)$') { throw 'Non-loopback readiness URL refused.' }
    $request = [Net.HttpWebRequest]::Create($Uri)
    $request.Proxy = $null; $request.AllowAutoRedirect = $false; $request.Timeout = 3000; $request.ReadWriteTimeout = 3000
    $response = $request.GetResponse()
    try {
        if ([int]$response.StatusCode -ne 200) { throw 'STT not ready.' }
        $reader = New-Object IO.StreamReader($response.GetResponseStream())
        try { $text = $reader.ReadToEnd() } finally { $reader.Dispose() }
        if ($text) { return $text | ConvertFrom-Json }
        return $null
    } finally { $response.Dispose() }
}

function Test-TyprSTTReady($Spec) {
    if ($Spec.kind -eq 'GigaSTT') {
        $null = Get-TyprLoopbackJson 'http://127.0.0.1:9876/ready'
        $health = Get-TyprLoopbackJson 'http://127.0.0.1:9876/health'
        return $health.model -ceq 'gigaam-v3-rnnt' -and $health.variant -ceq 'rnnt'
    }
    $null = Get-TyprLoopbackJson 'http://127.0.0.1:5092/healthz'
    $h = Get-TyprLoopbackJson 'http://127.0.0.1:5092/health'
    $model = 'parakeet-tdt-0.6b-v3'
    return ($h.ready -eq $true -and $h.default_model -ceq $model -and @($h.loaded) -ccontains $model -and
        @($h.models) -ccontains $model -and $h.runtime.$model.backend -ceq 'cpu' -and $h.runtime.$model.encoder_precision -ceq 'int8')
}

function Wait-TyprSTT($Spec, [int]$TimeoutSeconds = 600) {
    $clock = [Diagnostics.Stopwatch]::StartNew()
    do {
        try { if (Test-TyprSTTReady $Spec) { return } } catch { Write-Verbose 'STT not ready yet.' }
        if ($clock.Elapsed.TotalSeconds -ge $TimeoutSeconds) { break }
        Start-Sleep -Seconds 2
    } while ($clock.Elapsed.TotalSeconds -lt $TimeoutSeconds)
    throw 'STT readiness timed out. Resources preserved; rerun installer to resume.'
}

function Install-TyprSTT($Spec, [switch]$Check) {
    Assert-TyprDocker
    $image = Invoke-TyprDocker @('image','inspect',$Spec.image) -AllowFailure
    if (-not $image) {
        if ($Check) { throw "Missing image: $($Spec.image)" }
        if ($Spec.kind -eq 'Parakeet') { Build-TyprParakeet }
        else {
            if (-not (Confirm-Typr 'Pull GigaSTT image (may download multiple GB)?')) { throw 'Image pull declined.' }
            $null = Invoke-TyprDocker @('pull','--platform','linux/amd64',$Spec.image)
        }
        $image = Invoke-TyprDocker @('image','inspect',$Spec.image)
    }
    $imageObject = @($image | ConvertFrom-Json)[0]
    if ($imageObject.Os -cne 'linux' -or $imageObject.Architecture -cne 'amd64') { throw 'STT image must be Linux/amd64.' }
    $v = Get-TyprDockerObject 'volume' $Spec.volume
    if ($v) {
        Assert-TyprLabels $v.Labels $Spec
        if ($v.Driver -cne 'local' -or ($v.Options -and @($v.Options.PSObject.Properties).Count -ne 0)) { throw 'Volume spec conflict.' }
    }
    $c = Get-TyprDockerObject 'container' $Spec.name
    if ($c) { Assert-TyprContainer $c $Spec $imageObject.Id $imageObject.Config }
    if ($Check) {
        if (-not $v -or -not $c -or -not $c.State.Running -or -not (Test-TyprSTTReady $Spec)) { throw 'STT is not ready.' }
        return
    }
    if (-not $c -or -not $c.State.Running) {
        if (-not (Confirm-Typr 'Start local STT? Initial model download may use multiple GB. No system autostart will be enabled.')) { throw 'STT start declined.' }
        # Deterministic SID names + strict labels/spec provide recovery before a separate receipt can be written.
        if (-not $v) {
            $null = Invoke-TyprDocker @('volume','create','--driver','local','--label',"io.typr.owner=$($Spec.owner)",
                '--label','io.typr.windows=1','--label',"io.typr.stt=$($Spec.kind)",$Spec.volume)
        }
        if ($c) { $null = Invoke-TyprDocker @('start',$Spec.name) }
        else { $null = Invoke-TyprDocker (Get-TyprRunArguments $Spec) }
    }
    Wait-TyprSTT $Spec
    if ($Spec.kind -eq 'GigaSTT') {
        Write-Host 'GigaSTT endpoint: http://127.0.0.1:9876/v1 ; model gigaam-v3-rnnt. Fresh configuration is initialized automatically; existing settings are preserved.'
    } else { Write-Host 'Typr Settings: Base URL http://127.0.0.1:5092/v1 ; model parakeet-tdt-0.6b-v3.' }
    Write-Host 'No existing configuration was read or overwritten.'
}

function Initialize-TyprConfig([string]$Root, [string]$STT) {
    if ($STT -eq 'Skip') { return }
    $kind = 'Parakeet'
    if ($STT -eq 'GigaSTT') { $kind = 'GigaSTT' }
    & "$Root\\runtime\python.exe" -B "$Root\Initialize-Config.py" $kind
    if ($LASTEXITCODE -ne 0) { throw 'Fresh configuration initialization refused. Existing data preserved; configure the endpoint/model in Typr Settings.' }
}

function Remove-TyprModels([string]$Owner) {
    Assert-TyprDocker
    # Preflight ALL resources before any deletion. Never delete images or Docker itself.
    $resources = @()
    foreach ($kind in @('Parakeet','GigaSTT')) {
        $s = Get-TyprSTTSpec $kind $Owner
        $v = Get-TyprDockerObject 'volume' $s.volume
        $c = Get-TyprDockerObject 'container' $s.name
        if ($v) {
            Assert-TyprLabels $v.Labels $s
            if ($v.Driver -cne 'local' -or ($v.Options -and @($v.Options.PSObject.Properties).Count -ne 0)) { throw 'Volume spec conflict.' }
        }
        if ($c) {
            $image = @(Invoke-TyprDocker @('image','inspect',$s.image) | ConvertFrom-Json)[0]
            Assert-TyprContainer $c $s $image.Id $image.Config
            if ($c.State.Running) { throw 'Stop owned STT containers manually before removing model volumes.' }
        }
        $resources += [pscustomobject]@{ spec = $s; volume = $v; container = $c }
    }
    if (-not (Confirm-Typr 'Permanently delete ONLY verified Typr Windows STT containers and their model volumes?')) { throw 'Model deletion declined.' }
    foreach ($r in $resources) {
        if ($r.container) { $null = Invoke-TyprDocker @('container','rm',$r.spec.name) }
        if ($r.volume) { $null = Invoke-TyprDocker @('volume','rm',$r.spec.volume) }
    }
}

function Invoke-TyprInstaller([string]$Payload, [switch]$Check, [switch]$Uninstall,
    [switch]$RemoveModels, [string]$STT = 'Ask') {
    Assert-TyprPlatform
    $owner = Get-TyprOwner
    $root = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'Programs\Typr'))
    Assert-TyprPath $root
    if ($RemoveModels -and -not $Uninstall) { throw '-RemoveModels requires -Uninstall.' }
    if ($Check) {
        # No mutex/file creation, downloads, prompts, writes or daemon mutations.
        $m = Read-TyprOwnership $root $owner
        Assert-TyprFiles $root $m
        Assert-TyprShortcutReceipt $m $root
        if ($STT -eq 'Ask') { throw 'Specify -STT Parakeet, GigaSTT, Both or Skip for readiness check.' }
        if (-not $Uninstall) {
            foreach ($kind in @('Parakeet','GigaSTT')) {
                if ($STT -eq $kind -or $STT -eq 'Both') { Install-TyprSTT (Get-TyprSTTSpec $kind $owner) -Check }
            }
        }
        Write-Host 'Read-only readiness checks passed. Release qualification for CPython 3.15.2 remains OPEN.'
        return
    }
    $mutex = New-Object Threading.Mutex($false, "Global\Typr-Installer-$owner")
    $locked = $false
    try {
        try { $locked = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $locked = $true }
        if (-not $locked) { throw 'Another Typr installer is active.' }
        if ($Uninstall) {
            Assert-TyprNotRunning $root
            $m = Read-TyprOwnership $root $owner
            Assert-TyprFiles $root $m -AllowMissing
            Assert-TyprShortcutReceipt $m $root
            if (-not (Confirm-Typr 'Uninstall Typr application? Config/history/models/images/Docker are preserved by default.')) { throw 'Uninstall declined.' }
            if ($RemoveModels) { Remove-TyprModels $owner }
            foreach ($s in $m.shortcuts) { if (Test-Path -LiteralPath $s.path) { Remove-Item -LiteralPath $s.path } }
            Remove-TyprTree $root $m
            Write-Host 'Application removed. LOCALAPPDATA\Typr and Docker resources preserved unless model removal was explicitly confirmed.'
            return
        }
        if (-not (Confirm-Typr "Install/repair Typr in $root ? No application will be launched.")) { throw 'Installation declined.' }
        $null = New-Item -ItemType Directory -Path (Split-Path -Parent $root) -Force
        Install-TyprPayload $Payload $root $owner
        $startup = Confirm-Typr 'Opt in to starting Typr at user logon (Startup shortcut)?'
        Set-TyprShortcuts $root $owner -Startup:$startup
        if ($STT -eq 'Ask') {
            $answer = Read-Host 'Local STT: 1 Parakeet (pinned CPU build), 2 GigaSTT, 3 Both, 4 Skip [4]'
            switch ($answer) { '1' { $STT = 'Parakeet' }; '2' { $STT = 'GigaSTT' }; '3' { $STT = 'Both' }; '' { $STT = 'Skip' }; '4' { $STT = 'Skip' }; default { throw 'Invalid STT choice.' } }
        }
        if ($STT -ne 'Skip' -and -not (Get-Command docker -ErrorAction SilentlyContinue)) { Install-TyprDockerDesktop }
        foreach ($kind in @('Parakeet','GigaSTT')) {
            if ($STT -eq $kind -or $STT -eq 'Both') { Install-TyprSTT (Get-TyprSTTSpec $kind $owner) }
        }
        Initialize-TyprConfig $root $STT
        Write-Host 'Typr installed. Launch it manually from Start. CPython 3.15.2 release qualification remains OPEN.'
    } finally {
        if ($locked) { $mutex.ReleaseMutex() }
        $mutex.Dispose()
    }
}
