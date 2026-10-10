param(
    [string]$Python = "$env:LOCALAPPDATA/Programs/Python/Python312/python.exe",
    [string]$ISCC = "$env:LOCALAPPDATA/Programs/Inno Setup 6/ISCC.exe",
    [string]$AghArchive = "$PSScriptRoot/../../竞赛/work/agh-runtime-official/agnes-win32-x64-5da4073.zip",
    [string]$AghSource = "$PSScriptRoot/../../竞赛/work/agnes-harness",
    [switch]$NoCompilerInstall
)
$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$env:PIP_NO_CACHE_DIR = '1'
$env:PIP_EXTRA_INDEX_URL = ''
[Console]::OutputEncoding = [Text.UTF8Encoding]::new()
$started = [Diagnostics.Stopwatch]::StartNew()
$root = Split-Path -Parent $PSScriptRoot
$cache = Join-Path $root 'build/installer-cache'
$stage = Join-Path $root ('build/光筑-' + [guid]::NewGuid().ToString('N'))
$manifest = [ordered]@{ sources = @(); wheels = @() }
function Run([string]$Program, [string[]]$Arguments) {
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed: exit $LASTEXITCODE" }
}
function RemoveStageDirectory([string]$Path) {
    $stageRoot = (Get-Item -LiteralPath $stage).FullName
    $target = Get-Item -LiteralPath $Path
    if (-not $target.FullName.StartsWith($stageRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Deletion target escaped staging'
    }
    for ($entry = $target; $entry.FullName -ne $stageRoot; $entry = $entry.Parent) {
        if ($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw 'Reparse path in deletion target'
        }
    }
    $links = Get-ChildItem -LiteralPath $target.FullName -Recurse -Force |
        Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }
    if ($links) {
        throw 'Reparse entry inside deletion target'
    }
    Remove-Item -LiteralPath $target.FullName -Recurse -Force
}
function Download([string]$Url, [string]$Name) {
    $file = Join-Path $cache $Name
    if (-not (Test-Path -LiteralPath $file) -or (Get-Item $file).Length -eq 0) {
        Invoke-WebRequest $Url -OutFile $file -TimeoutSec 120
    }
    $manifest.sources += @{ url = $Url; sha256 = (Get-FileHash $file -Algorithm SHA256).Hash }
    return $file
}
function Signed([string]$File, [string]$Publisher) {
    $signature = Get-AuthenticodeSignature -LiteralPath $File
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notlike "*CN=$Publisher,*") {
        throw "Invalid publisher signature: $File ($($signature.Status))"
    }
}
Run $Python @('-c', "assert __import__('sys').version_info[:2] == (3,12) and __import__('sys').maxsize > 2**32")
if ((Get-FileHash -LiteralPath $AghArchive).Hash -ne 'FFB6DE31E409098459847F67DB1A68D1FB3B23F8893ADF9F489BFD1B03284AED') {
    throw 'Official AGH archive hash mismatch'
}
$revision = & git -C $AghSource rev-parse HEAD
if ($LASTEXITCODE -ne 0 -or $revision -ne '5da40731214976ad8aff982cd5626d3a676fdd88') { throw 'AGH license revision mismatch' }
Run 'git' @('-C', $AghSource, 'diff', '--exit-code', 'HEAD', '--', 'LICENSE', 'NOTICE')
New-Item -ItemType Directory -Force -Path $cache,$stage | Out-Null
$zip = Download 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip' 'python-3.12.10-embed-amd64.zip'
if ((Get-FileHash $zip -Algorithm MD5).Hash -ne 'FE8EF205F2E9C3BA44D0CF9954E1ABD3') { throw 'Python published digest mismatch' }
$inno = Download 'https://github.com/jrsoftware/issrc/releases/download/is-6_7_3/innosetup-6.7.3.exe' 'innosetup-6.7.3.exe'
Signed $inno 'Pyrsys B.V.'
if (-not (Test-Path -LiteralPath $ISCC)) {
    if ($NoCompilerInstall) {
        throw 'Compiler not found; automatic compiler installation is disabled'
    }
    $toolDir = Join-Path $cache 'Inno Setup 6'
    $arguments = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/CURRENTUSER', "/DIR=`"$toolDir`"")
    $process = Start-Process $inno -ArgumentList $arguments -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw "Inno bootstrap failed: $($process.ExitCode)" }
    $ISCC = Join-Path $toolDir 'ISCC.exe'
}
Signed $ISCC 'Pyrsys B.V.'
$compilerInfo = @'
[Setup]
AppName=Guangzhu compiler probe
AppVersion=1
DefaultDirName={localappdata}\Programs\guangzhu-build-probe
PrivilegesRequired=lowest
Uninstallable=no
'@ | & $ISCC '/O-' '-'
if ($LASTEXITCODE -ne 0) { throw 'Compiler version probe failed' }
$engine = [regex]::Match(($compilerInfo -join "`n"), 'Compiler engine version: Inno Setup (6\.\d+\.\d+)')
if (-not $engine.Success) { throw 'Inno Setup 6 compiler required' }
$manifest.compiler = @{ version = $engine.Groups[1].Value; sha256 = (Get-FileHash $ISCC).Hash }
Expand-Archive -LiteralPath $zip -DestinationPath (Join-Path $stage 'runtime/python')
Signed (Join-Path $stage 'runtime/python/python.exe') 'Python Software Foundation'
Expand-Archive -LiteralPath $AghArchive -DestinationPath (Join-Path $stage 'runtime/agh')
$distribution = Join-Path $stage 'runtime/agh/agnes-win32-x64.tar.gz'
Run 'tar.exe' @('-xf', $distribution, '-C', (Join-Path $stage 'runtime/agh'))
Remove-Item -LiteralPath $distribution
foreach ($name in @('LICENSE','NOTICE')) {
    Copy-Item -LiteralPath (Join-Path $AghSource $name) -Destination (Join-Path $stage "runtime/agh/$name")
    $manifest.sources += @{ url = "https://github.com/AgnesAI-Labs/agnes-harness/blob/$revision/$name";
        sha256 = (Get-FileHash -LiteralPath (Join-Path $AghSource $name)).Hash }
}
$manifest.sources += @{ input = 'user-provided official agnes-win32-x64-5da4073.zip';
    url = "https://github.com/AgnesAI-Labs/agnes-harness/tree/$revision"; sha256 = (Get-FileHash $AghArchive).Hash }
$wheelhouse = Join-Path $cache ('wheels-' + [guid]::NewGuid().ToString('N'))
Run $Python @('-m','pip','wheel','--no-cache-dir','--verbose','--index-url','https://pypi.org/simple','--no-deps',
    '-r',"$root/requirements.lock.txt",'-w',$wheelhouse)
$site = Join-Path $stage 'runtime/python/Lib/site-packages'
Run $Python @('-m','pip','install','--no-index','--no-deps','--no-compile','--find-links',$wheelhouse,
    '--target',$site,'-r',"$root/requirements.lock.txt")
foreach ($wheel in Get-ChildItem -LiteralPath $wheelhouse -Filter '*.whl') {
    $manifest.wheels += @{ file = $wheel.Name; sha256 = (Get-FileHash $wheel.FullName).Hash; index = 'https://pypi.org/simple' }
}
@('python312.zip','.', 'Lib/site-packages','../../backend','../..','import site') |
    Set-Content -LiteralPath (Join-Path $stage 'runtime/python/python312._pth') -Encoding ascii
@'
import os
from pathlib import Path
import site
directory = Path(__file__).parent / "Lib/site-packages"
site.addsitedir(str(directory))
_dll_handles = [os.add_dll_directory(str(directory / "pywin32_system32"))]
'@ | Set-Content -LiteralPath (Join-Path $stage 'runtime/python/sitecustomize.py') -Encoding utf8
foreach ($relative in @('backend/guangzhu','desktop','data/catalog','data/demo','data/roofs','.agh/skills')) {
    $destination = Join-Path $stage $relative
    New-Item -ItemType Directory -Force -Path (Split-Path $destination) | Out-Null
    Copy-Item -LiteralPath (Join-Path $root $relative) -Destination $destination -Recurse
}
New-Item -ItemType Directory -Path (Join-Path $stage 'scripts'),(Join-Path $stage 'projects'),(Join-Path $stage 'runs'),(Join-Path $stage 'data/showcase') | Out-Null
# Codex review E1: one real, fully verified run ships with the app so it can be looked through before any key is set
Copy-Item -LiteralPath (Join-Path $root 'runs/gz-changzhou-demo-1008-2113') -Destination (Join-Path $stage 'data/showcase/gz-changzhou-demo-1008-2113') -Recurse
foreach ($name in @('agh_export_run.py','agh_verify_run.py','check_secrets.py')) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination (Join-Path $stage 'scripts')
}
foreach ($directory in Get-ChildItem -LiteralPath $stage -Recurse -Directory -Filter '__pycache__') {
    RemoveStageDirectory $directory.FullName
}
Remove-Item -LiteralPath (Join-Path $stage 'desktop/start.cmd')
RemoveStageDirectory (Join-Path $stage 'desktop/launcher')
# 光筑.exe：用 Windows 自带的 C# 编译器生成，图标和名字都是光筑自己的。
$csc = Join-Path $env:WINDIR 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
$icon = Join-Path $root 'desktop\web\assets\guangzhu.ico'
$launcher = Join-Path $root 'desktop\launcher\launcher.cs'
Run $csc @('-nologo','-target:winexe','-codepage:65001',"-win32icon:$icon","-out:$(Join-Path $stage '光筑.exe')",$launcher)
Run 'npm.cmd' @('--prefix',"$root/agh-plugin/guangzhu-studio",'ci','--ignore-scripts','--registry=https://registry.npmjs.org')
$manifest.plugin = @{ lock_sha256 = (Get-FileHash "$root/agh-plugin/guangzhu-studio/package-lock.json").Hash }
$release = & (Join-Path $stage 'runtime/python/python.exe') -B "$PSScriptRoot/build_agh_plugin.py" --check --release
if ($LASTEXITCODE -ne 0) { throw 'Plugin release failed' }
$snapshot = ($release | Where-Object { $_ -like 'Package source: file:./*' }) -replace '^Package source: file:\./',''
New-Item -ItemType Directory -Path (Join-Path $stage 'plugins') | Out-Null
Copy-Item -LiteralPath (Join-Path $root $snapshot) -Destination (Join-Path $stage 'plugins') -Recurse
$manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $stage 'build-manifest.json') -Encoding utf8
Run $Python @("$PSScriptRoot/installer_stage.py", $stage, '--host-python', $Python, '--developer-root', $root, '--clean')
$probe = @'
import json, os, subprocess, sys
allowed = "APPDATA HOMEDRIVE HOMEPATH LOCALAPPDATA PATH PROCESSOR_ARCHITECTURE SYSTEMDRIVE SYSTEMROOT TEMP USERNAME USERPROFILE PROGRAMFILES".split()
code = """import win32api, clr, webview, PySAM, guangzhu
from guangzhu import api
from guangzhu.selfcheck import offline_analysis, selfcheck
import json
checks = selfcheck()
assert checks["passed"], checks["failures"]
r = offline_analysis()
print(json.dumps(r, ensure_ascii=True))
raise SystemExit(0 if r['passed'] else 1)
"""
subprocess.run([sys.argv[1], "-B", "-c", code], cwd=os.environ["TEMP"], env={k:os.environ[k] for k in allowed}, check=True)
'@
# Windows PowerShell 5.1 strips embedded double quotes from native arguments, so the probe runs from a file.
$probeFile = Join-Path $cache 'installed-probe.py'
Set-Content -LiteralPath $probeFile -Value $probe -Encoding utf8
Run $Python @($probeFile,(Join-Path $stage 'runtime/python/python.exe'))
Run $ISCC @("/DStage=$stage", "/DOutput=$root/dist", "$root/installer/guangzhu.iss")
Run $Python @("$PSScriptRoot/installer_size.py", (Join-Path $root 'dist/guangzhu-setup.exe'))
$installer = Get-Item -LiteralPath (Join-Path $root 'dist/guangzhu-setup.exe')
Write-Output "Stage: $stage"
Write-Output "Installer: $($installer.FullName); bytes: $($installer.Length); SHA256: $((Get-FileHash $installer.FullName).Hash)"
Write-Output "Elapsed seconds: $([math]::Round($started.Elapsed.TotalSeconds,2))"
