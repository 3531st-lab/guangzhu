param([string]$Python = '')
$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [Console]::OutputEncoding
$taskRoot = Split-Path -Parent $PSScriptRoot
if (-not $Python) {
    $Python = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
}
if (-not (Test-Path -LiteralPath $Python)) { throw '找不到 Python 3.12，请使用 -Python 指定解释器。' }
& $Python -c "import sys; assert sys.version_info[:2] == (3, 12), 'Python 3.12 required'"
if ($LASTEXITCODE -ne 0) { throw '解释器版本检查失败' }
$taskVenv = Join-Path $taskRoot '.venv'
if (-not (Test-Path -LiteralPath (Join-Path $taskVenv 'Scripts\python.exe'))) {
    & $Python -m venv $taskVenv
    if ($LASTEXITCODE -ne 0) { throw '创建虚拟环境失败' }
}
$taskPython = Join-Path $taskVenv 'Scripts\python.exe'
& $taskPython -m pip install -r (Join-Path $taskRoot 'requirements-dev.txt')
if ($LASTEXITCODE -ne 0) { throw '安装锁定依赖失败' }
& $taskPython -m pip install --no-deps --no-build-isolation -e $taskRoot
if ($LASTEXITCODE -ne 0) { throw '安装光筑包失败' }
& $taskPython -m guangzhu.selfcheck
if ($LASTEXITCODE -ne 0) { throw '自检失败' }
