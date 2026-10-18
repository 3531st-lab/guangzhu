# 源码版 AGH 接入

适用于光筑公开源码和 AGH 固定版本 `5da40731214976ad8aff982cd5626d3a676fdd88`。只做离线计算或账本核验可跳过本页。运行包的来源和限制见 [DEPENDENCIES.md](DEPENDENCIES.md)。

## 1. 准备运行目录和配置

先完成 [源码环境安装](REPRODUCING.md)，再按 [配置说明](CONFIGURATION.md) 创建 `desktop/settings.json`。

可使用公开光筑安装器带的运行目录：安装 [v0.2.0](https://github.com/3531st-lab/guangzhu/releases/tag/v0.2.0) 后，`agh_runtime` 指向本机 `%LOCALAPPDATA%/Programs/guangzhu/runtime/agh/agnes-win32-x64.exe` 的展开路径。源码实例使用单独的 `.guangzhu-agh`，不要借用安装版保存账号的实例目录。完整 AGH 目录中的 `runtime`、`web`、`native`、`daemon` 等文件必须一起保留。

在仓库根目录的 PowerShell 执行下面的变量设置；后续另开终端时也要执行这一段：

```powershell
$ErrorActionPreference = 'Stop'
$taskRoot = (Get-Location).Path
$taskConfig = Get-Content desktop/settings.json -Raw -Encoding UTF8 | ConvertFrom-Json
$aghEntry = $taskConfig.agh_runtime
$env:AGH_HOME = $taskConfig.agh_home
$taskProfile = 'local-dev'
$taskPython = (Resolve-Path '.venv/Scripts/python.exe').Path
if (-not (Test-Path -LiteralPath $aghEntry -PathType Leaf)) { throw 'AGH executable not found' }
```

## 2. 启动专用实例

首次创建实例目录时，已有的 `private_home` 函数会仅为新目录设置当前用户的访问权限。不要将 `agh_home` 指向一个存放其他项目数据的目录。

```powershell
& $taskPython -c "from guangzhu.agh_process import private_home; import sys; private_home(sys.argv[1])" $env:AGH_HOME
if ($LASTEXITCODE -ne 0) { throw 'AGH home preparation failed' }
$env:AGNES_WEB_ORIGIN = 'http://127.0.0.1:4177'
& $aghEntry serve --profile $taskProfile --cwd $taskRoot --port 4177
```

保留这个终端，打开 `http://127.0.0.1:4177/`。如果该端口已被其他 AGH 实例占用，先关闭相应实例，不能把不同实例的工具、插件与凭据混用。

## 3. 注册当前的 12 个 MCP 工具

另开 PowerShell，进入同一个仓库，重新执行第 1 节变量设置。新实例使用：

```powershell
$taskTools = @('gz_project_summary', 'gz_set_requirements', 'gz_fetch_weather',
    'gz_generate_layout', 'gz_analyze', 'gz_edit_design', 'gz_compare_options',
    'gz_crosscheck_yield', 'gz_record_review', 'gz_export', 'gz_new_project', 'gz_wait')
$taskArgs = @('mcp', 'add', 'guangzhu', '--profile', $taskProfile,
    '--name', '光筑', '--stdio', $taskPython, '--arg', '-m', '--arg', 'guangzhu.mcp_server')
foreach ($taskTool in $taskTools) { $taskArgs += @('--allow-tool', $taskTool) }
& $aghEntry @taskArgs
if ($LASTEXITCODE -ne 0) { throw 'MCP registration failed; inspect existing definition' }

function Read-GzRevision {
    $taskGet = & $aghEntry mcp get guangzhu --profile $taskProfile
    if ($LASTEXITCODE -ne 0) { throw 'MCP get failed' }
    $taskGet | Write-Host
    $taskMatch = [regex]::Match(($taskGet -join "`n"), '(?m)^guangzhu revision=(\S+) ')
    if (-not $taskMatch.Success) { throw 'No revision; inspect get output' }
    return $taskMatch.Groups[1].Value
}
$taskRevision = Read-GzRevision
```

检查输出中的 Python 路径、启动参数和工具清单后，依次信任并启用；每次写入前重新读取 revision：

```powershell
& $aghEntry mcp trust guangzhu trusted --profile $taskProfile --expected-revision $taskRevision
if ($LASTEXITCODE -ne 0) { throw 'MCP trust failed' }
$taskRevision = Read-GzRevision
& $aghEntry mcp enable guangzhu --profile $taskProfile --expected-revision $taskRevision
if ($LASTEXITCODE -ne 0) { throw 'MCP enable failed' }
& $aghEntry mcp status guangzhu --profile $taskProfile
& $aghEntry mcp tools guangzhu --profile $taskProfile
```

成功标准是 `trusted`、`enabled`、`ready`，并能看到全部 12 个工具。已有 `guangzhu` 服务时，不要再次 add：使用官方 MCP 管理界面按“停用 → 修改定义 → 审核并信任 → 启用 → 重连”更新同一服务。stdio 进程必须使用本仓库已安装的 Python，不依赖外部环境变量传递密钥。

## 4. 构建并安装光筑插件

安装 Node.js（本项目核验使用 Node.js 24），然后：

```powershell
npm --prefix agh-plugin/guangzhu-studio ci
.\.venv\Scripts\python.exe scripts/build_agh_plugin.py --check --release
```

这会核对已提交的生成文件，输出 `Package source: file:./dist/agh-plugin/guangzhu-studio-<版本>-<摘要>`。默认工具前缀为 `mcp_guangzhu_df14eb73_`；若 AGH 中实际完整工具名的前缀不同，先用 `--tool-prefix <实际前缀>` 构建，再用相同参数执行 `--check --release`。不要把占位符原样复制到命令中。

在 AGH 网页“设置 → 插件管理”中，以**本次输出的完整 file 地址**检查包，确认 `id=guangzhu-studio`、`blockers` 为空；首次安装选安装，已有同 ID 选更新，然后信任本次权限并启用。源地址相对第 2 节 `--cwd` 指定的仓库根目录解析。包只申请界面和插槽能力。确认 `trusted=true`、`actual=running`，再选择“光筑”皮肤。

若需要脚本化管理，固定版支持 `/admin/plugins/api/` 的 `inspect`、`install` / `update`、`trust`、`enable` 和 `operation/get`：每次写操作携带页面 `context` 返回的 `profile`、`clientId` 及新 `commandId`；安装传入本次 `preview.integrity`，信任传入同次 `capabilityHash`；等待操作到 `completed`。具体接口以 [固定版官方实现](https://github.com/AgnesAI-Labs/agnes-harness/blob/5da40731214976ad8aff982cd5626d3a676fdd88/packages/web/src/admin/plugins/api.ts) 为准，不使用不存在的 `package update` CLI。

## 5. 模型、Skill 与新设计

1. 在 AGH 设置或光筑首页填写自己的模型 key，验证连接；不要写入源码、配置模板或截图。
2. 在 AGH 的工作区 / Skill 管理中选本仓库，刷新并启用 `.agh/skills/pv-rooftop-design/SKILL.md`。
3. 在仓库根目录运行 `start.cmd`。已有正确的 AGH 实例时，桌面会复用本机 4177 服务。
4. 选 `changzhou-demo`、填写需求并开始设计。会话权限用“工作区内修改”，审批采用人工模式；设计工具按需“本会话允许”，每次导出只点“仅允许这次”。
5. 完成后检查版本、最终分析、导出文件与独立审核；一次会话结束本身不代表成功。新的模型运行受服务可用性和随机性影响，不保证复现历史成功率。

保存与核验时使用桌面运行页的执行记录导出入口，它读取 `desktop/settings.json`。手动脚本 `agh_export_run.py` 保留历史默认运行包路径，当前 CLI 不提供覆盖该路径的参数，因此新电脑应使用桌面导出入口；不要照抄开发者旧目录，也不要改写已有账本。记录默认脱敏，不使用 `--raw`。离线核验的准确命令见 [REPRODUCING.md](REPRODUCING.md)。
