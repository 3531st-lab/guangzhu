# 三维组件操作与版本证据验证记录

执行日期：2026-11-03。对应本地源码分支 `feat/competition-upgrade-20261103`，承接[手动组件编辑](MANUAL_MODULES_VALIDATION_2026-11.md)。操作入口与限制见[三维工作台说明](THREE_DIMENSIONAL_EDITING_2026-11.md)。本轮没有发布新安装包，也没有执行新的模型评测。

## 最终测试记录

环境为 Windows、Python 3.12.10、Node.js 24.16.0。浏览器验证使用 Playwright、系统 Microsoft Edge 和实际 WebGL。

| 范围 | 实际结果 | 证据 |
| --- | --- | --- |
| 组件几何契约、手动工程联动、诊断、证据、输入缓存、完整计算清单、API、锁定与既有分析回归 | 266 通过、6 跳过、0 失败，132.90 秒 | [日志](../output/direct-manipulation/backend-final.log)、[JUnit](../output/direct-manipulation/backend-final.xml) |
| DOM／WebGL 最终组合回归（12 个测试文件） | 19 通过、0 跳过、0 失败，143.75 秒 | [日志与完整命令](../output/direct-manipulation/dom-final.log)、[JUnit](../output/direct-manipulation/dom-final.xml) |
| 真实浏览器锁空白补充验收及两种显示模式回归 | 3 通过、0 跳过、0 失败，51.52 秒 | [日志与拒绝证据](../output/direct-manipulation/locked-region-webgl.log)、[JUnit](../output/direct-manipulation/locked-region-webgl.xml) |
| 吸附几何专项（含独立中心、同侧边线用例） | 7 通过、0 跳过、0 失败 | [日志](../output/direct-manipulation/snap-geometry-final.log) |
| 桌面 JavaScript 全套 | 246 通过、17 跳过、0 失败，1.04 秒 | [日志](../output/direct-manipulation/desktop-node-final.log) |
| AGH release 产物一致性 | 通过，`Plugin artifacts match` | [日志](../output/direct-manipulation/plugin-release-check.log) |
| 生产界面、真实鼠标手势与截图 | 3 次预览请求，无保存请求，0 页面错误；37 份项目文件 SHA-256 未变 | [QA 摘要及详情](../output/direct-manipulation/qa.json)、[采图日志](../output/direct-manipulation/capture.log) |
| 真实本机 HTTP 预览／保存／撤销 | v7–v10 均有一致的输入签名与完成清单；36 份历史设计／分析文件未变；2 块锁板未变；撤销恢复起点几何 | [JSON](../output/direct-manipulation/live-roundtrip.json)、[日志](../output/direct-manipulation/live-roundtrip.log) |
| 最终只读文件复核 | 37 份采图原文件及 32 份新版本记录摘要一致；v7–v10 各完成清单的 6 份输出核验通过；撤销与锁板几何再次确认 | [当前状态审计](../output/direct-manipulation/current-state-audit.json) |
| 本机运行依赖自检 | 全部通过，退出码 0；保留本轮实际输出与依赖版本 | [自检记录](../output/direct-manipulation/selfcheck-final.json) |

各组测试覆盖有重叠，数量不可相加；锁空白专项的 3 项包含上述 19 项中的 2 个显示模式用例，吸附专项的 7 项也包含在 Node 全套中。后台 6 项跳过中，5 项依赖本次检出未包含的历史归档，1 项因 Windows 没有符号链接权限；这些项目没有计入通过。Node 的 17 项跳过同样单独保留。DOM／WebGL 使用单个 pytest 进程串行运行，期间未并发采图。本轮执行了表中关联回归，没有将其称为整个 Python 仓库的一次全量通过。

## 真实 HTTP 版本链

本机可打开[三维操作示例 v10](http://127.0.0.1:8765/#result/direct-manipulation-demo?version=10)。项目 `direct-manipulation-demo` 使用合成屋顶与示意承重，初始 v1–v6 来自手动组件演示；[脚本](../scripts/direct_manipulation_demo.py)随后通过真实 8765 服务执行四轮预览与确认保存。指针手势另由浏览器测试和截图证明，HTTP 脚本没有模拟鼠标动作。

| 保存版本 | 操作 | 详细复算的平均遮挡损失 | 基准年发电估算 | 硬性规则未通过 |
| --- | --- | --- | --- | --- |
| v7 | 未锁组件沿 X 移动 0.3 m、Y 移动 0.4 m | 4.7857% | 3574.20 kWh | 1：S01 |
| v8 | 撤销移动，恢复 v6 几何 | 4.8274% | 3572.64 kWh | 1：S01 |
| v9 | 未锁组件顺时针旋转 45° | 4.6193% | 3559.59 kWh | 2：E08、S01 |
| v10 | 撤销旋转，再次恢复 v6 几何 | 4.8274% | 3572.64 kWh | 1：S01 |

四个新版本均为 6 块、3.3 kWp；`input_binding` 与 `completion_status` 均为 `matched`。v9 缺少该朝向对应的离线 PVGIS 链，记录保留缺失原因；回本年限为 `null`，没有把缺失结果显示成零或通过。示例保留失败项以检验诊断流程，不是已通过全部工程校核的方案。

每轮预览前后核对项目文件摘要，确认预览不落盘；确认后的保存几何等于候选几何。v1–v6 的 36 份历史设计／分析文件始终保持 SHA-256 不变，两块受保护组件 `R01-1-C001`、`R02-1-C001` 的几何不变，v8 与 v10 均恢复 v6 几何。该 HTTP 记录共 13 次请求：初始读取及四组预览、保存、读取。

## 界面截图与操作证据

六张截图取自 `manual-modules-demo` 的保存版本 v6，使用生产页面、实际 WebGL 与真实鼠标手势；API 请求经本地 TestClient 执行。启动／模型状态使用固定值，没有模型调用，也没有提交保存。采图前后核对的 37 份文件包含 `project.json`，与上方 HTTP 核对的 36 份历史文件口径不同。

拖动中没有发出预览请求，候选轮廓与数值更新时保持视角稳定，并隐藏旧年度热图图例、风荷载、布线及检查卡片。松手后请求一次预览；旋转候选和 S01 修复候选均记录了真实详细复算。所有截图、请求和界面状态见 [qa.json](../output/direct-manipulation/qa.json)。

![移动中的轮廓、位移与网格吸附](../output/direct-manipulation/01-move-ghost.png)

![真实旋转环与 45° 角度吸附](../output/direct-manipulation/02-rotate-ring.png)

![旋转松手后的后端候选与未保存提示](../output/direct-manipulation/03-rotate-candidate.png)

![S01 规则对象定位与同版本证据](../output/direct-manipulation/04-problem-location.png)

![保留锁定对象的修复预览与工程比较](../output/direct-manipulation/05-repair-preview.png)

![文件页中的保存版本证据与未知记录](../output/direct-manipulation/06-version-evidence.png)

## 独立边界验证

- 平顶、彩钢瓦和多坡屋面的手柄候选与后端真实角点比较；网格、邻板边线、目录间隙、角度吸附及 Alt 旁路分别验证。多选旋转保持每板自身中心语义。
- 指针捕获、Esc、失焦、切换工具、离开页面、取消请求及过期响应不会提交或恢复旧候选。已加载风荷载／电气卡片时，隐藏卡片不使场景画布改变尺寸，拖动不误转相机。
- 锁板不能拖动，锁定空白不能被占用；详细预览、确认保存和撤销使用生产 API，历史文件保留。晚到的旧保存响应不抢占当前导航。
- 诊断核对版本、对象集合及来源；定位保留已有选择，修复只预览明确证据支持的未锁定 S01 对象。未知硬规则不会因建议项通过而被提升为通过。
- 单板定位保留周围 3 m 的场景参考，修复预览保留当前镜头，避免候选删除对象后丢失周边位置关系。
- 历史空元数据安全读取；独立审核使用其自身归档摘要核验，篡改后不作为证据。脱敏导出快照的归档核验与原件清单匹配分别显示。
- 工程输入变化使旧缓存和诊断失效。完成清单绑定六份分析输出的预期字节摘要，另一写入者混入文件时拒绝发布；原子替换故障保留旧清单并清理临时文件；现代输出缺少必需清单时标为过期。旧遮挡缓存仅改变 JSON 空白格式仍能按原始字节正确复用。

旧归档未保存完整分析或完成清单时，证据如实显示不完整／未记录。本轮没有扩展旧归档的脱敏格式；本地新计算的完整性与旧归档原件／快照的可核验范围分别呈现。通过功能回归、文件完整性校验和同版本规则校核，都不替代现场核定、独立审核或导出批准，也不产生新的智能体评测成绩。

## 逐项目标验收

本表对应“完善项目，并根据比赛要求设计功能”的本轮明确范围：[三项功能设计](COMPETITION_FEATURE_DESIGN_2026-11.md#三项实施设计与验收)及[三维工作台的六条验收](THREE_DIMENSIONAL_EDITING_2026-11.md#验收)。最终审计逐项核对源码、测试断言与实际执行记录；下列已承诺项目均已闭环。

| 目标／验收项 | 直接实现与验证入口 | 实际证据与结论 |
| --- | --- | --- |
| 根据真实比赛要求选功能 | [参赛依据](COMPETITION_FEATURE_DESIGN_2026-11.md#比赛和原始依据)记录两份盖章原件、页码、完整 SHA-256 与三个功能的赛事对应 | 最终只读复核两份现存 PDF 的 SHA-256 均与记录一致。三维操作对应 OPC 工作流与工具演示，诊断对应可解释服务流程，证据与费用对应部署及经营说明；没有杜撰评分权重或获奖概率。 |
| P0 三维操作；验收 1：真实板材与坡面几何 | [几何变换](../desktop/web/module-transform-geometry.js)、[后端目录与安装面契约](../backend/guangzhu/manual_modules.py)；[跨语言角点比对](../tests/test_module_transform_contract.py)、[坡面真实指针测试](../tests/test_scene_module_transform_dom.py) | 平顶、彩钢瓦、多坡屋面、横竖放及连续移动／旋转均有独立比较；跨语言数值比对的中心、角点、倾角和方位误差容限为 `1e-9`。专项在后台与 DOM 最终日志中通过。 |
| P0 三维操作；验收 2：grid／center／edge／gap／angle／Alt | [吸附算法](../desktop/web/module-transform-geometry.js)、[7 项数值验证](../tests/desktop/module-transform-geometry.test.mjs)、[WebGL 手势验证](../tests/test_scene_module_transform_dom.py) | 网格、中心线、同侧边线、真实安装间隙、角度及 Alt 旁路均有行为断言；center／edge 用例明确排除其他吸附分支，核对目标与参考线。真实鼠标覆盖网格、角度、多选 Alt 旁路与视角不误转；[专项日志](../output/direct-manipulation/snap-geometry-final.log)及 DOM 日志通过。 |
| P0 三维操作；验收 2：锁板／锁空白及取消 | [手势控制](../desktop/web/scene-module-transform.js)、[后端锁约束](../backend/guangzhu/manual_modules.py)；[真实生产页面手势](../tests/test_module_gesture_app_webgl.py)及[取消状态验证](../tests/test_module_gesture_editor_dom.py) | 锁板不能开始拖动。空白锁区补证使用相同 `dx=4 m, dy=6 m`：无锁预览 200，加锁后真实鼠标只发一次预览，返回 422／`DESIGN_LOCK_CONFLICT`，0 次保存；5 份项目文件不变，v4／下一版本 v5 不变，相机与选择保留、候选和轮廓清除。Esc、失焦、指针取消及切换工具另有通过断言。 |
| P0 工程联动；验收 3：实际遮挡、电气与经济复算 | [详细影响计算](../backend/guangzhu/design_edits.py)、[真实几何遮挡](../backend/guangzhu/shading.py)；[工程期望](../tests/test_manual_engineering.py)、[天空遮挡独立算例](../tests/test_manual_sky_visibility.py) | v7–v10 的[真实 HTTP 记录](../output/direct-manipulation/live-roundtrip.json)保留实际遮挡、发电、造价、组串和失败规则变化；v9 缺 PVGIS 链、回本未知及 E08／S01 失败均保留。计算失败不借用旧值，拖动／候选期间旧热图、风荷载与布线显示隔离有 DOM 验证。 |
| P0 版本链；验收 3：预览、确认、重开、撤销与历史 | [编辑事务与界面](../desktop/web/design-edit-ui.js)、[API](../backend/guangzhu/design_edits.py)；[真实保存撤销](../tests/test_module_gesture_app_webgl.py)、[旧响应导航竞争](../tests/test_edit_navigation_race_dom.py) | 松手预览不写盘，明确确认才新增版本，读取结果等于候选；v8／v10 恢复 v6，2 块锁板不变，36 份历史文件不变。最终[只读复核](../output/direct-manipulation/current-state-audit.json)再次核对新版本记录与恢复几何；取消和旧响应不会生成或重现旧候选。 |
| P1 诊断；验收 4：四类问题及安全修复 | [同版本诊断](../backend/guangzhu/design_diagnostics.py)、[定位与修复意图](../desktop/web/design-diagnostics.js)；[20 项后端验证](../tests/test_design_diagnostics.py)、[前端边界验证](../tests/desktop/design-diagnostics.test.mjs)、[生产页验收](../tests/test_diagnostic_evidence_editor_dom.py) | S01／E08／E10／坡面 L01 分别从逐板损失、未接线清单、明确失败线路与坡面荷载关联对象。来源冲突或缺对象不猜测；定位保留选择；S01 修复只预览未锁定明确 ID，默认详细复算并保留锁板；全锁定、只读和过期操作被拒绝。未知硬规则不会显示通过。 |
| P1 版本证据；验收 5：输入及整套输出完整性 | [证据采集](../backend/guangzhu/design_evidence.py)、[签名与原子清单](../backend/guangzhu/analysis_inputs.py)；[输入缓存验证](../tests/test_analysis_input_binding.py)、[中断和混写验证](../tests/test_analysis_completion.py) | 四个新版本各 6 份分析文件与完成清单、设计及项目输入签名匹配。输入变化、混写、缺必需清单或摘要不符会标为过期并禁用诊断修复；原子替换失败保持旧清单。该签名不覆盖外部目录 CSV、代码版本或天气缓存原始字节，因此不声称完整运行环境可复现。 |
| P1 审核、交付与成本；验收 5：真实来源及缺失值 | [原生会话用量](../backend/guangzhu/api.py)、[证据展示与下载](../desktop/web/design-evidence.js)；[证据测试](../tests/test_design_evidence.py)、[独立审核／脱敏回归](../tests/test_design_evidence_review.py)、[原生用量测试](../tests/test_api.py) | 独立审核使用对应归档自身摘要；篡改文件排除，脱敏快照与原始导出匹配分开。原生费用按编号去重，估算不作为实付，缺账本／费用／人工工时／失败重试统计保持未知；计算用时与跨版本会话总用时分开。历史案例与无模型调用的手动示例没有拼接成新实验。 |
| 验收 6：可运行交付、文档与独立验证 | [操作步骤与新项目复现](THREE_DIMENSIONAL_EDITING_2026-11.md)、[中英 README 入口](../README.md)、[HTTP 演示脚本](../scripts/direct_manipulation_demo.py)、[本机自检](../output/direct-manipulation/selfcheck-final.json)及本页最终日志／截图 | 本机 v10 入口、两步新项目脚本、6 张最终界面图、266／6 后台、19／0 DOM、3／0 锁区补证、246／17 Node、插件一致性和自检退出 0 均有记录。测试重叠与跳过单列；产品源码与配套说明完成，未把旧安装包称为本轮新版。 |

本轮之外仍包括新安装包发布、30 道新任务 × 3 次真实模型评测、公平基线／留出集、DXF／PDF 辅助识别、联合工程经济搜索，以及按赛事制作新的录屏、申报表和真实经营材料。它们没有在本次功能与验收设计中承诺交付；本表不将既有视频、历史 51/54 成绩、示意项目或未知人工成本代替这些工作。

## 复验入口

以下命令复验本轮核心契约；表中 266 项后台集合的 23 个测试文件及每项结果以 JUnit 为准。

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest -q tests/test_module_transform_contract.py tests/test_design_diagnostics.py tests/test_design_evidence.py tests/test_design_evidence_review.py tests/test_analysis_input_binding.py tests/test_analysis_completion.py
node --test tests/desktop/*.test.mjs
.\.venv\Scripts\python.exe -X utf8 scripts/build_agh_plugin.py --check --release
```

创建新的 HTTP 演示项目和版本链，见[操作说明中的两步脚本](THREE_DIMENSIONAL_EDITING_2026-11.md#打开示例)。使用新编号与新输出文件，不覆盖已记录的 v10 示例。
