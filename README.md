# 光筑 · 工厂屋顶光伏方案自动设计 Agent

2026 江苏省高校 AI+科学与工程创新实践黑客松 · 本科生组 · U058「验形工坊」

光筑是工厂屋顶光伏设计智能体，可自动排布、测算发电与收益，经独立审核输出方案书、图纸和材料清单。

原创代码采用 [MIT 许可证](LICENSE)。从源码安装及离线复现见 [复现指南](docs/REPRODUCING.md)，配置示例见 [settings.example.json](desktop/settings.example.json)，第三方许可见 [第三方声明](THIRD_PARTY_NOTICES.md)。按比赛“获奖代码库开源”条款的逐项核对见 [开源检查记录](docs/OPEN_SOURCE_CHECKLIST.md)。

作品内容、实现方案、核心功能与技术亮点见[作品详情](docs/project-description.md)；[提交表文本](docs/materials/submission-form.txt)提供 50 字以内简介和 5000 字以内详情。

选一栋厂房屋顶（也可以导入它的图纸，或者在软件里画出来；彩钢瓦、斜屋面、空地、车棚、养殖棚也行），写一句"6 年内回本，留 1 米检修通道"，光筑就在 **AGH（Agnes Harness）** 里让 DeepSeek 一次做完排板、阴影、发电、电气和串联布线、风荷载、经济和规范核对，再由 Agnes 在另一个会话里独立审核，最后给出方案书 PDF、CAD 排布图（DXF）和材料清单（XLSX）。要求做不到时，它会停下来说清楚为什么、可以怎么放宽。

## 三步用起来

1. **安装**：从 [Releases](https://github.com/3531st-lab/guangzhu/releases/latest) 下载 `guangzhu-setup.exe`（约 149 MB，Windows 10/11 64 位，不需要管理员权限），双击安装。安装程序会配好光筑自带的 AGH、设计工具和插件，并做一次离线计算自检。安装包没有数字签名，Windows 提示"已保护你的电脑"时选"更多信息 → 仍要运行"。SHA256：`19E7BE68A43B512839A6CFFDED1C2BA470820F5F778B52935E7BB2E791EEF146`。
2. **填 key**：打开桌面上的"光筑"，在首页最上面填一家模型的 key：DeepSeek、Agnes，或 AGH 支持的其他服务商。key 经插件交给 AGH 官方接口验证和保存，光筑的后台、文件和日志都不经手 key。不填 key 也能打开随包的真实案例，看 3D 结果和执行记录回放。
3. **设计**：选屋顶（演示屋顶、12 栋真实厂房轮廓，或「＋ 新建屋顶」自己画、导入图纸，示例图纸在 [`samples/sample-drawing/`](samples/sample-drawing/)）→ 填一句要求 → 开始自动设计。右边是 AGH 原生会话；设计工具第一次审批选「本会话允许」，导出选「仅允许这次」。2026 年 10 月 11 日苏州示意屋顶案例中，设计约 5 分 03 秒，Agnes 独立审核约 1 分 48 秒；实际耗时随模型、缓存和网络变化。完成后在结果页看 3D 方案、三方案对比和规则核对，打开方案书。

## 怎么工作

```
光筑生成任务书 ──(光筑插件，AGH 插件 SDK)──→ AGH 会话（DeepSeek V4 Pro）
  ① 任务规划：读设计 Skill（.agh/skills/pv-rooftop-design），先写计划
  ② 能力调用：通过 MCP（stdio）调用 12 个 gz_ 工具：建项目 → 存需求 → 取天气 → 排板 → 分析
  ③ 反馈处理：按不通过的规则修改方案 → 重新分析，最多迭代 6 轮；无法满足时说明原因
  ④ 结果验证：三方案选定 → 最终分析 → 发电五链复核 → 人在审批卡上批准导出
  ⑤ 独立审核：另开一个 AGH 会话，模型换成 Agnes（agnes-3.0-flash），只读复算并保存审核意见
  ⑥ 核对：导出两个会话的 AGH 原生执行记录，按记录逐条检查四步和审核
```

所有模型调用都只在 AGH 会话里；光筑后台只生成任务书、显示进度和结果、生成方案书，不调用模型。

## 苏州演示案例

2026 年 10 月 11 日的苏州自建示意屋顶案例中，用户要求“6 年内回本，留 1 米检修通道，避开天窗”。系统识别初稿遮挡问题，删除 26 块遮挡超限组件后重新计算，最终批准导出 v2：

| 指标 | 结果 |
| --- | --- |
| 组件与装机 | 725 块，438.625 kWp |
| 预计年发电量 | 约 52.02 万 kWh |
| 估算投资与静态回本 | 约 111.90 万元，约 4.70 年 |
| 规则与审核 | 25 条检查中 19 条通过、6 条不适用，0 条硬性失败；Agnes 独立审核通过 |
| 交付 | 同版 PDF 方案书、DXF 排布图、XLSX 材料清单及原生运行记录已归档于参赛提交包 |

以上是给定图纸、天气与示意参数下的初步测算。屋面设备、承重和部分经济参数为示意输入，实际项目需结合现场勘测、用电曲线及结构和并网条件复核。仓库中的常州执行记录见下文，苏州案例的完整成果与记录随参赛提交包提供。

## 能做什么

| 功能 | 说明 |
| --- | --- |
| 一键设计 | DeepSeek 在 AGH 会话里调用光筑的设计工具：建项目、取天气、排板、综合分析、修改方案、三方案对比、发电复核、导出；不满足要求就自己改 |
| 独立审核 | 另开一个 AGH 会话，由 Agnes（或任何已配置的模型）复算并给结论，审核意见原样写进方案书 |
| 屋顶输入 | 混凝土平屋顶、彩钢瓦、整栋斜屋面、空地、车棚、养殖棚和牧光互补；软件里按尺寸画、点角画，或导入图片、PDF、DXF 图纸 |
| 排法和倾角 | 按所在地全年天气算最佳倾角；正南、顺屋边、东西向人字形三种排法 |
| 躲开阴影 | 屋面设备、女儿墙、前后排以及屋顶外的楼和树，全年逐块组件光线追踪 |
| 三方案 | 多装、最快回本、折中三套，生成时就满足硬性要求；点方案名，3D 换成那一套 |
| 电气和布线 | 组串电压电流校核；每串按实际走线算电缆长度、截面和压降 |
| 风荷载与固定 | 按基本风压分角区、边区、中区算压块，超过屋面承重改用锚栓 |
| 规则 | 共 32 条，按屋面类型和工况适用（平屋顶用到 25 条）：冬至不遮挡、组串电压电流、荷载、电缆压降，以及检修通道、留空、装机、预算、回本等业主要求 |
| 投资测算 | 分项造价（普通屋顶约 2.59 元/W）；江苏分时电价（苏发改价格发〔2025〕426 号）逐时算自用；税、贷款、运维；自投、合同能源管理、屋顶租赁三种方式的 25 年账 |
| 园区 | 多栋厂房画在一张总图上，算楼间遮挡，排队批量设计，汇总装机、发电和回本 |
| 交付件 | 方案书 PDF、DXF 排布图、XLSX 材料清单，都带 SHA256；每次运行的执行记录可以回放、重新核对 |

## 怎么证明算得对

- **太阳位置**：和美国海军天文台（USNO）官方数据比 29 个时刻，高度角最大差 0.0043°、方位角最大差 0.0025°（合格线 0.05°）；日出日落和 USNO 比最大差 0.50 分钟，和中国天气网江苏 13 个市比最大差 1.59 分钟。复算（离线，用仓库里存的官方原始响应 `data/field/sun-official/`）：`python scripts/check_official_sun.py`，对照表写在 [`reports/assets/T12/sun-official.md`](reports/assets/T12/sun-official.md)。
- **真实电站**：和 NREL PVDAQ 公开数据里一座 893 kW 真实电站（2107 号，2022 全年）比，不调参数，用电站实测斜面辐照时月发电平均误差 5.1%。逐月结果在 [`data/field/plant/2107-monthly.csv`](data/field/plant/2107-monthly.csv)，清洗规则见 [`data/field/plant/README.md`](data/field/plant/README.md)；从 NREL 公开数据重新下载并复算：`python scripts/compare_plant.py --download`。
- **发电计算链**：pvlib 计算链和 NREL PySAM（PVWatts v8）同参数相差约 0.5%；发电复核工具 `gz_crosscheck_yield` 对五条计算链进行交叉复核。
- **历史评测（2026-10-03，DeepSeek Flash）**：当日冻结的 24 个屋顶任务包含 12 个正常、6 个边界和 6 个不可行任务。18 个可行任务各运行 3 次，完整 Agent 成功 51/54 次，约 94%；不用 AI 的默认排板成功 1/18 次。6 个不可行任务各运行 3 次，18/18 次识别不可行、0 次谎称完成，15/18 次放宽建议经复核有效。该成绩对应当时的模型、版本与评测口径，不作为当前版本成功率。当前用例见 `eval/cases.json`，真实厂房轮廓的取数和挑选规则见 [`data/roofs/README.md`](data/roofs/README.md)；驱动和打分为 `scripts/eval_run.py`、`scripts/eval_score.py`。
- **执行记录**：[`runs/gz-changzhou-demo-1008-2113`](runs/gz-changzhou-demo-1008-2113) 是一次真实运行的完整存档（安装包里随包附带的真实案例）：AGH 原生执行记录 `ledger.agnes.jsonl`、核对结果、各版本、方案书。从原生记录重新核对：

  ```powershell
  .\.venv\Scripts\python.exe scripts\agh_verify_run.py runs\gz-changzhou-demo-1008-2113\captures\fff0c410d7ef366cd4d3 --review-run runs\gz-changzhou-demo-1008-2113\reviews\42cd14cf5d1c2743bc94
  ```

## 开发者

### 目录

| 位置 | 内容 |
| --- | --- |
| `backend/guangzhu/` | 计算和工具：排板、阴影、发电、电气、规则、经济、MCP 工具进程（`python -m guangzhu.mcp_server`）、本机后台 |
| `desktop/` | 桌面窗口（pywebview + WebView2）和页面；`desktop/launcher/` 编译成"光筑.exe" |
| `agh-plugin/guangzhu-studio/` | AGH 插件：任务书、工具结果卡片、和桌面页面传话 |
| `.agh/skills/` | 给 Agent 的设计 Skill（一键模式的步骤和规矩） |
| `data/` | 演示和评测屋顶、天气快照、设备目录、官方对照数据 |
| `eval/` | 24 个评测屋顶的题目和标准答案 |
| `scripts/` | 环境安装、核对器、评测、安装包构建、官方数据对照 |
| `installer/` | 安装包脚本（Inno Setup） |
| `tests/` | 自动测试 |
| `docs/` | 作品详情、提交表文本和第三方数据来源 |

### 从源码运行

Windows 10/11 x64、Python 3.12，先克隆仓库并安装锁定依赖：

```powershell
git clone https://github.com/3531st-lab/guangzhu.git
cd guangzhu
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup.ps1
```

开发版用本机 `127.0.0.1:8765`（光筑）和 `127.0.0.1:4177`（AGH），安装版用 8766 和 4178，两者可以同时开。

离线计算和已归档运行核验不需要模型 key，准确命令及成功标准见 [复现指南](docs/REPRODUCING.md)。发起新的自动设计前，复制 [配置模板](desktop/settings.example.json) 为 `desktop/settings.json`、填写本机路径，并按 [AGH 接入说明](docs/AGH_SETUP.md) 配置运行包、MCP、插件与模型，然后运行 `start.cmd`。Python 安装路径不是默认值时，给安装脚本传入 `-Python`。

### 测试

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest
node --test agh-plugin/guangzhu-studio/test/*.test.js
node --test tests/embed_harness/*.test.mjs
node --test tests/desktop/*.test.mjs
.\.venv\Scripts\python.exe scripts/check_secrets.py
```

公共仓库不含全部历史过程归档，相关历史测试会明确跳过；通过、跳过、失败应分别统计，详见 [复现指南](docs/REPRODUCING.md)。

### 安装包

```powershell
powershell -NoProfile -File scripts/build_installer.ps1 -AghArchive 'C:/inputs/agnes-win32-x64-5da4073.zip' -AghSource 'C:/src/agnes-harness'
```

需要 Python 3.12 和官方 AGH 运行包（脚本参数 `-AghArchive`、`-AghSource`）。脚本下载官方 Python 嵌入包、Inno Setup 和锁定的依赖（`requirements.lock.txt`），核对签名和摘要，跑安装树检查和离线计算自检，输出 `dist/guangzhu-setup.exe`。

原始 AGH ZIP 的获取渠道、固定摘要和缺失时的替代复现路径见 [外部依赖说明](docs/DEPENDENCIES.md)；仅凭源码克隆不能声称已重建同一安装包。

## 第三方来源

- 运行底座 [Agnes Harness](https://github.com/AgnesAI-Labs/agnes-harness)（Apache-2.0），官方运行包原样随安装包分发。
- 开源库：pvlib、NREL PySAM、pandas、NumPy、SciPy、Shapely、FastAPI、Uvicorn、Pydantic、Requests、MCP Python SDK、ezdxf、pypdfium2、openpyxl、Matplotlib、Jinja2、pywebview、three.js（r128）；字体 IBM Plex Mono、Noto Serif SC（OFL-1.1）。
- 数据：NASA POWER（CC BY 4.0）、JRC PVGIS、OpenStreetMap（© OpenStreetMap 贡献者，ODbL 1.0）、NREL SAM CEC 库（BSD-3）、NREL PVDAQ（CC BY 4.0）、美国海军天文台。
- 逐项的来源、版本、许可和用途见 [`docs/sources.md`](docs/sources.md)；随仓库的许可证文件在 `data/catalog/`、`data/roofs/`、`desktop/web/vendor/`、`agh-plugin/guangzhu-studio/licenses/`。

不要把任何 key 写进文件；key 只在光筑首页或 AGH 设置里填。

## 许可证与公开范围

[LICENSE](LICENSE) 适用于团队原创部分；第三方代码、字体和数据继续遵循 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 列明的许可。用户图纸、真实个人项目、模型凭据、AGH 实例目录和未经复核的执行记录不属于公开内容。提交前运行密钥扫描，并人工检查图像、PDF、账本和 Git 历史；忽略规则不能清除已提交的信息。
