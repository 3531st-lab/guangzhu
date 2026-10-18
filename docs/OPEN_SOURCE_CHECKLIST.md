# 开源要求核对

核对日期：2026-10-17（America/Los_Angeles）。依据用户提供的比赛规则截图“十二、获奖代码库开源”。检查对象是 [3531st-lab/guangzhu](https://github.com/3531st-lab/guangzhu) 的公开仓库；本次从公开 `main` 的 `243ebad` 克隆后补充，未把开发目录或内部过程归档整包上传。

## 规则逐项对应

| 要求 | 状态与证据 |
| --- | --- |
| 包含团队原创代码 | 已提供计算后端、桌面界面、AGH 插件源码、设计 Skill、安装器及验证脚本。与本地开发版本比对，`backend/`、`desktop/`、`.agh/` 的已跟踪文件无遗漏、内容一致；插件实现也齐全，公开测试对缺失历史归档的处理有差异 |
| 配置模板 | 已补 [desktop/settings.example.json](../desktop/settings.example.json) 和 [配置说明](CONFIGURATION.md)，与 `api.settings()` 实际读取字段一致；不含凭据 |
| README、安装或运行方法 | 已补 [README](../README.md) 中克隆、安装、配置入口，补充 [AGH 接入](AGH_SETUP.md) 的运行包、实例、12 工具、插件、Skill 和模型步骤 |
| 项目复现说明 | 已补 [REPRODUCING.md](REPRODUCING.md)：离线计算、太阳位置对照、原生账本与独立审核核验、测试及新设计分别说明输入、命令和成功标准 |
| 第三方依赖说明 | [requirements.lock.txt](../requirements.lock.txt)、[requirements-dev.txt](../requirements-dev.txt)、npm lockfile、[来源登记](sources.md) 与新增 [第三方声明](../THIRD_PARTY_NOTICES.md) 共同记录版本、用途、来源及许可 |
| 适用的开源许可证 | 原插件已声明 MIT，本次补全根目录 [LICENSE](../LICENSE)、Python 项目元数据和插件随包许可；第三方软件与数据保留各自条款；后续安装器构建也复制根许可与第三方声明 |
| 不公开密码、个人信息、受限数据和闭源组件 | 当前文本密钥扫描通过；补查历史文本中的凭据前缀、公开 PDF/XLSX 的文本和元数据，匹配的历史测试样例为脱敏测试用假值。已补 `.env*`、本机设置、私钥、AGH 实例和新运行目录的忽略规则；没有加入私人图纸或模型 key |
| 无法随源码提供的依赖说明获取方式、接口或替代复现方案 | 已补 [DEPENDENCIES.md](DEPENDENCIES.md)：AGH 固定版本、原始 ZIP 的渠道和摘要、公开安装包内的运行目录、模型账号、WebView2、在线数据、受限规格书与历史归档的边界；提供无需模型的替代核验路径 |
| 赛果公布后 5 个工作日内公开 | GitHub 元数据确认仓库当前为 public；未提供正式赛果公布日期，不能据此判断是否满足截止时间。应保存正式公告及首次公开时间凭据 |

## 本次验证

验证在新克隆和独立 `.venv` 中进行；Windows x64、Python 3.12.10、Node.js 24.16.0。

| 检查 | 实测结果 |
| --- | --- |
| `scripts/setup.ps1` | 首次下载遇到 PyPI 读取超时；设置 `PIP_DEFAULT_TIMEOUT=120` 后复用下载缓存重试，依赖安装、editable 包安装、原生加载自检全部通过，退出码 0 |
| `python -m pip check` | `No broken requirements found`；安装元数据包含 `License-Expression: MIT` 和 `License-File: LICENSE` |
| `offline_analysis()` | `passed=true`、`failures=[]`；P50 年发电量 247624.1986 kWh，PySAM 原生计算返回正值，临时项目已清理 |
| `scripts/check_official_sun.py` | 离线对照：太阳位置 29/29、USNO 日出日落 12/12、天气网录样 13/13；退出码 0 |
| 公开常州案例原生账本 + 独立审核 | 任务规划、能力调用、反馈处理、结果验证全部通过；独立审核证据齐全，退出码 0 |
| Python 回归子集（下面 9 个文件） | **239 passed，0 failed**；验证依赖加载、仓库检查、发布包许可、桌面入口、原生运行库、MCP 与太阳位置；未将本次子集结果称为全量测试 |
| 三组 JavaScript 测试 | **254 passed，29 skipped，0 failed**；跳过的是公共仓库不含的历史归档用例 |
| `scripts/build_agh_plugin.py --check --release` | `Plugin artifacts match`；生成的发布包含原字体许可、OSM 声明与新增项目 MIT 许可 |
| 密钥与资料检查 | `scripts/check_secrets.py` 通过；补查 622 个历史文本 blob，2 处凭据前缀匹配经上下文确认是测试假值；4 个公开 PDF/XLSX 的文本与元数据未命中检查的凭据、联系方式标签或用户目录模式 |
| 文档与分发检查 | 新增配置 JSON、Python 许可元数据、PowerShell 命令块及安装器语法通过；文档本地链接无缺失；4 个 three.js 来源清单文件的 SHA256 一致 |
| `scripts/loc.py` | 公开仓库非空源码 21858 行（含注释，不含测试和生成文件）；本次生产脚本增加 3 行，用于后续安装包保留许可证 |

Python 子集的实际命令（仓库根目录）：

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest -q tests/test_smoke.py tests/test_repository_checks.py `
    tests/test_installer_stage.py tests/test_agh_plugin_data.py tests/test_native_runtime.py `
    tests/test_mcp_server.py tests/test_mcp_smoke.py tests/test_official_sun.py tests/test_desktop_app.py
```

其余命令见 [复现指南](REPRODUCING.md)。本次修改了原插件发布测试中“只能有两份 txt 许可证”的过时断言，改为逐份核验字体许可及项目许可内容；随后上述 239 项重新通过。

## 复现边界

- 公开真实案例可从原生账本重验，但本仓库没有 2026-10-03 全部历史评测归档；不能从单个案例独立重算 51/54 的历史成绩。测试的 skip 单独统计。
- 新自动设计需要用户配置可用模型；本次开源补充不把离线回放或计算测试记为一次新模型实跑。
- 原始 AGH ZIP 未包含在源码中，安装器构建有明确外部输入；本次不替换已发布的 v0.2.0 安装器，不声称重新构建了同一个二进制。
- 自动扫描不是对任意私人信息的保证。今后追加截图、录音、视频、图纸或原生运行记录时，仍需逐件检查；`.gitignore` 不会删除 Git 历史中的已提交内容。
