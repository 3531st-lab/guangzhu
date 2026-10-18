# 第三方软件与数据声明

光筑团队原创的源码、文档、图标和合成示例采用根目录 [MIT License](LICENSE)。本项目的 MIT 许可不改变第三方软件、字体、数据库、公开观测数据或服务的许可，也不授予第三方商标权。插件发布包在 `licenses/LICENSE-guangzhu.txt` 中附带同一份项目许可。

## 随仓库提供的第三方内容

| 内容 | 许可及署名 | 本地声明 / 来源 |
| --- | --- | --- |
| three.js r128、OrbitControls（含压缩版本） | MIT；保留 three.js authors 的版权声明 | [LICENSE-three.txt](desktop/web/vendor/LICENSE-three.txt)、[固定版本、哈希与变换记录](desktop/web/vendor/SOURCES.json) |
| IBM Plex Mono | SIL OFL 1.1，保留原版权和 Reserved Font Name | [字体许可](desktop/web/vendor/licenses/LICENSE-IBM-Plex.txt)；插件 `licenses/` 中也有原文 |
| Noto Serif SC「光筑」子集 | SIL OFL 1.1 | [字体许可](desktop/web/vendor/licenses/LICENSE-Noto-Serif-SC.txt)；子集来源见 [sources.md](docs/sources.md) |
| OpenStreetMap 厂房轮廓、城市坐标及其派生展示数据 | © OpenStreetMap contributors，ODbL 1.0 | [OSM 声明](data/roofs/LICENSE-OSM.md)、[取数与示意字段说明](data/roofs/README.md)；适用于 `data/roofs/` 中 OSM 派生部分、`desktop/web/cities.json` 及插件内相应派生数据 |
| NREL SAM CEC 组件、逆变器库子集 | BSD-3-Clause；保留上游版权 | [LICENSE-SAM.txt](data/catalog/LICENSE-SAM.txt)、[PROVENANCE.md](data/catalog/PROVENANCE.md) |
| NASA POWER 天气及接口录样 | CC BY 4.0；署名 NASA POWER Project | `data/demo/weather/`、相关测试录样；[许可、接口与引用登记](docs/sources.md) |
| European Commission JRC / PVGIS 天气、发电计算结果 | 遵循 JRC PVGIS 使用条件，署名 JRC / PVGIS 及数据库 | `data/demo/weather/`、`data/demo/yields/`、相关测试录样；[使用条件](https://joint-research-centre.ec.europa.eu/photovoltaic-geographical-information-system-pvgis/general-information/usage-conditions-data-protection_en) |
| PVDAQ 2107 电站元数据及月度衍生汇总 | CC BY 4.0；Deline 等（2021），DOI 10.25984/1846021 | [数据选择、署名与清洗说明](data/field/plant/README.md)；原始全年文件按需从官方源获取 |
| USNO / 中国天气网太阳位置、日出日落录样 | 保留数据来源与访问说明；不以本项目 MIT 许可重新授权来源材料 | `data/field/sun-official/`；[逐项来源](docs/sources.md) |

## 通过依赖管理器安装的组件

实际版本由 [requirements.lock.txt](requirements.lock.txt)、[requirements-dev.txt](requirements-dev.txt) 和两个 npm `package-lock.json` 锁定。以下为直接使用的组件；传递依赖及原生库的 LICENSE、NOTICE、COPYING 等文件也必须随二进制分发保留。

| 组件 | 上游项目许可 |
| --- | --- |
| pvlib、NREL PySAM、pandas、NumPy、SciPy、Shapely、Uvicorn、Jinja2 | BSD-3-Clause |
| FastAPI、Pydantic、MCP Python SDK、ezdxf、openpyxl、pytest | MIT / Expat |
| Requests | Apache-2.0 |
| pypdfium2 | BSD-3-Clause 或 Apache-2.0；PDFium 另含其第三方许可 |
| Matplotlib | Matplotlib 许可（基于 PSF 许可），并保留随附声明 |
| [pywebview](https://github.com/r0x0r/pywebview) | BSD-3-Clause；其 Windows 桥接和系统运行时各有许可 |
| pypdf（测试）、Playwright（测试） | 分别为 BSD-3-Clause、Apache-2.0 |
| esbuild、Ajv、ajv-formats（构建与协议校验） | MIT |

官方项目、版本依据和用途详见 [来源登记](docs/sources.md)。本表是索引，不能替代上游许可原文。

## 外部运行环境

- [Agnes Harness](https://github.com/AgnesAI-Labs/agnes-harness/tree/5da40731214976ad8aff982cd5626d3a676fdd88)：Apache-2.0。本项目通过官方插件和 MCP 接口接入；仓库不复制整套 AGH 源码。分发 AGH 运行包时须保留其 LICENSE、NOTICE、THIRD-PARTY-NOTICES 及原有目录结构。
- Python：PSF 许可；安装包保留官方解释器随附许可。
- Microsoft Edge / WebView2：Microsoft 的软件条款；用户从系统或官方渠道安装，本项目不以 MIT 许可分发这些系统组件。
- Inno Setup：仅用于构建，遵循其官方许可，编译器不随光筑运行包分发。
- 模型服务：使用者自己的账号、凭据和服务条款，不属于本项目可再分发内容。

获取方法、版本限制及离线替代路径见 [外部依赖说明](docs/DEPENDENCIES.md)。
