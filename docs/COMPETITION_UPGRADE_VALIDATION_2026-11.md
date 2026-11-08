# 参赛首批改进验证记录

执行日期：2026-11-03。本记录对应本地分支 `feat/competition-upgrade-20261103`，基于公开仓库提交 `66ed06506d6d325b0b1531ceeddd8ab1c16ef37e` 的源码改动。功能与适用范围见 [改进说明](COMPETITION_UPGRADE_2026-11.md)。

环境：Windows、Python 3.12.10、Node.js 24.16.0，独立 `.venv` 与锁定依赖；依赖自检通过。浏览器交互使用 Playwright Chromium，三维验收使用实际 WebGL。

## 可复验的完整示例

本机项目：`compound-upgrade-final`，最终版本 v4。运行：

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts/competition_demo.py --project another-compound-demo --analyze
```

须使用尚不存在的项目编号。脚本不会覆盖已有项目，也不会调用模型或批准导出。

| 阶段 | 结果 |
| --- | --- |
| v1 初稿 | 431 块组件 |
| v2 人工锁定 | 锁定主厂房 P1 屋面，包含 189 块组件及屋面空白区域 |
| v3 局部重排 | 其余区域改横排，共 440 块；实际复算出现 1 项硬性规则失败：局部遮挡超限 |
| v4 规则修正 | 移除 13 块未锁定的遮挡超限组件，保留 427 块，234.85 kWp；35 项规则中 20 项通过、15 项不适用，硬性失败 0 |
| 保锁核对 | v2 与 v4 的 189 块锁定组件逐项相同，最终锁定几何签名已保存 |

结果、各版本 SHA-256 与未通过中间版本记录见 [`compound-upgrade-final.json`](../output/competition-upgrade/compound-upgrade-final.json)。启动工作台后可打开 [最终方案](http://127.0.0.1:8765/#result/compound-upgrade-final?version=4)，或进入“设计结果 → 局部修改”。

示例采用合成屋面尺寸、示意承重及常州天气快照，属于离线工程演示，不是客户案例、泰州实测数据或新一轮 Agent 评测。`analysis_complete=true` 表示计算完成；是否通过应检查对应版本 `rules.hard_failed`。最终草案仍须专业复核和正式导出流程。

## 测试记录

| 验证范围 | 实际结果 | 记录 |
| --- | --- | --- |
| Python 全量扫描 | 1911 通过、124 跳过、2 项网络测试未选择；42 项当次未通过，后续复验见下行；3151.00 秒 | [日志](../output/competition-upgrade/pytest-full.log)、[JUnit](../output/competition-upgrade/pytest-full.xml) |
| 全量扫描未通过项，在收尾后的代码上统一复验 | 41 通过、1 跳过（Windows 无目录符号链接权限）、0 失败；123.09 秒 | [日志](../output/competition-upgrade/pytest-failures-rerun.log)、[JUnit](../output/competition-upgrade/pytest-failures-rerun.xml) |
| 最终代码集成验收（15 个 Python 测试文件） | 186 通过，7 跳过（5 项缺归档、2 项缺 Windows 符号链接权限），0 失败；100.66 秒 | [日志](../output/competition-upgrade/pytest-final.log)、[JUnit](../output/competition-upgrade/pytest-final.xml) |
| 首批功能验收（8 个测试文件） | 47 通过，0 失败、0 跳过；33.44 秒 | [日志](../output/competition-upgrade/pytest-upgrade.log)、[JUnit](../output/competition-upgrade/pytest-upgrade.xml) |
| API 兼容回归 | 80 通过，6 跳过（5 项缺归档、1 项缺 Windows 符号链接权限），0 失败 | [日志](../output/competition-upgrade/api-regression-tests.log) |
| 桌面 JavaScript（含建筑细节，收尾后再次验证） | 194 通过，17 项原有跳过，0 失败 | [日志](../output/competition-upgrade/desktop-node-final.log) |
| AGH 客户端与嵌入桥接 | 74 通过，12 项原有跳过，0 失败 | [日志](../output-plugin-tests.log) |
| AGH release 产物一致性 | 通过，`Plugin artifacts match` | [日志](../output/competition-upgrade/agh-plugin-release-check.log) |
| 最终示例独立核对 | 文件摘要、锁定组件、中间失败及最终规则全部与记录一致 | [JSON](../output/competition-upgrade/demo-audit.json) |

全量扫描与功能收尾有时间重叠，因而保留其原始失败记录，不将它改写为一次全部通过的最终代码全量测试。随后对全部 42 个未通过项统一复验：旧归档的严格解析、示例天窗字段断言、建筑墙面标记以及界面保存测试均已通过；另 1 项因 Windows 目录符号链接权限缺失而跳过。当前没有尚未处理的失败项。

原始日志保存于 `output/competition-upgrade/`。各行测试范围有重叠，不应将数量相加；缺归档或系统权限的跳过项不视为通过。最终演示 API 也独立确认了 427 块组件、189 块锁定组件、可进入编辑及锁定几何有效，见 [结果核对](../output/competition-upgrade/final-result-api-audit.json)。

浏览器实测覆盖晚到的预览响应、切换标签、取消预览、改参数、确认保存，以及真实 WebGL 中的高差、选择、移除轮廓和资源释放。新增红色轮廓线使用原坐标，不绘制重叠填充。最终截图只发出 GET 请求，项目文件摘要未变且页面无错误，见 [截图采集记录](../output/competition-upgrade/partial-reflow-capture.json)。

![组合厂房锁定与局部重排](../output/competition-upgrade/partial-reflow-workbench.png)

## 追加厂房外观验证

新增外观参数校验、保存重开及工程隔离测试 27 项通过；编辑器 DOM／真实 WebGL 联动测试 6 项通过，见 [编辑器日志](../output/competition-upgrade/factory-facade-editor-tests.log)。11 项外墙几何／网格测试已包含在上面的 JavaScript 全套统计中。

独立几何审核发现并修正了窄天井装卸平台穿入对面墙、雨棚外偏未计入净空和合法窄门被略去三处问题；修正后以具体 U 形天井、旋转和高低跨坐标复核。大尺寸厂房采用有界细分，避免装饰砖缝无限增长。

实际 WebGL 验收保持 427 块组件、3 个屋面；默认外观生成 26 扇窗、2 樘卷帘门、1 樘人行门、1 处装卸口、3 处雨棚。该场景共 37 次 draw call，反复切换材质后几何和纹理数量没有增长；保持观察位置、主题切换和资源释放均有验证。建筑墙面保留独立语义及朝外法线。截图采集不修改示例项目，见 [三维 QA 记录](../output/competition-upgrade/factory-facade-qa.json) 和 [外观编辑截图](../output/competition-upgrade/factory-facade-editor.png)。

## 仍待完成的下一批工作

此首批完成平顶／双坡组合、精确设备编辑及阵列、锁定与局部重排。后续已追加对象多选与精确变换、标准正交视图和分段女儿墙，见[建模工作台验证](MODELING_WORKBENCH_VALIDATION_2026-11.md)。第三批完成[组件手动补放、移动与旋转](MANUAL_MODULES_2026-11.md)。DXF/PDF 辅助识别和联合工程经济搜索仍未交付。

真实模型的 30 道新任务 × 3 次评测、公平基线、模型调用与人工成本记录，仍需另行执行。本轮结果不更新历史 51/54 成绩，不据功能完成数推算比赛胜率。既有 v0.2.0 安装包未重新发布；本次交付为本地可运行源码及 AGH 插件构建检查。
