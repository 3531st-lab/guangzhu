# 外部依赖的获取、接口与替代路径

光筑原创计算、界面、插件、MCP 工具和设计 Skill 均在本仓库。依赖的服务、账号和系统组件不随源码提供；离线计算与已归档执行记录的核验不需要模型账号。

| 依赖 / 未随源码提供的内容 | 获取与版本 | 接口要求 / 替代复现方式 |
| --- | --- | --- |
| Python 及计算库 | Windows x64 Python 3.12，建议 3.12.10；`scripts/setup.ps1` 安装锁定依赖 | 首次安装需联网。之后按 [REPRODUCING.md](REPRODUCING.md) 使用仓库天气和合成屋顶离线计算 |
| AGH 官方 Windows 运行目录 | 已验证源码提交 `5da40731214976ad8aff982cd5626d3a676fdd88`；本项目 [v0.2.0 Release](https://github.com/3531st-lab/guangzhu/releases/tag/v0.2.0) 的安装器内含当时的完整官方运行目录 | 安装后可复用其 `runtime/agh/`，另设源码版 `AGH_HOME`。必须保留整个目录，不能单拷 exe。见 [AGH 接入](AGH_SETUP.md) |
| 用于重建旧安装包的原始 AGH ZIP | 构建脚本接受 `-AghArchive`；原文件名 `agnes-win32-x64-5da4073.zip`，SHA256 `FFB6DE31E409098459847F67DB1A68D1FB3B23F8893ADF9F489BFD1B03284AED` | 原始 ZIP 来自比赛提供的官方运行包；需要该版本时向赛事组织方取得。这里没有声称存在公开的同字节 ZIP 下载地址。缺少它时可运行源码或现有公开安装包，但不能声称重建出同一安装器 |
| AGH 源码 | [固定提交](https://github.com/AgnesAI-Labs/agnes-harness/tree/5da40731214976ad8aff982cd5626d3a676fdd88)、[该版本官方安装文档](https://github.com/AgnesAI-Labs/agnes-harness/blob/5da40731214976ad8aff982cd5626d3a676fdd88/docs/guide/install.zh-CN.md) | 源码构建使用 Node.js 24.10+、pnpm 10.34.5 及平台原生工具；输出的 Node 入口不等同于本项目要求的 Windows exe。若自行适配，须重新验证官方插件 SDK、MCP stdio、原生审批、`export --format agnes` 和管理 API，不能仅改路径就假定兼容 |
| DeepSeek / Agnes 等模型 | 用户从相应服务商取得账号与 API 使用权限，只在 AGH / 光筑的模型设置页填写 key | 所有模型调用均经 AGH。模型不可用时，用已存档账本核验闭环和审核，用离线计算核验数值；不能把回放说成新模型运行。新运行可能产生服务商费用 |
| Microsoft Edge / WebView2 | [WebView2 官方下载](https://developer.microsoft.com/microsoft-edge/webview2/)，安装当前 Windows 对应运行时 | 桌面窗口用 WebView2，PDF 导出与浏览器测试用系统 Edge。纯计算、MCP 冒烟和 JSON 结果检查不依赖桌面窗口 |
| npm 构建工具 | 插件和 `scripts/agh_schema_check/` 各自执行 `npm ci`，版本与完整性见各自 lockfile | 插件源码已公开；React、`react/jsx-runtime`、Ant Design 由 AGH 宿主提供，不打包为第二份 React |
| NASA POWER / PVGIS 在线接口 | 官方公开 API；请求参数、年份和数据许可见 [sources.md](sources.md) | 仓库中的全年快照可做离线演示。新的地点或年份需要在线数据；接口不可达时如实报告，不伪造天气 |
| PVDAQ 全年原始观测 CSV | `python scripts/compare_plant.py --download` 从官方公开源获取，缓存到 `data/cache/plant/` | 元数据和月度汇总已提供；清洗与筛选方法见 [数据说明](../data/field/plant/README.md)。重新计算依赖上游数据仍可访问 |
| 厂家规格书、标准文本、真实用户图纸 | 通过 [来源登记](sources.md) 中官方链接或权利人授权获取 | 仅保留实现所需参数、来源与规则说明，不重新分发受限全文；用 `samples/sample-drawing/`、`data/demo/projects/` 的原创示例替代私人图纸 |
| 2026-10-03 完整评测及内部过程归档 | 公共仓库含用例、驱动、评分代码及一组完整真实运行；并未上传全部历史运行、截图和内部报告 | 可核验公开常州案例或重新跑测试。51/54 等历史汇总不能从这一组案例独立重算；完整归档须经权利与脱敏复核后提供。涉及缺失归档的历史测试会明确 skip，不能算作通过 |

项目源码采用 MIT；以上组件和数据各按其自身条款使用，详见 [第三方声明](../THIRD_PARTY_NOTICES.md)。
