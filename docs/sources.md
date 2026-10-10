# 来源登记

下表登记 T01 引入的 16 个直接依赖。核查日期：2026-10-01；安装版本以 `requirements.lock.txt` 为准。许可证栏记录项目自身许可证，发行包随附的版权、许可和第三方声明应予保留。

| 直接依赖 | 官方项目 | 许可证及第一方依据 | 用途 |
| --- | --- | --- | --- |
| pvlib | [pvlib-python](https://github.com/pvlib/pvlib-python) | BSD-3-Clause；[LICENSE](https://raw.githubusercontent.com/pvlib/pvlib-python/main/LICENSE) | 太阳位置、辐照转置和光伏模型 |
| nrel-pysam | [PySAM](https://github.com/NatLabRockies/pysam) | BSD-3-Clause；[LICENSE](https://raw.githubusercontent.com/NatLabRockies/pysam/main/LICENSE) | SAM / PVWatts 独立复核 |
| pandas | [pandas](https://github.com/pandas-dev/pandas) | BSD-3-Clause；[LICENSE](https://raw.githubusercontent.com/pandas-dev/pandas/main/LICENSE) | 带时区的逐小时表和数据读写 |
| numpy | [NumPy](https://github.com/numpy/numpy) | BSD-3-Clause；[LICENSE.txt](https://raw.githubusercontent.com/numpy/numpy/main/LICENSE.txt) | 数组运算 |
| scipy | [SciPy](https://github.com/scipy/scipy) | BSD-3-Clause；[LICENSE.txt](https://raw.githubusercontent.com/scipy/scipy/main/LICENSE.txt) | 科学计算与数值求解 |
| shapely | [Shapely](https://github.com/shapely/shapely) | BSD-3-Clause；[LICENSE.txt](https://raw.githubusercontent.com/shapely/shapely/main/LICENSE.txt) | 屋顶与遮挡几何 |
| requests | [Requests](https://github.com/psf/requests) | Apache-2.0；[LICENSE](https://raw.githubusercontent.com/psf/requests/main/LICENSE) | 外部天气接口 HTTP 请求 |
| pydantic | [Pydantic](https://github.com/pydantic/pydantic) | MIT；[LICENSE](https://raw.githubusercontent.com/pydantic/pydantic/main/LICENSE) | 结构化输入和数据校验 |
| fastapi | [FastAPI](https://github.com/fastapi/fastapi) | MIT；[LICENSE](https://raw.githubusercontent.com/fastapi/fastapi/master/LICENSE) | 后端 HTTP API |
| uvicorn | [Uvicorn](https://github.com/encode/uvicorn) | BSD-3-Clause；[LICENSE.md](https://raw.githubusercontent.com/encode/uvicorn/master/LICENSE.md) | ASGI 服务运行 |
| mcp | [官方 Python SDK](https://github.com/modelcontextprotocol/python-sdk) | MIT；[LICENSE](https://raw.githubusercontent.com/modelcontextprotocol/python-sdk/main/LICENSE) | AGH 接入的 MCP 服务 |
| ezdxf | [ezdxf](https://github.com/mozman/ezdxf) | MIT；[LICENSE](https://raw.githubusercontent.com/mozman/ezdxf/master/LICENSE) | DXF 排布图导出 |
| pypdfium2 | [pypdfium2](https://github.com/pypdfium2-team/pypdfium2) | BSD-3-Clause 或 Apache-2.0，随附 PDFium 等依赖许可；[LICENSES](https://github.com/pypdfium2-team/pypdfium2/tree/main/LICENSES)；2026-10-05 起用 5.14.0 | T18 把导入的 PDF 图纸页转成图片描边 |
| openpyxl | [openpyxl](https://foss.heptapod.net/openpyxl/openpyxl) | MIT/Expat；[官方文档 License 字段](https://openpyxl.readthedocs.io/en/stable/) | XLSX 材料清单导出 |
| matplotlib | [Matplotlib](https://github.com/matplotlib/matplotlib) | Matplotlib 许可（基于 PSF 许可）；[官方说明](https://matplotlib.org/stable/project/license.html)、[LICENSE](https://raw.githubusercontent.com/matplotlib/matplotlib/main/LICENSE/LICENSE) | 月度对比图等科学绘图 |
| jinja2 | [Jinja](https://github.com/pallets/jinja) | BSD-3-Clause；[LICENSE.txt](https://raw.githubusercontent.com/pallets/jinja/main/LICENSE.txt) | 方案书 HTML 模板 |
| pytest | [pytest](https://github.com/pytest-dev/pytest) | MIT；[LICENSE](https://raw.githubusercontent.com/pytest-dev/pytest/main/LICENSE) | 自动化测试 |

T01 的 PySAM Windows 路径兼容处理依据 [v7.1.1 原生加载器](https://github.com/NatLabRockies/pysam/blob/v7.1.1/src/PySAM_utils.h)：模块路径按 ASCII 编码。运行时镜像仅复制已安装发行包的二进制与默认配置，不修改其代码；同样适用 PySAM 的 BSD-3-Clause 许可。

## T02 天气数据

| 来源 | 许可 / 引用要求与依据 | 用途 |
| --- | --- | --- |
| [NASA POWER 逐小时接口](https://power.larc.nasa.gov/docs/services/api/temporal/hourly/) | CC-BY-4.0；[官方 LICENSE](https://nasa-power.s3.us-west-2.amazonaws.com/LICENSE.txt)、[CITATION](https://nasa-power.s3.us-west-2.amazonaws.com/CITATION.cff)、[引用指南](https://power.larc.nasa.gov/docs/referencing/)。引用 NASA POWER Project，记录 API 版本、访问日期、地点和年份。 | 常州 2023 UTC 五参数天气；演示数据及接口录样，API v2.10.2，下载 2026-10-01。来源含 MERRA2、SYN1DEG、POWER。 |
| [European Commission JRC，PVGIS 5.3 TMY](https://re.jrc.ec.europa.eu/api/v5_3/tmy) | 官方[使用条件](https://joint-research-centre.ec.europa.eu/photovoltaic-geographical-information-system-pvgis/general-information/usage-conditions-data-protection_en)说明输出免费且无使用限制；注明 JRC / PVGIS、数据库和访问日期。 | 常州 PVGIS-ERA5 典型年（候选年 2005–2023），演示数据及接口录样；下载 2026-10-01。 |

NASA 小时标签为时段开始，依据 [NASA 官方 FAQ：Time Range](https://power.larc.nasa.gov/docs/faqs/other/#time-range)。PVGIS JSON/CSV 的 ERA5 标签 HH:00 对应辐照时刻 HH:30，依据 [官方手册 §9.3、§10.2](https://joint-research-centre.ec.europa.eu/photovoltaic-geographical-information-system-pvgis/using-pvgis-5/pvgis-5-user-manual_en)；实际响应 `irradiance_time_offset=0.5` 小时。

## T03 发电模型与设备数据

| 来源 | 许可 / 第一方依据 | 用途 |
| --- | --- | --- |
| NREL SAM，锁定提交 `cba319ded1c32a7f5b3ac76545a29e1f7181d238` 的 [CEC Modules.csv](https://raw.githubusercontent.com/NREL/SAM/cba319ded1c32a7f5b3ac76545a29e1f7181d238/deploy/libraries/CEC%20Modules.csv) 与 [CEC Inverters.csv](https://raw.githubusercontent.com/NREL/SAM/cba319ded1c32a7f5b3ac76545a29e1f7181d238/deploy/libraries/CEC%20Inverters.csv) | BSD 3-Clause；[锁定版本 LICENSE](https://raw.githubusercontent.com/NREL/SAM/cba319ded1c32a7f5b3ac76545a29e1f7181d238/LICENSE)，原文保存在 `data/catalog/LICENSE-SAM.txt`。 | 完整库 SHA-256 校验、CEC 单二极管组件和 Sandia 逆变器效率模型；原始行离线子集、哈希、提取日期见 `data/catalog/PROVENANCE.md`。 |
| 天合光能 [TSM-DE19 官方规格书，2022 APAC B](https://static.trinasolar.com/sites/default/files/Vertex_DE19_EN_2022_APAC_B_web.pdf) | 厂家版权资料，仅链接引用，不再分发 PDF。 | TSM-550DE19 的 2384 × 1096 × 35 mm、28.6 kg 写入 `data/catalog/modules.csv`；不替换 CEC 电气参数。 |
| 天合光能 [官方公司介绍](https://www.trinasolar.com/en-glb/about-us/)与[官方公司手册](https://static.trinasolar.com/sites/default/files/Trinasolar_Corporate_Brochure_EN_20240514.pdf) | 厂家版权资料，仅链接引用。 | 核实厂商总部位于江苏常州。 |
| 阳光电源 [SG60CX-US 官方规格书 V13](https://info-support.sungrowpower.com/application/pdf/2023/04/04/DS_20230327_SG60CX-US_Datasheet_V13_EN.pdf) 与[用户手册 Ver17，2024-11](https://info-support.sungrowpower.com/application/pdf/2024/11/29/M-D-000059-JS-105303-SG36_60CX_US-UEN-Ver17-202411_compress.pdf) | 厂家版权资料，仅链接引用，不再分发 PDF。 | 核实组串式型号与 550–850 V 额定功率 MPPT 范围。仅用于 T03 效率模型和 STC 组合记录，T06 再定义国内电气约束。 |
| [NREL SPA 技术报告](https://www.nrel.gov/docs/fy08osti/34302.pdf) | NREL 第一方技术报告；通过已登记 BSD 许可的 pvlib 调用其算法，不复制报告。 | 标准例题与 ΔT=67 s 验证。 |
| [PySAM v7.1.1 发行记录](https://github.com/NatLabRockies/pysam/releases/tag/v7.1.1)与[对应 SSC 306 PVWatts v8 源码](https://github.com/NatLabRockies/ssc/blob/2025.4.16.r2.ssc.306/ssc/cmod_pvwattsv8.cpp) | PySAM / SSC 官方源；SSC [BSD-3-Clause LICENSE](https://github.com/NatLabRockies/ssc/blob/2025.4.16.r2.ssc.306/LICENSE)。仅引用版本及模型依据。 | 确认安装的 SSC 版本 306、屋顶 NOCT 49°C、标准组件 CEC 模型和逆变器内部模型；解释与 pvlib 简化链的差异。 |
| [JRC PVGIS 5.3 PVcalc](https://re.jrc.ec.europa.eu/api/v5_3/PVcalc) | 同 T02 的 PVGIS 官方使用条件；注明 JRC / PVGIS、PVGIS-ERA5、访问日期。 | 常州 1 kWp、25°、正南、损失 14% 的独立天气源计算器对照；真实响应作为离线演示和测试录样。 |

## T04 排板依据与合成数据

| 来源 | 许可 / 引用范围 | 用途 |
| --- | --- | --- |
| [住建部《光伏发电站设计规范》2024局部修订公告及附件](https://www.mohurd.gov.cn/gongkai/zc/wjk/art/2024/art_96bd1b03e8d54760b4dff9ad60352ddc.html) | 官方公告与标准版权资料，仅链接并短摘，不分发PDF。核查2026-10-01。 | 7.2.2第2款的地面阵列适用范围、9–15窗口及2024措辞修订；旧屋顶7.2.3要求技术经济比较。报告区分2012版本与2025-04-01生效修订。 |
| [宁波官方屋面光伏图集](https://zjjcmspublic.oss-cn-hangzhou-zwynet-d01-a.internet.cloud.zj.gov.cn/jcms_files/jcms1/web3516/site/attach/0/5208a7c3002c4291a3745727828dd6e7.pdf) | 官方发布的版权资料，仅链接引用，不分发PDF。 | “典型屋面光伏阵列计算”式5-1转述GB50797-2012条文说明7.2.2，复核任务手算行距式；不是原版条文说明的一手整页。 |
| [pvlib SPA输出文档](https://pvlib-python.readthedocs.io/en/stable/reference/generated/pvlib.solarposition.spa_python.html) | 已登记BSD-3-Clause库的官方文档，仅引用。 | 真实高度与视高度的区别、均时差单位；T04真实太阳时迭代换算与影长计算。 |
| 项目规格与T04任务卡；T03已登记厂家尺寸 | 本项目合成输入及示意假设，无外部底图、无真实现场测量。 | 常州演示和三屋顶fixture；支架缝0.02 m、下沿0.3 m标“示意”，组件真实物理尺寸沿用厂家规格书。 |

## T05 遮挡与影子工具

| 来源 | 许可 / 引用范围 | 用途 |
| --- | --- | --- |
| pvlib 官方 [masking_angle_passias](https://pvlib-python.readthedocs.io/en/stable/reference/generated/pvlib.shading.masking_angle_passias.html)、[sky_diffuse_passias](https://pvlib-python.readthedocs.io/en/stable/reference/generated/pvlib.shading.sky_diffuse_passias.html)、[对应源码](https://pvlib-python.readthedocs.io/en/stable/_modules/pvlib/shading.html#sky_diffuse_passias) | 已登记BSD-3-Clause库的函数与官方文档；文档列出Passias/Källbäck 1984原始论文及天空散射公式依据。只调用库函数，不复制论文。 | 前排天空散射遮挡因子。Passias假定各向同性天空，按任务要求将其作用于Perez天空散射；报告注明近似和不计障碍物/女儿墙散射。 |
| T02 NASA2023、T03 SPA/Perez、T04项目及厂家尺寸 | 来源与许可沿用上面的登记；未新增天气或设备源。 | UTC月15日小时中点代表几何，用真实8760小时斜面直射能量加权；元数据含天气gzip SHA-256。 |
| 本项目任务卡的三段模型、解析阴影与合成屋顶 | 本项目规则与合成测试，不冒充现场实测；8%阈值标“示意”。 | 精确面射线判断、1/6/1/2/5/6样点、归因与500组件性能夹具；`data/field/shadow_test.csv`只含空表头。 |

## T06 设备、温度和电气依据

访问日期均为2026-10-01。厂家PDF保留厂家版权，本仓库仅登记链接与事实参数，不分发PDF。原始CEC行仍适用上述SAM BSD许可。

| 来源 | 许可 / 引用范围 | 用途 |
| --- | --- | --- |
| [润阳HY-WH144P8官方规格书](https://www.runergy.com/wp-content/uploads/download/WH144P8-35F.pdf) | 厂家版权；Global Ver3.0，2023，第1–2页 | 单面单晶550 W组件尺寸、电气、NOCT；锁定CEC原始行及与规格书差别见PROVENANCE.md。 |
| [阳光SG100CX-P2 IEC/AU规格书](https://info-support.sungrowpower.com/datasheet-materials/fe40521c-fd35-4a37-9b79-fdf4d29d51b2.pdf)、[用户手册Ver18-202604](https://info-support.sungrowpower.com/product-materials/52a5cd73-4418-4314-a7a1-14a979d6300c.pdf) | 厂家版权；规格书AU Version4，2026，第2页；手册PDF第113页/印刷106页 | 99.99 kW、1100 V、每MPPT 30/50 A、运行与满载MPPT范围；保留缺失字段。 |
| [华为SUN2000-100KTL-M2 IEC规格书](https://solar.huawei.com/admin/asset/v1/pro/view/c5056ea20b95424fad3c62f0a5e64a84.pdf) | 厂家版权；文件元数据2025-06-26，第2页 | 100 kW、1100 V、每MPPT 30/40 A；选400 V效率；重量取≤93 kg上界。 |
| [NASA POWER逐日API](https://power.larc.nasa.gov/docs/services/api/temporal/daily/) | 同T02 CC-BY-4.0及NASA POWER引用要求 | 常州1996–2025、T2M_MIN/MAX、community=RE，10958天，API2.10.0，MERRA2、LST；常州原始缓存/演示gzip及元数据。 |
| [常州市政府2018公开规划资料](https://www.changzhou.gov.cn/gi_news/509154440924443) | 政府公开资料，链接引用事实，不复制全文 | 第3.7/3.8节历史气温；明确不是同站同1996–2025时段极值复核。 |
| 上述[住建部2024局部修订及附件](https://www.mohurd.gov.cn/gongkai/zc/wjk/art/2024/art_96bd1b03e8d54760b4dff9ad60352ddc.html) | 官方公告与标准版权资料，链接和公式事实引用 | PDF第26页/印刷20页6.4.2已删除旧MPPT上界公式；任务保留E04为厂家附加检查。G02措辞沿用T04查证。 |
| 本项目估算与任务卡 | 示意，无外部厂家依据 | 支架6 kg/块=2×2.5×0.9+1.5；压块30 kg/块=2×15，不用于结构或风荷载设计。 |

## T07 经济默认值、政策和减碳

核查日期2026-10-01；完整页码、日期区别、适用条件、原件哈希和未查证说明见`data/catalog/ASSUMPTIONS.md`。CSV每项保存状态和出处，计算结果另记录项目覆盖来源。

| 来源 | 许可 / 引用范围 | 用途 |
| --- | --- | --- |
| [CPIA《中国光伏产业发展路线图2025–2026》官方发布](https://www.chinapv.org.cn/StaticPage/Industry/resource_1411.html)、[陕西太阳能协会原文入口](https://www.sxseia.com/nd.jsp?id=1094)所附原件 | 未发现开放再分发许可，保留原作者版权；只链接、摘取有限事实，不分发PDF | 2025工商业造价2.59元/W（PDF65/印刷55页）、基础运维0.046元/(W年)（PDF66/印刷56页）；脚注排除固定资产更换。演示2.6/0.04是用户示意覆盖。 |
| [国网江苏入口](https://js.sgcc.com.cn/)、[金坛2026年5月公告](https://www.jintan.gov.cn/html/czjt/2026/JFKEQAOD_0428/297534.html) | 公开价格核查入口；最新2026年10月官方表未取得 | 不采用旧月份或二手转录价格，0.65自用价保留示意；失败入口与检索条件记录在ASSUMPTIONS.md。 |
| [国家发改价格〔2025〕136号](https://www.ndrc.gov.cn/xxgk/zcfb/tz/202502/t20250209_1396066_ext.html)、[江苏苏发改规发〔2025〕5号](https://www.jiangsu.gov.cn/art/2025/11/18/art_64797_11676529.html) | 官方公开规范文件，仅链接及事实转述 | 查证新能源市场电价与增量竞价机制；0.391燃煤基准价仅作未确定新建结算价的示意占位。 |
| [能源局2025分布式光伏管理办法](https://www.nea.gov.cn/20250123/112c5b199c5f45dd8e7ac93c9f5e4eaf/c.html)、[官方问答](https://www.nea.gov.cn/20250411/dca28f9186e848dda1d690d192fa50f8/20250411dca28f9186e848dda1d690d192fa50f8_113000de00999043e8a7fe4446dd6d97d8.pdf) | 官方公开政策及解读，仅链接与事实转述 | 206.8kW厂房按公共连接点≤10(20)kV假设属于一般工商业，可选择自用余电上网；真实接网条件与省级自用比例仍需核实。 |
| [MEE/NBS 2025年第47号公告](https://www.mee.gov.cn/xxgk2018/xxgk/xxgk01/202512/t20251231_1139517.html)、[2023因子附件](https://www.mee.gov.cn/xxgk2018/xxgk/xxgk01/202512/W020251231726284332528.pdf) | 官方公开统计资料，只引用两个因子与口径，不分发附件 | 2025-12-31发布，2023江苏0.5827/全国0.5306 kgCO₂/kWh；作为平均电力减碳估算，不作CCER或生命周期因子。 |
| 上述[天合2022 APAC B规格书](https://static.trinasolar.com/sites/default/files/Vertex_DE19_EN_2022_APAC_B_web.pdf) | 厂家版权；只事实引用 | 第2页0.55%后续年衰减与25年功率质保，按任务转为指数发电估算；不再扣厂家首年2%。 |
| [NREL PVWatts v5 Manual](https://pvwatts.nrel.gov/downloads/pvwattsv5.pdf)，NREL/TP-6A20-62641 | 第一方公开技术报告；只链接与分项/公式事实引用 | 印刷10页表6/式9：去掉3%遮挡后的连乘损失11.418206895118011%，另扣T05遮挡；T03保留14%。 |
| [JRC PVGIS 5.3计算器](https://re.jrc.ec.europa.eu/api/v5_3/PVcalc) | 沿用T02/JRC官方使用条件：输出免费、无使用限制，注明JRC/PVGIS与数据库日期 | 演示25°、180°、精确11.418206895118011%损失的新真实响应，按独立loss键提交；原14%样本未改。 |

自用比例0.8、折现率0.06及演示自用电价/造价/运维覆盖均为示意，非外部已查证工程条件。临时读取原件用TemporaryDirectory并清理；未引入付费资料、厂家PDF或新依赖。

## T08 MCP 与执行记录

| 来源 | 许可 / 依据 | 用途 |
| --- | --- | --- |
| 已锁定官方 MCP Python SDK 2.2.0，本机发行包 `mcp/server/lowlevel/server.py`、`mcp/server/stdio.py`、`mcp/client/stdio.py` | 沿用 T01 登记 MIT；直接调用 SDK，未复制第三方实现 | stdio、十个工具、只向协议输出 stdout；客户端真实冒烟。 |
| [Ajv](https://github.com/ajv-validator/ajv)、[ajv-formats](https://github.com/ajv-validator/ajv-formats) | 两者 MIT；本机安装包 LICENSE / package.json 已核对；版本固定 8.20.0 / 3.0.1，package-lock 锁定下载完整性 | JSON Schema 2020-12 严格编译，参数来自真实 tools/list。 |
| 已有 `竞赛/work/agnes-harness` 官方源树，HEAD `5da40731214976ad8aff982cd5626d3a676fdd88` | 只读核查，不复制运行包或第三方源码；来源与固定版本沿用 06-agh / T08 任务卡 | `protocol/gen/ts/session-v1.ts` 原生事件；`cli/src/commands/export.ts:145,173` 原生逐行/默认脱敏；`core/src/step/tools.ts:547,742`、`approval-callback.ts:91` 实际审批顺序及网页 callback；`resource-control-cli/src/resources.ts:263,531,586` 无密钥 stdio 注册与实时 revision。 |
| T04 已登记屋顶 fixture；T08 任务卡 | 本项目合成几何与合成事件，非现场 / 模型执行记录 | L 形和旋转演示项目保持 fixture 屋顶，采用已有常州天气与已审查经济默认；四份账本文件名明确标“合成”。 |
| 官方 [MCP TypeScript SDK v1.25.2 stdio 源码](https://github.com/modelcontextprotocol/typescript-sdk/blob/v1.25.2/src/client/stdio.ts) | MIT；只核查 `DEFAULT_INHERITED_ENV_VARS_WIN32` / `getDefaultEnvironment`，不复制实现 | 结合上述 AGH `mcp-server-opener.ts:153,178` 和 `connect.ts:264`，锁定无额外环境变量、无指定工作目录的真实启动方式。 |
| 上述 JRC PVGIS 5.3 PVcalc；T08 审查第5项 | 沿用已有 JRC 许可与引用要求；精确参数、原响应 SHA256、原下载日期保存在预取证据中 | 常州31.81/119.97、10°/15°/20°/25°/30°、正南、损失11.418206895118011%的预取缓存；命中已有缓存时如实记录为cache。 |

## T09 Windows 工具进程诊断

| 来源 | 许可 / 引用范围 | 用途 |
| --- | --- | --- |
| Microsoft 官方 [SetProcessInformation](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-setprocessinformation)、[PROCESS_POWER_THROTTLING_STATE](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/ns-processthreadsapi-process_power_throttling_state)、[GetProcessInformation](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getprocessinformation) | 2026-10-02 查阅 API 定义和掩码事实；本项目自行编写 ctypes 调用，没有复制第三方代码 | 仅在光筑工具进程内关闭执行速度节流，记录前后状态；不更改系统电源计划或进程优先级。 |

## T09 模型费用估算

| 来源 | 许可 / 引用范围 | 用途 |
| --- | --- | --- |
| DeepSeek 官方 [Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/) | 2026-10-01（America/Los_Angeles）核查；只登记公开型号、价格和时段事实，不分发页面 | `deepseek-flash` 对应V4.1-Flash；每百万未命中输入/输出/缓存读取美元价格：闲时0.15/0.60/0.003，峰时0.30/1.20/0.006。法定假日全天闲时。仅按官方直连假设估算，不当作账号实付。 |
| [国务院办公厅2026年节假日安排](https://big5.www.gov.cn/gate/big5/www.gov.cn/zhengce/zhengceku/202511/content_7047091.htm) | 政府公开通知，2025-11-04；仅链接和日期事实 | 首轮北京时间2026-10-02处于国庆10/1–7放假期；依据DeepSeek公开时段规则选闲时档。 |

## T10 AGH 插件与离线构建

| 来源 | 许可 / 依据 | 用途 |
| --- | --- | --- |
| 上述固定 AGH 源树 `5da40731214976ad8aff982cd5626d3a676fdd88`，官方 frontend / skins / packages 文档及 client-panel、dsh-tool-view、skin-example 示例 | 沿用官方项目许可登记；只读核对接口和清单，未修改 AGH；插件为本项目独立实现 | 两个插件行分别绑定面板和皮肤的描述文件；使用宿主 React / antd、会话命令和投影、公开插槽；官方包管理 inspect/operation/get 读取公开完整性与能力摘要。 |
| [esbuild 构建文档](https://esbuild.github.io/getting-started/)、[esbuild 源码和许可](https://github.com/evanw/esbuild) | MIT；2026-10-02 核对 npm 元数据并在项目开发目录安装 0.28.2；完整性 `sha512-HKVLS8dvII+xoKW9kmqxbRKrnWEXfJJr/FZhhJmiqIB0e053QNYFqOBouTMO/k5sID4MvCiUCvv8b9M4h32wIA==` | Python 构建脚本生成数据与浏览器 ESM；React、react/jsx-runtime、antd 作为宿主 external，不打包第二份 React。正式版 package-lock 锁定 esbuild 0.28.2；构建脚本 --check 在临时目录重建核对，--release 生成仅含运行文件的安装包。 |

## T10 本地字体

| 来源 | 许可 / 第一方依据 | 用途与保存 |
| --- | --- | --- |
| IBM 官方 [Plex Mono](https://github.com/IBM/plex/tree/master/packages/plex-mono)、[Regular woff2](https://raw.githubusercontent.com/IBM/plex/master/packages/plex-mono/fonts/complete/woff2/IBMPlexMono-Regular.woff2) | OFL-1.1；[原始 LICENSE](https://raw.githubusercontent.com/IBM/plex/master/LICENSE.txt)，保留 IBM 版权及 Reserved Font Name「Plex」，字体未经本项目改动 | 数字字体，400 字重，49,248 字节；字体保存在 `agh-plugin/guangzhu-studio/extensions/main/skins/guangzhu/assets/IBMPlexMono-Regular.woff2`，许可保存在包根 `agh-plugin/guangzhu-studio/licenses/LICENSE-IBM-Plex.txt`。 |
| Google 官方 [Noto Serif SC](https://github.com/google/fonts/tree/main/ofl/notoserifsc)、[METADATA](https://raw.githubusercontent.com/google/fonts/main/ofl/notoserifsc/METADATA.pb)，上游 [Noto CJK](https://github.com/notofonts/noto-cjk) | OFL-1.1；[原始 OFL](https://raw.githubusercontent.com/google/fonts/main/ofl/notoserifsc/OFL.txt)，保存为包根 `agh-plugin/guangzhu-studio/licenses/LICENSE-Noto-Serif-SC.txt`；METADATA 锁定上游提交 `985fa52c81c1d6692ccdd82bc3656e8fb932fd89` | 标志「光筑」900 字重，Google Fonts 官方 `text=光筑` API 返回的两个字子集，1,420 字节，小于 200KB；保存在 `agh-plugin/guangzhu-studio/extensions/main/skins/guangzhu/assets/NotoSerifSC-900-guangzhu.woff2`。 |

下载日期 2026-10-02；两个 woff2 的 SHA-256、大小、具体下载 URL、UTC 下载时间、官方子集 CSS 和核查结果保存在 `reports/assets/T10-spike/fonts-manifest.json`。运行时仅从插件包加载本地字体，不使用 Google Fonts 网络 CSS；正文使用系统中文字体。发布包保留包级 `licenses/`；官方皮肤资源白名单仅允许图片和字体，因此许可证不放入皮肤 `assets/`。

## T14 桌面窗口与界面

| 来源 | 许可 / 第一方依据 | 用途与保存 |
| --- | --- | --- |
| [pywebview 6.2.1 官方 PyPI](https://pypi.org/project/pywebview/6.2.1/)、[官方窗口 API](https://pywebview.flowrl.com/api/)、[Windows 渲染器说明](https://pywebview.flowrl.com/guide/web_engine.html) | BSD-3-Clause；2026-10-02 核查并安装 6.2.1；通过官方包发行元数据核对许可 | 桌面原生窗口使用 `edgechromium`（系统 WebView2），不复制实现。新增 pywebview/pythonnet/clr_loader/proxy_tools/bottle 的解析版本登记在 `requirements.lock.txt`；其余原有依赖不升级。元数据证据为 `reports/assets/T14-prep/desktop-dependencies.json`。 |
| 上述 T10 IBM Plex Mono 和 Noto Serif SC 字体 | OFL-1.1，字体字节保持不变，保留原版权与许可证 | 离线副本位于 `desktop/web/vendor/fonts/`，许可证在 `desktop/web/vendor/licenses/`，SHA-256 与字节一致性证据为 `reports/assets/T14-prep/font-provenance.json`。 |
| three.js [r128 官方预压缩发行文件](https://raw.githubusercontent.com/mrdoob/three.js/r128/build/three.min.js)、[官方 OrbitControls 源码](https://raw.githubusercontent.com/mrdoob/three.js/r128/examples/js/controls/OrbitControls.js)、[MIT 许可证](https://raw.githubusercontent.com/mrdoob/three.js/r128/LICENSE) | MIT，2026-10-02 下载固定标签 r128，保留版权与原始许可 | `desktop/web/vendor/three.min.js` 为官方原厂发行文件；OrbitControls 原文在 `docs/sources/three-r128/OrbitControls.js`，仅用已有 esbuild 0.28.2 压缩该第三方文件生成 `vendor/OrbitControls.min.js`。下载来源、逐文件 SHA-256、变换命令登记于 `desktop/web/vendor/SOURCES.json`，不压缩本项目代码、不在页面引入构建工具。 |

界面布局参考了 Modex · MH Agent 的公开产品截图（mingheng.xin），只参考布局，没有使用它的代码、图标、图片和文字。实现依据是审查方已经批准的 `docs/design/autopilot.html` 第 5 版。

## T11 方案书打印与验证

| 来源 | 许可 / 第一方依据 | 用途 |
| --- | --- | --- |
| [pypdf 6.19.0 官方 PyPI](https://pypi.org/project/pypdf/6.19.0/) | BSD-3-Clause；2026-10-03 核对安装包元数据及随包 LICENSE，版本锁在 requirements-dev.txt | 仅开发测试读取 PDF 页数和文本，不在业务运行时导入；安装回执在 reports/assets/T11/pypdf-install.txt。 |
| [Chromium Headless 命令说明](https://developer.chrome.com/docs/automation-and-testing/headless-cli) | 系统浏览器提供的命令行功能；浏览器不随本项目分发 | 按 T11 卡用系统 Microsoft Edge 无头打印，找不到则用 Chrome；两个都没有时保留 HTML，由用户自行打印。 |
| 上述 IBM Plex Mono 与 Noto Serif SC 字体 | 原 OFL 许可不变，使用既有字节，不改字体 | 以 base64 内嵌到 HTML 方案书，保证单文件可离线打开；正文仍使用系统中文字体。 |

## T12 测试屋顶与官方太阳数据

| 来源 | 许可 / 使用依据 | 用途与保存 |
| --- | --- | --- |
| [OpenStreetMap 版权与署名](https://www.openstreetmap.org/copyright)、[ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/)、[Overpass 公共服务使用规则](https://dev.overpass-api.de/overpass-doc/en/preface/commons.html) | © OpenStreetMap contributors；建筑轮廓及改编数据库按 ODbL 1.0 提供，保留署名和许可；公共实例只做离线准备，遵守限流与退避，不作为产品服务后端 | 常州武进 12 栋工业建筑轮廓及江苏城市点；2026-10-03 取数，固定挑选规则在 data/roofs/README.md，原始顶点、查询、时间及响应 SHA256 在 osm-raw.json；不用企业名称，其余屋面资料标示意。 |
| 上述 NASA POWER 小时、逐日接口及 JRC PVGIS TMY、PVcalc | 沿用已核对的 CC-BY-4.0 / JRC 使用条件和署名 | T12 精确场址与倾角的离线验证快照沿用 data/demo/weather 和 data/demo/yields；各文件元数据保留真实 API URL、下载时间、数据源和 SHA256，原演示数据不改。 |
| [USNO API](https://aa.usno.navy.mil/data/api)、[USNO 隐私与版权声明](https://aa.usno.navy.mil/about/PrivacyNotice) | 官方声明第 2 项：未特别说明的信息可视为公开并复制、分发，应适当署名；注明 U.S. Naval Observatory | 2026-10-03 获取太阳几何高度、方位及日出日落；原响应 JSON 和逐请求 URL、UTC 时间、SHA256 在 data/field/sun-official/，离线对照见 reports/assets/T12/sun-official.md。 |
| [中国天气网城市页](https://www.weather.com.cn/weather1d/101191101.shtml)、[版权声明](https://www.weather.com.cn/wzfw/banquan.shtml) | 中国气象局公共气象服务中心主办；网站保留版权，不标开放许可，不镜像内容或保存整页。仅按 T12 卡摘录公开的日出、日落时刻事实并引用城市 URL | 江苏 13 城逐日摘录；每城每天至多一次，保留实际取数时间及页面日期，验证或防火墙拒绝即停止；具体时刻与日期在 data/field/sun-official/weather-*.json。 |

## T12 真实电站数据

| 来源 | 许可 / 使用依据 | 用途与保存 |
| --- | --- | --- |
| [PVOD 作者仓库](https://github.com/yaotc/PVODataset)、[数据 DOI](https://doi.org/10.11922/sciencedb.01094) | 作者 README 限定科学研究用途；仓库 MIT 声明未明确覆盖数据，匿名 API 返回 403，未登录或绕过验证 | 按卡片顺序查证后放弃此源，不使用其数据。 |
| [NREL PVDAQ / OEDI](https://data.openei.org/submissions/4568)、[官方数据目录与许可](https://catalog.data.gov/dataset/photovoltaic-data-acquisition-pvdaq-public-datasets)、[元数据说明与时段标记 L/C/R](https://github.com/openEDI/documentation/blob/main/pvdaq.md) | CC BY 4.0；引用 Deline, Perry, Deceglie, Muller, Sekulic, Jordan (2021), Photovoltaic Data Acquisition (PVDAQ) Public Datasets, DOI 10.25984/1846021 | 匿名公开 S3 HTTPS，不注册账号；固定电站 2107、2022 整年（先固定 2024，时间覆盖审计缺 12 月后、未看模拟误差前改为 2022），容量/倾角/朝向来自官方元数据。原下载仅 data/cache/plant，网址、SHA256、清洗规则和月度子集在 data/field/plant，完整对照证据在 reports/assets/T12/plant-2107.md。 |

## T13 评测驱动

| 来源 | 许可 / 第一方依据 | 用途 |
| --- | --- | --- |
| [Playwright Python 1.58.0 官方 PyPI](https://pypi.org/project/playwright/1.58.0/)、[官方浏览器 channel 文档](https://playwright.dev/python/docs/browsers) | Apache-2.0；2026-10-03 核查安装包版本；开发依赖锁在 requirements-dev.txt | 按卡片用系统 Edge 的 msedge channel、单独临时用户目录驱动本地评测页面；只安装 Python 包，不运行 playwright install、不下载或分发浏览器。 |

## T18 自建屋顶

| 来源 | 许可 / 使用依据 | 用途与保存 |
| --- | --- | --- |
| [OpenStreetMap Nominatim 搜索接口](https://nominatim.org/release-docs/latest/api/Search/)、[公共实例使用规则](https://operations.osmfoundation.org/policies/nominatim/)、[OpenStreetMap 版权与署名](https://www.openstreetmap.org/copyright) | © OpenStreetMap contributors，ODbL 1.0；公共实例每秒不超过 1 次、带应用标识，一次性取数，不作为产品服务后端 | 江苏 13 个市和 30 个省会、直辖市的城市点经纬度（保留 4 位小数和 OSM 对象编号）；2026-10-05 取数，保存在 desktop/web/cities.json，屋顶编辑页选城市时填入，用户可改。 |
| 测试用图纸 | 测试运行时用 Pillow、ezdxf 现画的矩形、L 形屋顶图片、PDF 和 DXF，不用任何外来图纸 | tests/test_myroofs.py、tests/test_roof_editor_dom.py |

## T15 安装包

| 来源 | 校验与许可 | 用途 |
| --- | --- | --- |
| [Python 3.12.10 官方发布页](https://www.python.org/downloads/release/python-31210/)、[嵌入式发行说明](https://docs.python.org/3.12/using/windows.html#the-embeddable-package) | Windows x64 embeddable ZIP；核对官网 MD5 `fe8ef205f2e9c3ba44d0cf9954e1abd3`、解释器 PSF Authenticode 签名；保留随包 LICENSE.txt | 程序自带解释器和锁定依赖，不在用户运行时下载。真实 ZIP SHA256 由构建 manifest 记录。 |
| [Inno Setup 6 下载页](https://jrsoftware.org/isdl.php)、[官方验签说明](https://jrsoftware.org/isdl-verify.php)、[静默安装参数](https://jrsoftware.org/ishelp/topic_setupcmdline.htm) | 6.7.3 官方安装器及 ISCC 均检查有效的 Pyrsys B.V. Authenticode 签名；原安装器 SHA256 记录到 manifest | 构建工具；用户安装包不含编译器。默认使用已安装 ISCC，缺失时隐藏安装到构建缓存。 |
| [AGH 固定源码](https://github.com/AgnesAI-Labs/agnes-harness/tree/5da40731214976ad8aff982cd5626d3a676fdd88) | 用户提供官方 x64 ZIP，SHA256 `FFB6DE31E409098459847F67DB1A68D1FB3B23F8893ADF9F489BFD1B03284AED`；原 LICENSE/NOTICE 从该提交复制，保留分发包 THIRD-PARTY-NOTICES | 只复制 runtime/agh 原始发行文件，不构建或修改 AGH。 |
| [PyPI 官方索引](https://pypi.org/simple/)、[npm 官方 registry](https://registry.npmjs.org/) | Python 依赖由 requirements.lock.txt 固定；构建日志保留下载 URL，manifest 记录 wheel SHA256；插件 npm ci 按 package-lock integrity 校验 | 安装包内含运行依赖和 build_agh_plugin.py --release 的单一不可变快照。 |
| 光筑图标（`desktop/web/assets/guangzhu.ico`、`guangzhu-128.png`） | 本项目原创：用 Pillow 画的圆角方块、光伏板和太阳，不用任何现成图片和字体 | 安装包、快捷方式、窗口、任务栏和页面左上角的图标 |
| Windows 自带的 .NET Framework 4 C# 编译器（`%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe`） | 随 Windows 提供的系统组件，只在构建时使用，不随包分发 | 把 `desktop/launcher/launcher.cs` 编译成"光筑.exe"（只负责用内置 Python 打开窗口） |
| Inno Setup 自带的简体中文语言文件 `Languages\ChineseSimplified.isl` | 随 Inno Setup 6.7.3 官方安装器提供，与 Inno Setup 同一许可 | 安装界面用中文 |

# T23 逆变器官方来源核实

访问日期：2026-10-05（America/Los_Angeles）。仅下载官网原始 PDF；没有改仓库文件。页码均为从1起的PDF页码；手册另列印刷页码。CSV结构与当前 inverters.csv 一致，未知项写“规格书未给出”。

## 来源及逐字段核对

### SG50CX-P2

- 规格书：https://info-support.sungrowpower.com/application/pdf/2023/12/21/DS_20231219_SG36_40_50CX-P2_Datasheet_V4_EN.pdf
- 版本：Version 4；日期：2023；技术规格PDF第2页。
- 官方产品页：https://www.sungrowpower.com/kr/en/products/string-inverter/b-sg50cx-p2
- 口径：最大交流视在功率55kVA；最大交流有功功率和中国效率规格书未给出；日期只有版权年份；满载范围来自手册PDF第107页（印刷第100页）；英文IEC版；访问日期2026-10-05（美国洛杉矶）
- 满载来源：https://info-support.sungrowpower.com/cms/af994f1d-bb0d-408a-b310-6ad732402c99/GUID-25D7DF3A-AC5A-4DDE-AE7D-B02E6AE8DB3C_1_en-US_PDF%20%28%E4%BA%A7%E5%93%81%E4%BF%A1%E6%81%AF%E8%AE%BE%E8%AE%A1%E9%83%A8_%E5%9F%BA%E7%A1%80%E7%89%88%29_1789440969930_compressed.pdf
- 满载来源版本：SG25_30_33_36_40_50CX-P2-UEN-Ver114-202604；PDF第107页。

| 字段 | 核实值 |
| --- | --- |
| inverter_id | sungrow-sg50cx-p2 |
| manufacturer | Sungrow |
| model | SG50CX-P2 |
| rated_ac_kw | 50 |
| max_ac_kw | 规格书未给出 |
| max_ac_kva | 55 |
| max_dc_voltage_v | 1100 |
| mppt_min_v | 160 |
| mppt_max_v | 1000 |
| full_load_mppt_min_v | 500 |
| full_load_mppt_max_v | 800 |
| start_voltage_v | 200 |
| mppt_count | 4 |
| strings_per_mppt | 2 |
| max_input_current_per_mppt_a | 30 |
| max_short_circuit_current_per_mppt_a | 40 |
| max_efficiency_pct | 98.5 |
| weighted_efficiency_pct | 98.3 |
| weighted_efficiency_type | European |
| weight_kg | 41 |
| grid_frequency_hz | 50/60 |
| datasheet_version | Version 4 |
| datasheet_page | 2 |
| datasheet_date | 2023 |
| full_load_source_version | SG25_30_33_36_40_50CX-P2-UEN-Ver114-202604 |
| full_load_source_page | 107 |
| assumptions_note | 最大交流视在功率55kVA；最大交流有功功率和中国效率规格书未给出；日期只有版权年份；满载范围来自手册PDF第107页（印刷第100页）；英文IEC版；访问日期2026-10-05（美国洛杉矶） |

### SG125CX-P2

- 规格书：https://info-support.sungrowpower.com/application/pdf/2024/09/13/DS_20240709_SG125CX-P2_Datasheet_V6_EN.pdf
- 版本：Version 6；日期：2024；技术规格PDF第2页。
- 官方产品页：https://www.sungrowpower.com/en/products/string-inverter/sg125cx-p2
- 口径：最大交流视在功率125kVA；最大交流有功功率和中国效率规格书未给出；重量为≤93kg上界；日期只有版权年份；满载范围来自手册PDF第118页（印刷第111页）；欧洲中东非洲版；手册要求不同MPPT电压差小于80V；访问日期2026-10-05（美国洛杉矶）
- 满载来源：https://info-support.sungrowpower.com/cms/af994f1d-bb0d-408a-b310-6ad732402c99/GUID-A7FE8914-EB73-4237-B12A-12F4897634A0_1_en-US_PDF%20%28%E4%BA%A7%E5%93%81%E4%BF%A1%E6%81%AF%E8%AE%BE%E8%AE%A1%E9%83%A8_%E5%9F%BA%E7%A1%80%E7%89%88%29_1789023703700_compressed.pdf
- 满载来源版本：SG125_110_75CX-P2-UEN-Ver19-202510；PDF第118页。

| 字段 | 核实值 |
| --- | --- |
| inverter_id | sungrow-sg125cx-p2 |
| manufacturer | Sungrow |
| model | SG125CX-P2 |
| rated_ac_kw | 125 |
| max_ac_kw | 规格书未给出 |
| max_ac_kva | 125 |
| max_dc_voltage_v | 1100 |
| mppt_min_v | 180 |
| mppt_max_v | 1000 |
| full_load_mppt_min_v | 550 |
| full_load_mppt_max_v | 850 |
| start_voltage_v | 200 |
| mppt_count | 12 |
| strings_per_mppt | 2 |
| max_input_current_per_mppt_a | 30 |
| max_short_circuit_current_per_mppt_a | 40 |
| max_efficiency_pct | 98.5 |
| weighted_efficiency_pct | 98.3 |
| weighted_efficiency_type | European |
| weight_kg | 93 |
| grid_frequency_hz | 50/60 |
| datasheet_version | Version 6 |
| datasheet_page | 2 |
| datasheet_date | 2024 |
| full_load_source_version | SG125_110_75CX-P2-UEN-Ver19-202510 |
| full_load_source_page | 118 |
| assumptions_note | 最大交流视在功率125kVA；最大交流有功功率和中国效率规格书未给出；重量为≤93kg上界；日期只有版权年份；满载范围来自手册PDF第118页（印刷第111页）；欧洲中东非洲版；手册要求不同MPPT电压差小于80V；访问日期2026-10-05（美国洛杉矶） |

### SUN2000-50KTL-M3

- 规格书：https://solar.huawei.com/-/media/Solar/attachment/pdf/eu/datasheet/SUN2000-50kTL-M3-Datasheet.pdf
- 版本：规格书未给出；日期：规格书未给出；技术规格PDF第2页。
- 官方产品页：https://solar.huawei.com/en/products/SUN2000-50KTL-M3/
- 口径：重量含安装板；满载MPPT范围及中国效率规格书未给出；每MPPT两串由规格书第1页电路图核实并与8输入4MPPT交叉核对；IEC版；PDF元数据创建时间2022-10-08不是发布日期；访问日期2026-10-05（美国洛杉矶）

| 字段 | 核实值 |
| --- | --- |
| inverter_id | huawei-sun2000-50ktl-m3 |
| manufacturer | Huawei |
| model | SUN2000-50KTL-M3 |
| rated_ac_kw | 50 |
| max_ac_kw | 55 |
| max_ac_kva | 55 |
| max_dc_voltage_v | 1100 |
| mppt_min_v | 200 |
| mppt_max_v | 1000 |
| full_load_mppt_min_v | 规格书未给出 |
| full_load_mppt_max_v | 规格书未给出 |
| start_voltage_v | 200 |
| mppt_count | 4 |
| strings_per_mppt | 2 |
| max_input_current_per_mppt_a | 30 |
| max_short_circuit_current_per_mppt_a | 40 |
| max_efficiency_pct | 98.5 |
| weighted_efficiency_pct | 98 |
| weighted_efficiency_type | European |
| weight_kg | 49 |
| grid_frequency_hz | 50/60 |
| datasheet_version | 规格书未给出 |
| datasheet_page | 2 |
| datasheet_date | 规格书未给出 |
| full_load_source_version | 规格书未给出 |
| full_load_source_page | 规格书未给出 |
| assumptions_note | 重量含安装板；满载MPPT范围及中国效率规格书未给出；每MPPT两串由规格书第1页电路图核实并与8输入4MPPT交叉核对；IEC版；PDF元数据创建时间2022-10-08不是发布日期；访问日期2026-10-05（美国洛杉矶） |

### SUN2000-115KTL-M2

- 规格书：https://solar.huawei.com/admin/asset/v1/pro/view/3159c4e8755b497cbdd47e7ca7020d19.pdf
- 版本：规格书未给出；日期：规格书未给出；技术规格PDF第2页。
- 官方产品页：https://solar.huawei.com/admin/asset/v1/pro/view/3159c4e8755b497cbdd47e7ca7020d19.pdf
- 口径：效率取400V档；重量为≤93kg上界含安装板；满载MPPT范围及中国效率规格书未给出；IEC版；PDF元数据创建时间2025-07-15不是发布日期；访问日期2026-10-05（美国洛杉矶）

| 字段 | 核实值 |
| --- | --- |
| inverter_id | huawei-sun2000-115ktl-m2 |
| manufacturer | Huawei |
| model | SUN2000-115KTL-M2 |
| rated_ac_kw | 115 |
| max_ac_kw | 125 |
| max_ac_kva | 125 |
| max_dc_voltage_v | 1100 |
| mppt_min_v | 200 |
| mppt_max_v | 1000 |
| full_load_mppt_min_v | 规格书未给出 |
| full_load_mppt_max_v | 规格书未给出 |
| start_voltage_v | 200 |
| mppt_count | 10 |
| strings_per_mppt | 2 |
| max_input_current_per_mppt_a | 30 |
| max_short_circuit_current_per_mppt_a | 40 |
| max_efficiency_pct | 98.6 |
| weighted_efficiency_pct | 98.4 |
| weighted_efficiency_type | European at 400 V |
| weight_kg | 93 |
| grid_frequency_hz | 50/60 |
| datasheet_version | 规格书未给出 |
| datasheet_page | 2 |
| datasheet_date | 规格书未给出 |
| full_load_source_version | 规格书未给出 |
| full_load_source_page | 规格书未给出 |
| assumptions_note | 效率取400V档；重量为≤93kg上界含安装板；满载MPPT范围及中国效率规格书未给出；IEC版；PDF元数据创建时间2025-07-15不是发布日期；访问日期2026-10-05（美国洛杉矶） |

## 版本与日期解释

阳光版本和版权年份均明确印在规格书页脚。文件名日期不直接当发布日期：SG50规格书URL含DS_20231219（PDF元数据创建2023-12-19），SG125含DS_20240709（PDF元数据创建2024-07-10）。华为两个PDF未明示规格书版本或发布日期，故对应CSV列均为“规格书未给出”，不将搜索引擎日期、上传时间、PDF创建时间当作发布日。

SG50官网韩国页当前的Datasheet链接指向印度Version16；为避免区域额定条件混用，导入采用另一个官网英文IEC Version4原始PDF，额定50kW、最大视在55kVA，手册基础版本核对一致。SG50四路与每路两串、160–1000V、30/40A、98.5/98.3%、41kg均来自SG50型号列，非SG40列。

华为50满载范围在本次规格书未给出；父任务提供的中文用户手册EDOC1100248707不是本次已下载的原始PDF，未用其未核实内容补数。华为50两串/路已由官方PDF电路图和总输入数核实。

## T23 江苏分时电价检索未采用说明
访问日期2026-10-05。未检得省发改委官网苏发改价格发〔2025〕426号完整原件。
省发改委《关于开展2026年电力市场交易工作的通知》苏发改能源发〔2025〕1141号，发文2025-12-03，发布2025-12-19，
https://fzggw.jiangsu.gov.cn/art/2025/12/19/art_51012_11702429.html
第三节第5条引用426号但无完整分时段；南京市官网转发不符合任务卡要求，未采用。
结论：缺官方来源，未做；不新增峰谷CSV，自用电价沿用0.65元/度示意。

## T26

访问日期：2026-10-06。仅引用下列原始厂家参数及必要短表，PDF全文未复制入仓库；版权归原厂，未声明开放许可。产品结果为指定工况参考，不是采购匹配、敷设合格或寿命保证。

| 资料 | 原始来源、版本及页码 | 本项目用途与条件 |
| --- | --- | --- |
| Nexans / La Triveneta NPE SUN H1Z2Z2-K | [4mm² 180021101](https://latrivenetacavi.nexans.com/.rest/catalog/v1/product/pdf/180021101)、[6mm² 180023101](https://latrivenetacavi.nexans.com/.rest/catalog/v1/product/pdf/180023101)、[10mm² 180025101](https://latrivenetacavi.nexans.com/.rest/catalog/v1/product/pdf/180025101)，均PDF/印刷第2页；文件生成2026-10-06，未列独立发行日期或修订号 | 两根带载贴面相触44/57/79A；导体120°C、环境60°C。120°C仅对应20000h热耐久条件，不能解读成25年额定保证。 |
| ABB Electrical installation handbook | [原PDF](https://library.e.abb.com/public/7a93440e8c790852c125716c0033f7a9/1SDC010002D0204.pdf)，第4版，2006-03，卷2印刷标识1SDC010001D0204；PDF320/印刷260–261，Annex E | 铜ρ20=0.0175Ω·mm²/m、α20=.00395/K，ρ(T)=ρ20[1+α20(T−20)]。本项目DC120°C、AC90°C为导体温度假设；理想铜值不等于产品最大直流电阻。 |
| ABB Technical Application Papers No.10 Photovoltaic plants | [原PDF](https://library.e.abb.com/public/737452eca2644a16afb7b1e70f4ccf60/1SDC007109G0202%20QT10%20EN%202014.pdf)，1SDC007109G0202，03/2014，PDF35/印刷33，§3.4.2式3.4；PDF113/印刷111算例 | Ib=1.25Isc；光伏1–2%压降为厂家设计建议。DC2%是本项目在建议范围内的取值，不是中国强制规范限值。 |
| Prysmian Low Voltage Power Cable SEA | [原PDF](https://asean.prysmian.com/sites/asean.prysmian.com/files/media/documents/Prysmian_LVCables_SEA.pdf)，表C3.4，PDF215/印刷429；未见版本号、发行年月；PDF元数据生成2025-11-19，非发行日期 | 多芯无铠装、铜、90°C XLPE/EPR、3ph、木墙表面穿管、空气30°C。截面6/10/16/25/35/50/70/95/120/150/185mm²对应44/60/80/105/128/154/194/233/268/300/340A。 |
| Schneider Electric Electrical Installation Guide | [三相压降公式](https://www.electrical-installation.org/enwiki/Calculation_of_voltage_drop_in_steady_load_conditions)，2026-08-05修订，oldid29653，Fig.G29 | ΔU=√3I(Rcosφ+Xsinφ)L；本项目400V、PF1，故忽略电抗项。AC2%为项目设计假设，未声称规范强制值。 |

实际成束、穿管、桥架、气温和导体温度未核定，载流量必须按现场敷设条件及原厂降容表复核；不得将未知条件说成已验证。DC公式采用STC Imp、Isc、N×Vmp；真实温度工作点和接插件电阻未模拟。

长度为横竖折线，不绕障碍物。DC串内跳线与正负两端导体各计一次，乘1.1富余；等效单程=导体总长/2，因此2ρLI/(S×串工作电压)不会重复计算正负线。AC四芯按路线米统计，另存4倍导体米，屋面加屋顶高度与5m落地余量；这些几何简化和富余均为示意。两种接法比较使用DC导体米与AC四芯路线米之和。

手工逆变器点作为可共用的放置位置，各台按所接组件中心选择最近点；未给则投影屋面最近边。并网点未给则投影各逆变器平均位置至屋面边界，结果逐点标明默认或手工。分阴影类别阈值>3%、改善至少1个百分点、电缆增长不超过10%均为任务设计假设。类别不足成串则合并；保持原选定逆变器型号和台数且不增加未接板。发电仍按每块板单独计算，未模拟串内失配，不因改接线增加发电或改变经济结果；电缆造价留待T30。

## T27 N型组件与东西向示意支架

访问日期：2026-10-06。以下参数来自原始厂家规格书与NREL官方SAM，未用经销商材料。厂家PDF版权归原厂，仅引用必要参数；SAM库沿用 data/catalog/LICENSE-SAM.txt。不承诺双面背侧增益。

| 数据 | 原始来源、版本、页码与日期 | 用途 |
| --- | --- | --- |
| 天合605W N型i-TOPCon，TSM-NEG19RC.20 / 605 W | [官方PDF](https://static.trinasolar.com/sites/default/files/DT-M-0045%20E%20Datasheet_Vertex_NEG19RC.20_EN_2024_A_E1_print.pdf)，TSM_EN_2024_A_E1，第1页N型、第2页参数；版权2024，独立发布日期未载明；PDF创建2024-04-11不是发行日证明 | 2.382×1.134m、33.7kg、40.5V/14.94A、48.7V/15.83A、NOCT43±2°C；132半片；厂家系统1500V、熔断35A；NMOT与Vmp温度系数未给出。 |
| 晶科605W Tiger Neo N型，JKM605N-66HL4M-BDV | [官方PDF](https://www.jinkosolar.com/uploads/JKM600-625N-66HL4M-BDV-F1-EN.pdf)，JKM600-625N-66HL4M-BDV-F1-EN，第1页N型、第2页参数；版权2022，发布日期未载明；PDF创建2023-09-18非发行日证明 | 2.382×1.134m、32.4kg、40.31V/15.01A、48.48V/15.90A、NOCT45±2°C；132半片；1500V、35A；NMOT与Vmp温度系数未给出。 |
| NREL/SAM CEC Modules | [固定原CSV](https://raw.githubusercontent.com/NREL/SAM/cba319ded1c32a7f5b3ac76545a29e1f7181d238/deploy/libraries/CEC%20Modules.csv)，[官方提交](https://github.com/NREL/SAM/commit/cba319ded1c32a7f5b3ac76545a29e1f7181d238)，提交时间2026-07-01T00:57:04Z；两行Version=2026.7.3、Date=6/23/2026；CSV含头第8313/18706行 | 精确追加Jinko Solar Co Ltd JKM605N-66HL4M-BDV及Trina Solar TSM-605NEG19RC20原行。全库SHA256仍为a28cf8956a839ed98bb941809b439e4907f5b4c237bd9299bc123fb502c29aff；子集增加行后必须使用新真实文件哈希。 |

CEC字段为官方拟合模型，保留A_c、T_NOCT、温度系数和单二极管参数原值；不强改为厂家测值。Jinko CEC N_s=22不是物理电池片数，不改为66/132。天合CEC省略型号中的点号，605W档和四项STC电气值与该规格书对应。

b/b_tmy按项目所选组件计算；参考Trina550保留22×6，两个605W采用20×6，同为72.6kWp。已有Runergy550采用19×7=73.15kWp。参考效率逆变器CEC Paco=60182W，MPPT550–850V；三种串电压为695.2V、810/806.2V、797.24V，均按原始CEC值验证。仅为保持近似相同DC/AC的效率参考阵列，安装接线仍由项目电气规则独立计算。

ballast_ew每块支架6kg、压块30kg、支架造价100元均为**示意估数**，无厂家、风荷载或采购报价依据，防腐规格待厂家提供；已登记racking.csv及costs.csv，T30前不改变全系统示意单瓦造价算法。EW默认10°、允许5–15°、每4组留检修通道为本卡示意布置条件。

## T30：分项、分时电价、税贷与资格（2026-10-06核查）

以下资料由本批官方来源研究取得原件，并由Root在2026-10-06二次复核；原件在本批Temp研究目录，仓库只登记有限事实。访问日期均2026-10-06。已查证来源不等于项目已有资格、报价、并网承诺或融资合同。

| 原始来源、版本、公布日期与定位 | 用途和边界 |
|---|---|
| [江苏426原件](https://fzggw.jiangsu.gov.cn/art/2025/4/30/art_284_11557001.html)，苏发改价格发〔2025〕426号，成文2025-04-25/公布04-30，表1、表3，2025-06-01执行 | 工商业春秋/夏冬时段、峰谷比例及315kVA工业尖峰深谷。19:30边界按小时均拆两半小时示意；容量推断类别可改，基本电费不计收益。 |
| [江苏1141](https://fzggw.jiangsu.gov.cn/art/2025/12/19/art_51012_11702429.html)，苏发改能源发〔2025〕1141号，成文2025-12-03/公布12-19，三(5)、四(八)(2) | 继续引用426；已约定分时零售套餐不重复叠加；机制电量不得重复绿证收益。 |
| [2023假期原件](https://app.www.gov.cn/govdata/gov/202212/08/495070/article.html)，国办发明电〔2022〕16号，2022-12-08，正文 | 2023天气年春节1/21–27、五一4/29–5/3、合并中秋国庆9/29–10/6作为深谷窗口。 |
| [CPIA路线图原件](https://www.chinapv.org.cn/html/uploads/files/20260213213747175.pdf)，2025–2026年版，2026-02-05发布/02-13开放下载，PDF65/印55、PDF66/印56图72脚注15 | 2.59元/W总投资参考、0.046元/(W·年)基础运维已查证，运维不含固定资产更换。图72没有分项数值标签；costs.csv具体单价全部示意。SHA256 2a0638d07a43f884253676b3ee8a9cad9031246b0265acda436d37a0d464ada4。10/8 按用户要求造价不偏乐观：costs.csv另设“其他费用（未单列）”0.70元/W（2.59减12个真实园区分项合计中位数1.89，示意校准），普通屋顶总价约2.59元/W，翻新、锚栓、10千伏接入或钢构时更高。 |
| [江苏新能源方案原件](https://fzggw.jiangsu.gov.cn/art/2025/10/21/art_51007_11659583.html)，苏发改规发〔2025〕5号，2025-10-15成文/10-21公布，二(二)、三(一) | 2026-01-01起至2030-12-31；机制量与市场价差额结算，机制量不重复绿证。默认机制比例0，0.391元/kWh仅示意市场价。 |
| [竞价通知](https://fzggw.jiangsu.gov.cn/art/2025/11/11/art_284_11672928.html)，苏发改价格发〔2025〕1055号，2025-11-11，二、三 | 0.25–0.391是竞价范围，10年是公告期限，均不证明本项目入选。未取得1208官方结果，未采用商业转载0.36。 |
| [国网江苏](https://js.sgcc.com.cn/)，目标2026-10代理购电完整到户表 | 官网TLS访问失败，未取得1–10kV单一/两部制正式全表，保留0.65示意；不能用购电分量代替总到户价。检索js.sgcc.com.cn、sgcc.com.cn、95598.cn、jiangsu.gov.cn、changzhou.gov.cn、jintan.gov.cn；不是不存在公告的证明。 |
| [绿证107号](https://www.nea.gov.cn/20260107/9a905f263a8b4aa4a06e1a96855cc8eb/c.html)，国能发资质规〔2025〕107号，2025-11-28成文/2026-01-07公布，第14、16、17、19、25条 | 实发电量每1000kWh一张；模拟核发不是已核发，自用不可交易，弃电不计核发；交易量扣除机制和已售绿电。 |
| [能源局2026-08统计](https://www.nea.gov.cn/20260930/8cee035ddfd7417fbea02b55cc386469/c.html)，2026-09-30，二第三段 | 2026生产年份单独绿证全国成交均价6.32元/个，只是未来价格估算参考。 |
| [增值税法](https://shanghai.chinatax.gov.cn/sjtax/ztzl/yshj/ldjj/202412/t474700.html)，2024-12-25通过/12-27页面公布，第8、10、14、16条；[条例826号](https://fgk.chinatax.gov.cn/zcfgk/c100010/c5246349/content.html)，2025-12-25成文，第2条，均2026-01-01施行 | 一般纳税人售电13%，含税销项13/113；有合法票据硬件抵进项；自用节省无售电销项；不动产租赁9%。 |
| [企业所得税法](https://12366.chinatax.gov.cn/bzds/054/054-5-1.html)，第4条；[现行实施条例](https://fgk.chinatax.gov.cn/zcfgk/c100010/c5194417/content.html)，2007-12-06公布，含2019-04-23/2024-12-06修订，第59、60、87条 | 普通企业25%；直线折旧，20年/5%残值为本卡示意非统一法定；三免三减半默认关闭，内部自建自用被排除。更换折旧、损益与税亏处理简化在方案书公开。 |
| [中国货币网LPR第一方JSON](https://www.chinamoney.com.cn/r/cms/www/chinamoney/data/currency/bk-lpr.json)，[官方页面](https://www.chinamoney.com.cn/chinese/bklpr/)，showDateCN原样2026-09-20 9:00 | 5年期以上3.50%；未编造9月21日发布日期，非实际合同利率。 |
| [能源局2025问答原件](https://www.nea.gov.cn/20250411/dca28f9186e848dda1d690d192fa50f8/20250411dca28f9186e848dda1d690d192fa50f8_113000de00999043e8a7fe4446dd6d97d8.pdf)，2025-04-11，PDF34–35/印26–27第61、62问 | 新项目四可能力已查证；每项目1套与费用示意。Q/GDW1480-2015及480-2010原始技术全文未取得，400kW/6MW接网阈值仍示意；PDF10/印2管理分类不当作技术承诺。 |
| [常州212细则](https://www.changzhou.gov.cn/gi_news/761175757477244)，常发改〔2025〕212号，2025-09-09公布施行，第11–13、21条 | 常州公共机构、上一年并网审核、无重复市级以上支持且信用安全环保合格，投资企业一次性0.3元/W；无固定终止日，不套普通厂房。 |
| [江苏695](https://fzggw.jiangsu.gov.cn/art/2026/7/29/art_84097_11809969.html)，苏发改能源发〔2026〕695号，成文2026-07-21/公布07-29 | 未给普通工商业普惠光伏每瓦/度补贴。检索jiangsu.gov.cn、fzggw.jiangsu.gov.cn、changzhou.gov.cn、fgw.changzhou.gov.cn、czj.changzhou.gov.cn；默认“未查到本项目符合的现行普惠补贴，按0计”。 |

2026-10-06 Root二次官方限定检索“江苏2026分时电价426调整”“国网江苏2026年10月代理购电工商业用户电价”“江苏2025年第1208号新能源机制电价竞价结果”，重开426/1141；未得到替代表1/3的原件或新增可验证价格默认。0.65和0.391仍示意，具体分项设备报价、保险清洗、第13年更换、屋龄10年提醒线都标示意。

## T31：风压、分区、压块和夹具（2026-10-06）

示意，不能代替结构计算，施工前要由结构工程师按规范复核。本批官方来源研究核验如下；没有取得的原表不冒充已查证数据。

| 原始来源、日期与定位 | 实际用途和边界 |
|---|---|
| [住建部公告2021年第70号](https://www.mohurd.gov.cn/gongkai/zc/wjk/art/2021/art_17339_761192.html)，2021-04-09公布，GB55001-2021 §3.1.13，PDF13–14/印10–11；访问2026-10-06 | 有利永久作用分项系数取1、不利风作用取1.5；这是系数核验，不代表风压、体型或分区已核验。 |
| [国家标准全文公开系统](https://openstd.samr.gov.cn/bzgk/gb/index)，目标GB50009-2012附录E（目标表E.5）、粗糙度高度表和屋面分区图；访问2026-10-06 | 官方全文及页码未取得。13市全部暂取0.40kPa示意，不是附录E已核验值；站名和城市对应关系待核。最近市中心仅地理推定，不是行政归属。 |
| [SAMR行业标准元数据](https://std.samr.gov.cn/hb/search/stdHBDetailed?id=8B1827F14B84BB19E05397BE0A0AB44A)，NB/T10115-2018，2018-12-25发布、2019-05-01实施；访问2026-10-06 | 版本核验，斜放与东西向体型原表、页码、角度适用范围未取得；独立EW系数0.65仍示意。 |
| [S-5厂家ER-805原件](https://3482954.fs1.hubspotusercontent-na1.net/hubfs/3482954/Codes%20and%20Certifications/IAPMO.pdf)，2023-10-10原发、2025-09-15修订，Table1第8页；访问2026-10-06 | 560lbf按表注4.45N/lbf=2.492kN，仅S-5-S+Bridger Steel Tru Snap 24Ga、57.1ksi、基材厚0.0258in、扭矩130–150in-lb的ASD允许容量。没有默认套给本项目，也不与ULS风力混用。 |

当前示意方法：基本风压乘高度幂律、体型和阵风1.2；高度=屋面高度+组件实际最高z，幂律A/B/C/D指数0.2/0.3/0.44/0.6，高度下限5m，默认B且工业区可能C。普通平屋顶/东西向/金属屋面体型基数0.8/0.65/1；角/边/中乘1.6/1.3/1。以上均缺标准原表。分区宽min(屋顶最小旋转矩形短边×0.1,屋高×0.2)，有限边带相邻交集作角区，凹角补两边方向邻域；共线冗余点不制造角部。任意多边形推广仅示意。

法向风力F=p×实际组件面积×1000，U=Fcosβ、H=F|sinβ|。抗拔所需压块max(1.5U/9.81−组件及有效支架自重,0)；滑移所需max(1.5(U+H/μ)/9.81−自重,0)，默认μ=.5。取大者后按15kg向上取整；滑移摩擦扣除了上拔作用。EW两坡不相互抵消。压块目录旧30kg字段仅兼容旧档，当前真实设计和一期预算均用风结果。

质量按实际存活板和有效支架汇总，删除上/下层后的物理支架投影仍沿T27几何。逐架质量按其与分区相交面积比例分配；分母为所有架投影的union与该区相交面积，避免重叠面积重复。L01取分区最不利值，总平均另存。均布到架投影的模型不能推导支点局部应力。

通用夹具设计容量0.8kN、缝距0.5m、最小安装距离0.2m、最大允许间距1.2m、边距0.1m都为示意，须按厂家板型复核。需求=max(ceil(1.5U/容量),满足最大间距的实际点数,2)，可布数量来自实际屋缝/板形交线及三维最小间距。跨板点不重复、实际选点也检查最大间距，超出能力由硬规则W01失败；不能用“可布点数够”替代布点核验。导轨连接件45元/板、夹具5元/实际个数均待厂家报价。S-5挡雪系统间距未用作光伏间距。

分期安装先布一期夹具，再布二期；各期保持设计内原稳定板顺序。预算候选虽然按收益选板，计算实际点位时恢复设计顺序，使一期单算、全站中的一期、预算报价、现金流和材料表使用同一组实体点位。

分析摘要和只读项目摘要均返回完整示意原文、来源状态、最不利区及W01状态；适用金属屋面另给需求/实布/失败板数。旧档未存同版本风结果时明确unknown，不重新估算或声称已经核验。摘要限1920字节，超限只压缩可还原的删板建议范围，再省重复hint_zh/name_zh；稳定规则ID、等级、数值、限值、建议、hard_failed和风事实不因此删除，工具封装另留128字节。

## T33 空地与车棚（原文访问2026-10-06）

- 国家能源局《分布式光伏发电开发建设管理办法》，国能发新能规〔2025〕7号，成文2025-01-17、公布2025-01-23。
  [官方通知及DOC附件](https://www.nea.gov.cn/20250123/112c5b199c5f45dd8e7ac93c9f5e4eaf/c.html)。
  第二、四、五、十一、十七、十九条：建筑附属场所须同一用地红线，并同时满足分类、规划、场所合法及并网条件。
  不能凭ground类型自动认定分布式或合法建设；独立空地通常集中式，向当地发改/能源主管部门核实。
- [国家能源局政策解读](https://www.nea.gov.cn/20250123/d38e5436b4d04159863ddbc10a6ede10/c.html)，2025-01-23，第四部分（三），
  小型地面电站按集中式管理；该解释不排除同红线建筑附属场所依法满足分布式条件。
  2025年版《办法》问答2025-04-11，问答36 PDF第23页/印15、39 PDF第24页/印16：同红线附属闲置空地的用地简化条件不能外推到独立地面项目。
- [自然资办发〔2023〕12号官方全文](https://app.www.gov.cn/govdata/gov/202304/03/498835/article.html)，成文2023-03-20，政府网公开2023-04-03。
  一（二）、二（一）、三（二）、四（一）、五：新建方阵不得占用任何耕地（含一般耕地）；基本草原、保护林地、生态红线等另有禁限，其他土地也须当地确认。
  配套设施用地审批不等于允许方阵占耕地；存量过渡有已立项等前提，软件不认定适用。
- [JGJ100-2015官方原版扫描](https://jncc.jinan.gov.cn/cms_files/jcms1/web19/site/attach/0/ae49086858f94404be221c77b7b5c17b.pdf)，
  住建部公告788号，2015-03-30发布、2015-12-01实施；济南住建部门托管。
  表4.3.4 PDF26/印17：小型车倒车垂直停车净位宽2.4m、毗邻车位深5.1m、车道5.5m，属“宜”；邻墙深5.3m、前进停车车道9m不可混用。
  表4.1.1的1.8×4.8m为车身，不能当车位。表4.2.5 PDF22/印13与4.3.6 PDF27/印18的小型车2.2m净高为适用车库项目参照。
  未取得开放光伏车棚专门强制净高条款；G09是项目硬校核，不能称全国所有开放车棚依法强制2.2m。
- [GB55031-2022官方正文](https://ghzrzyw.beijing.gov.cn/biaozhunguanli/bzzl/202209/P020220929592779805981.pdf)，
  2022-07-15发布、2023-03-01实施，全部条文强制；本来源不证明所有开放棚统一2.2m。

平地、组件离地默认0.5m（允许0.3–3m）、4m道路、2m围栏退让、每架两桩、桩位置、0.2m柱径、0.6m结构带、0.3m竖向梁深、
2.5m默认梁底净高、5°棚面默认倾角、60kg/kW钢量且不低于12kg/m²棚面均为示意。地勘、基础抗拔、钢结构、消防及排水须设计方核定。
棚钢按生成时完整安装容量计量，删板或分期不拆棚；一期一次建设固定棚面/柱、道路与围栏，二期现金流为总计减一期。
围栏报价取原场地周长，实画内退边界长度另列；道路按真实面并集，地租按原面积/(2000/3)m²每亩，投资人年度支出三模式仅扣一次。
成本目录全部新增单价为示意；显式0地租有效。土地出租方税务未核定，不套屋顶租赁税率。未取得苏自然资函〔2023〕845号原件，不采用二手2.5m/8m数值。

## T34 养殖场与牧光（访问2026-10-07）

- 自然资办发〔2023〕12号，[政府网原文](https://app.www.gov.cn/govdata/gov/202304/03/498835/article.html)，
  成文2023-03-20、公开2023-04-03，第一（二）及第三（二）节（网页无页码）：新建方阵不得占用任何耕地、基本草原。
- 办草字〔2023〕126号，[陕西林业局官方附件](https://lyj.shaanxi.gov.cn/zwxx/tzgg/202310/P020231027360098481750.pdf)：
  成文2023-09-25，PDF第2页：降雨小于250mm对应1m、250–400mm对应2m，适用文件规定的草原项目；
  第3页规定由地方分类认定；不是全国羊/牛统一高度，不能移用为江苏统一要求。
- ArcelorMittal《Magnelis High-level corrosion protection in agricultural environments》，12/2023，PDF第2页：
  [厂家PDF](https://amiresources.arcelormittal.com/strapidata/uploads/Magnelis_Agriculture_leaflet_EN_122da74cf7.pdf)。
  20℃、5wt%氨水24小时是材料试验；不证明整套夹具、螺栓、切边和异种金属组合的耐氨认证。
- [日本制铁ZAM化学耐性](https://www-zam.nipponsteel.com/product/zam/en/quality/chemical/)：22℃、5%氨水24小时，切边及底面密封。
  页面无版本日期；试验边界不能忽略。
- [IEC62716:2013官方目录](https://webstore.iec.ch/en/publication/7392)，2013-06-27，Edition1.0，含2014-05勘误：对象是光伏组件。
  未取得付费正文，不用于证明支架、夹具或电缆已认证，也不宣称统一C4/C5等级。

养殖棚采用镀铝锌镁夹具与导轨为示意选型，加价20%：实际抗风夹具6元/个、导轨连接件54元/块。
通风口/天窗预设默认四周1m，仅缺省时采用，显式0保留；全楼/逐面禁装和玻璃禁装仍按实际几何。
风机班次4按七天运行，08–20时，6–9月1、春秋0.6、冬0.3、夜0.2，各月独立归一至月用电量。
清洗仅未填写时采用普通默认频次两倍；显式0不覆盖。手填自用比例在普通允许上网未分期时优先；不上网或分期使用共同实际负荷。

羊1.5m、牛2.5m和地面最低50%受光均为示意，既有/手填低高度不抬高掩盖G08。
G10采用2023年当地每月15日hh:30、太阳高度大于0的样本；实际组件和障碍物投影到z=0，阴影并集裁原场地。
按月天数及每样本1小时加权，总阴影面积时/原场地面积时计算；只存12个月摘要，不是PAR、产草量或牲畜舒适度预测。
加大排距通过真实重新排板改变几何；场外树木、场地边界和障碍基底进入地影，遮挡不重复累计。
防牲畜围栏120元/m替换普通围栏，报价按原轮廓周长，内退实际画线长度另列。
DC防啃附加3元/导体米，采用T26实际DC导体米及既有1.1富余，不再次乘2或1.1；一期按自己的实际导体量。
穿管/埋地载流量降容及施工规格须专业设计，示意加价不构成电气认证。
放牧节约仅为基础运维×除草份额20%×替代率50%，不减少保险、清洗、更换、融资或地租；全部费用为示意。

## T35 串联布线路径（2026-10-07）

本次无新增外部规格书、法规或电价数据；电阻、载流量、温度与压降取值沿用T26官方来源。
路径算法为项目自身实现：限制在屋面/场地内的横竖折线，直接折线失败时在障碍顶点坐标网格搜索。
设备外扩0.05m是显示/估算假设，不是施工净距要求；圆形设备按外接方框保守避让，玻璃和禁区避让。
固定组串成员、朝向、逆变器和MPPT；比较原顺序与最近邻加最多四轮2-opt候选的实际可达路径长度。
不是全局最优证明，也不用于宣称增发电收益；现场桥架、穿管、防火、支撑及净距仍须工程确认。
DC按完整连接链的导体长度乘1.1一次；屋面未计组件接头短引线，显示抬高不进入工程量。
多坡沿面分段；新建场地同架随面、异架落地。AC屋面至地面的垂直段进入route_3d；5m接线余量只进计量。
route_m为几何线路长；AC length_m为route_m加5m，conductor_m为四芯导体米，不混作路线米。
不可达时不生成穿障碍路径；长度为未绕障碍的下界估算，E10/E11失败，不能作为可施工报价。
节省量只在原顺序与选定DC路线都可达时比较；缺少比较条件用null，不虚报节线量。

## T36 安装包压缩与方案书排版（2026-10-07）

- [Inno Setup 官方 Compression 文档](https://jrsoftware.org/ishelp/topic_setup_compression.htm)：
  HTML在线帮助，未标独立发布日期/版号，无印刷页码；核对 `[Setup]: Compression` 参数及内存表，访问2026-10-07。
  本项目固定构建工具Inno Setup 6.7.3。采用 `lzma2/ultra64`，默认64MB字典；官方近似压缩内存742MB、解压字典64MB。
  更高压缩等级可能增加构建时间与内存，不把压缩等级视为最终大小保证。
- [Inno Setup 官方 SolidCompression 文档](https://jrsoftware.org/ishelp/topic_setup_solidcompression.htm)：
  同为无独立版本日期/页码的HTML在线帮助，核对 `[Setup]: SolidCompression`，访问2026-10-07。
  保留 `yes`；共同内容有利于整体压缩，解压重试可能需要重读压缩流。
- 两项均为官方说明的实现依据；仅引用链接和释义，不复制第三方代码或文档。
  沿用项目原有Inno Setup许可记录，不引入依赖或字体。
- 195MB来自用户本次要求，采用十进制且严格小于195,000,000字节；不是外部标准。
  A4章节、图表编号及颜色为本项目文档样式，不宣称经过工程标准认证。
  经济、电气、结构数值及来源沿用原归档；显示舍入保留原值，不改计算口径。
