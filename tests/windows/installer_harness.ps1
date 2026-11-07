param([Parameter(Mandatory=$true)][string]$Repository,
    [Parameter(Mandatory=$true)][string]$Sandbox)
$ErrorActionPreference = 'Stop'
. "$Repository\scripts\windows\TyprInstaller.ps1"
function Assert($Value, [string]$Message) { if (-not $Value) { throw "ASSERT: $Message" } }
function Reject([scriptblock]$Action, [string]$Message) {
    $rejected = $false
    try { & $Action } catch { $rejected = $true }
    Assert $rejected $Message
}
function Save([string]$Path, [string]$Text) {
    $null = New-Item -ItemType Directory -Path (Split-Path -Parent $Path) -Force
    [IO.File]::WriteAllText($Path, $Text)
}
Assert ($PSVersionTable.PSVersion.Major -eq 5) 'Harness must execute on PS5.1'
$owner = 'S-1-5-21-123-456-789-1001'
$payload = Join-Path $Sandbox 'payload'
$root = Join-Path $Sandbox 'Programs\Typr'
$names = @('runtime\pythonw.exe','runtime\python.exe','runtime\python315._pth',
    'runtime\Lib\site-packages\typr\__main__.py','Install.ps1','TyprInstaller.ps1','Uninstall.bat')
$files = @()
foreach ($name in $names) {
    $path = Join-Path $payload $name
    Save $path "fixture $name"
    $files += [pscustomobject]@{ path = $name; sha256 = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash }
}
Write-TyprJson (Join-Path $payload 'payload.json') @{ schema = 1; files = $files }
function Assert-TyprNotRunning { }
function Assert-TyprShortcutReceipt { }
Install-TyprPayload $payload $root $owner
$m = Read-TyprOwnership $root $owner
Assert-TyprFiles $root $m
# Resume an interrupted file copy and recover a missing owned file.
Remove-Item -LiteralPath "$root\runtime\pythonw.exe"
Install-TyprPayload $payload $root $owner
Assert (Test-Path -LiteralPath "$root\runtime\pythonw.exe") 'repair missing file'
$null = New-Item -ItemType Directory -Path "$root.stage"
Write-TyprJson "$root.stage.transaction.json" @{ schema = 1; kind = 'stage'; path = "$root.stage"; manifest = $m }
Write-TyprJson "$root.stage\ownership.json" $m
Save "$root.stage\runtime\pythonw.exe" 'truncated'
Install-TyprPayload $payload $root $owner
Assert (-not (Test-Path -LiteralPath "$root.stage")) 'partial staging recovered'
# Receipt precedes mkdir: crash immediately after mkdir is recoverable.
Write-TyprJson "$root.stage.transaction.json" @{ schema = 1; kind = 'stage'; path = "$root.stage"; manifest = $m }
$null = New-Item -ItemType Directory -Path "$root.stage"
Install-TyprPayload $payload $root $owner
Assert (-not (Test-Path -LiteralPath "$root.stage.transaction.json")) 'early receipt gap recovered'
# A killed JSON writer leaves its random scratch file OUTSIDE either managed tree.
$leftover = Join-Path (Split-Path -Parent $root) 'abandoned-writer.json-tmp'
Save $leftover 'partial JSON from killed writer'
Write-TyprJson "$root\ownership.json" $m
Install-TyprPayload $payload $root $owner
Assert-TyprFiles $root (Read-TyprOwnership $root $owner)
Assert ([IO.File]::ReadAllText($leftover) -eq 'partial JSON from killed writer') 'unproven crash leftover preserved outside inventory'
Assert (@(Get-ChildItem -LiteralPath $root -Filter '*.json-tmp').Count -eq 0) 'no JSON scratch inside installation'
Write-TyprJson "$root.stage.transaction.json" @{ schema = 1; kind = 'stage'; path = "$root.stage"; manifest = $m }
$null = New-Item -ItemType Directory -Path "$root.stage"
Write-TyprJson "$root.stage\ownership.json" $m
Install-TyprPayload $payload $root $owner
Assert (Test-Path -LiteralPath $leftover) 'staging resume ignores unrelated parent scratch'
$null = New-Item -ItemType Directory -Path "$root.stage"
Reject { Install-TyprPayload $payload $root $owner } 'receiptless unknown stage preserved'
[IO.Directory]::Delete("$root.stage")
# Predictable legacy .new is foreign and never removed/overwritten.
Save "$Sandbox\example.json.new" 'foreign'
Write-TyprJson "$Sandbox\example.json" @{ ok = 1 }
Write-TyprJson "$Sandbox\example.json" @{ ok = 2 }
Assert ([IO.File]::ReadAllText("$Sandbox\example.json.new") -eq 'foreign') 'JSON retry ignores foreign .new'
# Interrupted deletion retains external proof after in-tree receipt removal.
$deleteReceipt = @{ schema = 1; kind = 'delete'; path = $root; manifest = $m;
    directory_id = (Get-TyprDirectoryIdentity $root) }
Write-TyprJson "$root.delete.json" $deleteReceipt
$originalOwnership = [IO.File]::ReadAllText("$root\ownership.json")
$foreign = Read-TyprOwnership $root $owner
$foreign.owner = 'foreign-owner'
Write-TyprJson "$root\ownership.json" $foreign
Reject { Remove-TyprTree $root $m } 'delete sidecar cannot override foreign ownership'
Reject { Install-TyprPayload $payload $root $owner } 'install recovery rejects foreign ownership with stale delete receipt'
Assert (Test-Path -LiteralPath "$root\runtime\pythonw.exe") 'foreign conflicting tree preserved'
[IO.File]::WriteAllText("$root\ownership.json", '{corrupt')
Reject { Remove-TyprTree $root $m } 'corrupt in-tree ownership preserved'
Assert ([IO.File]::ReadAllText("$root\ownership.json") -eq '{corrupt') 'corrupt receipt not deleted'
[IO.File]::WriteAllText("$root\ownership.json", $originalOwnership)
# Replaced same-name directory must not inherit a stale receipt, even receiptless.
Move-Item -LiteralPath $root -Destination "$root.saved"
$null = New-Item -ItemType Directory -Path $root
Reject { Remove-TyprTree $root $m } 'different directory identity rejected'
Assert (Test-Path -LiteralPath $root) 'foreign empty replacement preserved'
[IO.Directory]::Delete($root)
Move-Item -LiteralPath "$root.saved" -Destination $root
function Remove-TyprEmptyDirectory { param($Path); throw 'injected locked directory' }
Reject { Remove-TyprTree $root $m } 'injected directory deletion failure'
Assert (Test-Path -LiteralPath "$root.delete.json") 'durable external delete receipt'
Assert (-not (Test-Path -LiteralPath "$root\ownership.json")) 'test interrupted after ownership deletion'
$recovered = Read-TyprOwnership $root $owner
function Remove-TyprEmptyDirectory { param($Path); [IO.Directory]::Delete($Path) }
Remove-TyprTree $root $recovered
Assert (-not (Test-Path -LiteralPath "$root.delete.json")) 'deletion retry complete'
Write-TyprJson "$root.delete.json" @{ schema = 1; kind = 'delete'; path = $root; manifest = $m }
Remove-TyprTree $root $m
Assert (-not (Test-Path -LiteralPath "$root.delete.json")) 'post-rmdir receipt cleanup resumed'
Install-TyprPayload $payload $root $owner
# Real ZIP Create mode regression, timestamp must precede entry.Open().
Write-TyprPayloadZip $payload "$Sandbox\payload.zip"
$archive = [IO.Compression.ZipFile]::OpenRead("$Sandbox\payload.zip")
try {
    Assert ($archive.Entries.Count -eq ($files.Count + 1)) 'ZIP contents complete'
    Assert ($archive.Entries[0].LastWriteTime.Year -eq 2020) 'stable ZIP timestamp'
} finally { $archive.Dispose() }
$zipHash = (Get-FileHash -LiteralPath "$Sandbox\payload.zip").Hash
Reject { Write-TyprPayloadZip $payload "$Sandbox\payload.zip" } 'ZIP no-clobber'
Assert ((Get-FileHash -LiteralPath "$Sandbox\payload.zip").Hash -eq $zipHash) 'existing output preserved'
Assert (@(Get-ChildItem -LiteralPath $Sandbox -Filter '*.zip-tmp').Count -eq 0) 'owned failed ZIP cleaned'
# Interrupted promotion: restore backup, then repair.
Move-Item -LiteralPath $root -Destination "$root.backup"
Install-TyprPayload $payload $root $owner
Assert (-not (Test-Path -LiteralPath "$root.backup")) 'backup recovered'
Save "$root\foreign.txt" 'preserve'
Reject { Install-TyprPayload $payload $root $owner } 'unowned files refused'
Assert (Test-Path -LiteralPath "$root\foreign.txt") 'unowned file preserved'
Remove-Item -LiteralPath "$root\foreign.txt"
Save "$root\runtime\pythonw.exe" 'tampered'
Reject { Install-TyprPayload $payload $root $owner } 'modified owned file refused'
Copy-Item -LiteralPath "$payload\runtime\pythonw.exe" -Destination "$root\runtime\pythonw.exe" -Force
Reject { Read-TyprOwnership $root 'other-sid' } 'foreign ownership refused'
$receipt = [IO.File]::ReadAllText("$root\ownership.json")
[IO.File]::WriteAllText("$root\ownership.json", '{broken')
Reject { Install-TyprPayload $payload $root $owner } 'corrupt manifest refused'
[IO.File]::WriteAllText("$root\ownership.json", $receipt)
foreach ($bad in @('..\escape','C:\escape','foo:bar','/absolute','a\..\b','trailing.','a\b ')) {
    Reject { Join-TyprSafe $root $bad } "unsafe path $bad"
}
$junction = Join-Path $Sandbox 'junction'
$null = New-Item -ItemType Junction -Path $junction -Target $payload
Reject { Assert-TyprPath "$junction\runtime\python.exe" } 'junction refused'
[IO.Directory]::Delete($junction)

# No COM/real shortcuts. Verify default Startup exclusion and explicit opt-in.
. "$Repository\scripts\windows\TyprInstaller.ps1"
function Assert-TyprNotRunning { }
function Get-TyprShellFolder([string]$Name) { return (Join-Path $Sandbox $Name) }
$defaults = @(Get-TyprShortcutSpecs $root)
$optin = @(Get-TyprShortcutSpecs $root -Startup)
Assert ($defaults.Count -eq 2 -and $optin.Count -eq 3) 'Startup explicit opt-in only'
$fake = Read-TyprOwnership $root $owner
$fake.shortcuts = @([pscustomobject]@{ path = "$Sandbox\victim"; target = 'bad'; arguments = '' })
Reject { Assert-TyprShortcutReceipt $fake $root } 'forged shortcut receipt refused'

# Signature and confirmations: fully mocked download/UAC, no network/process launch.
function Get-AuthenticodeSignature { param($LiteralPath); return $script:signature }
$script:signature = [pscustomobject]@{ Status = 'Valid'; SignerCertificate = [pscustomobject]@{ Subject = 'CN=Docker Inc, O=Docker Inc, C=US' } }
Assert-TyprDockerSignature 'fake.exe'
$script:signature.Status = 'NotSigned'
Reject { Assert-TyprDockerSignature 'fake.exe' } 'unsigned Docker rejected'
$script:signature.Status = 'Valid'
$script:signature.SignerCertificate.Subject = 'CN=Docker Inc, O=Evil Docker Inc, C=US'
Reject { Assert-TyprDockerSignature 'fake.exe' } 'lookalike signer rejected'
$script:signature.SignerCertificate.Subject = 'CN=Docker Inc, O=Docker Inc, C=US'
function Get-Command { param($Name, $ErrorAction); return $null }
function Test-Path { param($LiteralPath, $PathType); if ($LiteralPath -like '*Docker Desktop.exe') { return $false }; Microsoft.PowerShell.Management\Test-Path -LiteralPath $LiteralPath }
$script:downloads = 0; $script:launches = 0; $script:answers = New-Object 'System.Collections.Generic.Queue[bool]'
function Confirm-Typr { param($Message); return $script:answers.Dequeue() }
function Start-Process { param($FilePath, $Verb, [switch]$Wait, [switch]$PassThru); $script:launches++ }
# Advanced switch binding required by -UseBasicParsing.
function Invoke-WebRequest { param([switch]$UseBasicParsing, $Uri, $OutFile); $script:downloads++; Save $OutFile 'mock download' }
$script:answers.Enqueue($false)
Reject { Install-TyprDockerDesktop } 'download declined'
Assert ($script:downloads -eq 0 -and $script:launches -eq 0) 'decline no side effects'
$script:answers.Enqueue($true); $script:answers.Enqueue($false)
Reject { Install-TyprDockerDesktop } 'separate UAC confirmation'
Assert ($script:downloads -eq 1 -and $script:launches -eq 0) 'download without launch'
$script:signature.Status = 'NotSigned'
$script:answers.Enqueue($true)
Reject { Install-TyprDockerDesktop } 'bad signature prevents UAC'
Assert ($script:launches -eq 0) 'no unverified launch'
$script:signature.Status = 'Valid'
$script:answers.Enqueue($true); $script:answers.Enqueue($true)
Reject { Install-TyprDockerDesktop } 'post-install rerun guidance exits'
Assert ($script:launches -eq 1) 'confirmed launch once'
Remove-Item Function:\Test-Path

# Every daemon call pins the local endpoint even if the ambient context changes.
$savedHost = $env:DOCKER_HOST
try {
    $env:DOCKER_HOST = 'tcp://remote:2375'
    Reject { Get-TyprDockerEndpoint } 'remote Docker refused'
    $env:DOCKER_HOST = ''
    function docker { $script:dockerArgs = @($args); $global:LASTEXITCODE = 0; return 'mock' }
    $null = Invoke-TyprDocker @('info')
    Assert ($script:dockerArgs[0] -eq '--host' -and $script:dockerArgs[1] -eq 'npipe:////./pipe/dockerDesktopLinuxEngine') 'explicit pinned endpoint'
    Remove-Item Function:\docker
    $bin = Join-Path $Sandbox 'native-bin'
    Save "$bin\docker.cmd" "@echo off`r`necho {`"ok`":true}`r`necho build progress 1>&2`r`nexit /b 0`r`n"
    $savedPath = $env:PATH
    try {
        $env:PATH = "$bin;$savedPath"
        $json = Invoke-TyprDocker @('info') | ConvertFrom-Json
        Assert $json.ok 'native stderr exit0 does not terminate or pollute JSON'
        Save "$bin\docker.cmd" "@echo off`r`necho failure 1>&2`r`nexit /b 1`r`n"
        Reject { Invoke-TyprDocker @('info') } 'native exit1 rejected'
        Assert ($null -eq (Invoke-TyprDocker @('info') -AllowFailure)) 'explicit native failure handling'
    } finally { $env:PATH = $savedPath }
} finally { $env:DOCKER_HOST = $savedHost }
$spec = Get-TyprSTTSpec 'GigaSTT' $owner
$run = @(Get-TyprRunArguments $spec)
Assert ($run -ccontains '127.0.0.1:9876:9876') 'loopback publish'
Assert ($run -ccontains 'never' -and $run -ccontains 'no') 'no implicit pull or autostart'
Assert ($run -ccontains 'GIGASTT_MODEL_VARIANT=rnnt') 'GigaSTT environment'
Reject { Assert-TyprLabels ([pscustomobject]@{ 'io.typr.owner' = 'foreign'; 'io.typr.windows' = '1'; 'io.typr.stt' = 'GigaSTT' }) $spec } 'foreign Docker ownership'
$labels = [pscustomobject]@{ 'io.typr.owner' = $owner; 'io.typr.windows' = '1'; 'io.typr.stt' = 'GigaSTT' }
$container = [pscustomobject]@{
    Config = [pscustomobject]@{ Labels = $labels; Image = $spec.image; Env = $spec.env; Cmd = $spec.command }
    Image = 'sha256:fixture'
    HostConfig = [pscustomobject]@{ NetworkMode = 'default'; RestartPolicy = [pscustomobject]@{ Name = 'no' }; Privileged = $false;
        Binds = @("$($spec.volume):$($spec.mount)"); PortBindings = [pscustomobject]@{ '9876/tcp' = @([pscustomobject]@{ HostIp = '127.0.0.1'; HostPort = '9876' }) } }
    Mounts = @([pscustomobject]@{ Type = 'volume'; Name = $spec.volume; Destination = $spec.mount; RW = $true })
    State = [pscustomobject]@{ Running = $true }
}
Assert-TyprContainer $container $spec 'sha256:fixture'
$container.HostConfig.PortBindings.'9876/tcp'[0].HostIp = '0.0.0.0'
Reject { Assert-TyprContainer $container $spec 'sha256:fixture' } 'all-interface binding refused'
$container.HostConfig.PortBindings.'9876/tcp'[0].HostIp = '127.0.0.1'
$container.Config.Cmd = @('foreign')
Reject { Assert-TyprContainer $container $spec 'sha256:fixture' } 'modified command refused'
$container.Config.Cmd = $spec.command
$container.HostConfig.RestartPolicy.Name = 'unless-stopped'
Reject { Assert-TyprContainer $container $spec 'sha256:fixture' } 'unapproved autostart refused'
$container.HostConfig.RestartPolicy.Name = 'no'
function Assert-TyprDocker { }
$script:mutations = @()
function Invoke-TyprDocker {
    param([string[]]$Arguments, [switch]$AllowFailure)
    if ($Arguments[0] -eq 'image') { return '{"Id":"sha256:fixture","Os":"linux","Architecture":"amd64","Config":null}' }
    $script:mutations += ($Arguments -join ' ')
    return 'fixture'
}
function Get-TyprDockerObject {
    param($Type, $Name)
    if ($Type -eq 'container') { return $container }
    return [pscustomobject]@{ Labels = $labels; Driver = 'local'; Options = $null }
}
function Test-TyprSTTReady { return $true }
function Confirm-Typr { throw 'No prompt for already-ready cached resources' }
Install-TyprSTT $spec -Check
Install-TyprSTT $spec
Assert ($script:mutations.Count -eq 0) 'cached ready resources never pulled/recreated'
$container.State.Running = $false
Reject { Install-TyprSTT $spec -Check } 'stopped container readiness nonzero'
$container.State.Running = $true
# Restore semantic readiness implementation, preserving mocked Docker functions.
$readyFunction = (Get-Item Function:\Test-TyprSTTReady).ScriptBlock
. "$Repository\scripts\windows\TyprInstaller.ps1"
Reject { Get-TyprLoopbackJson 'http://example.com/ready' } 'non-loopback readiness refused'
function Get-TyprLoopbackJson { param($Uri); return $script:health }
$script:health = [pscustomobject]@{ ready = $true; default_model = 'parakeet-tdt-0.6b-v3'; loaded = @('parakeet-tdt-0.6b-v3'); models = @('parakeet-tdt-0.6b-v3'); runtime = [pscustomobject]@{ 'parakeet-tdt-0.6b-v3' = [pscustomobject]@{ backend = 'cpu'; encoder_precision = 'int8' } } }
$parakeet = Get-TyprSTTSpec 'Parakeet' $owner
Assert (Test-TyprSTTReady $parakeet) 'semantic readiness'
$script:health.runtime.'parakeet-tdt-0.6b-v3'.backend = 'cuda'
Assert (-not (Test-TyprSTTReady $parakeet)) 'GPU backend rejected'
Reject { Wait-TyprSTT $parakeet -TimeoutSeconds 0 } 'bounded readiness timeout'

# Full mocked install/check paths: Check must not prompt, lock, copy or configure.
function Assert-TyprPlatform { }
function Get-TyprOwner { return $owner }
function Assert-TyprNotRunning { }
function Get-TyprShellFolder([string]$Name) { return (Join-Path $Sandbox $Name) }
$savedLocal = $env:LOCALAPPDATA
$env:LOCALAPPDATA = $Sandbox
function Confirm-Typr { throw 'Unexpected prompt during read-only Check' }
function Set-TyprShortcuts { throw 'Unexpected shortcut mutation' }
Invoke-TyprInstaller -Payload $payload -Check -STT Skip
$before = [IO.File]::ReadAllText("$root\ownership.json")
Assert ($before -eq $receipt) 'Check did not write receipt'
Save "$Sandbox\Typr\config.json" 'secret fixture preserved'
Save "$Sandbox\Typr\history.json" 'history preserved'
function Confirm-Typr { return $true }
Invoke-TyprInstaller -Payload $payload -Uninstall
Assert (-not (Test-Path -LiteralPath $root)) 'owned application removed'
Assert ([IO.File]::ReadAllText("$Sandbox\Typr\config.json") -eq 'secret fixture preserved') 'config preserved'
Assert (Test-Path -LiteralPath "$Sandbox\Typr\history.json") 'history preserved'
$env:LOCALAPPDATA = $savedLocal
Write-Host 'ALL MOCKED INSTALLER TESTS PASSED'
