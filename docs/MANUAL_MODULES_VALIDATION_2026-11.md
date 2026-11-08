# 手动光伏组件编辑验证

执行日期：2026-11-03。本记录对应本地源码分支 `feat/competition-upgrade-20261103`；入口与限制见[操作说明](MANUAL_MODULES_2026-11.md)。本次未重新发布安装包。

## 可复验的实际版本链

运行[演示脚本](../scripts/manual_modules_demo.py)：

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts/manual_modules_demo.py --project another-manual-example --output output/manual-modules/another-demo.json
```

项目编号与输出文件都必须尚不存在，脚本明确拒绝覆盖。本机已经生成 `manual-modules-demo`，共 6 个版本；通过生产 HTTP 预览／保存契约运行真实几何和工程计算，不调用模型。

| 版本 | 内容 | 平均遮挡损失 | 基准年发电估算 | 硬性规则未通过 |
| --- | --- | --- | --- | --- |
| v1 | 空白起点 | 未计算 | 未计算 | 未计算 |
| v2 | 补放 6 块目录组件，3.3 kWp | 1.6896% | 3690.43 kWh | 0 |
| v3 | 锁定两块组件及邻接空白 | 1.6896% | 3690.43 kWh | 0 |
| v4 | 将未锁定组件移近设备箱 | 4.8274% | 3572.64 kWh | 1：S01 遮挡超限 |
| v5 | 该组件顺时针旋转 37° | 4.4772% | 3573.66 kWh | 2：S01、E08 组串未完整接入 |
| v6 | 撤销旋转，精确恢复 v4 几何 | 4.8274% | 3572.64 kWh | 1：S01 |

示例采用 20×14 m 合成屋顶、示意承重、设备箱与分段女儿墙，天气为常州 2023 年缓存。它用来验证工程反馈，不能当作已经通过校核的实测方案。v5 的新朝向缺少对应离线 PVGIS 链，缺失信息被保留；表内为现有主计算链估算，不伪造跨源验证通过。

[完整版本、指标和摘要](../output/manual-modules/demo.json)记录了：锁定前中心 `[8.7,4]` 可以补放，锁定后同一位置返回 `DESIGN_LOCK_CONFLICT`，且不生成版本；两块锁定组件保持完全相同；预览不落盘；确认保存与候选角点一致；36 份旧设计／分析文件 SHA-256 未变；v6 与 v4 的组件几何摘要相同。

## 最终测试与现场核对

环境：Windows、Python 3.12.10、Node.js 24.16.0；浏览器采用 Playwright 与实际 WebGL。

| 范围 | 结果 | 证据 |
| --- | --- | --- |
| 手动编辑、计算联动、天空积分、MCP 原契约 | 63 通过，0 失败，21.10 秒 | [日志](../output/manual-modules/backend-final-core.log)、[JUnit](../output/manual-modules/backend-final-core.xml) |
| 最终几何、锁定重排、撤销、规则、荷载、朝向与遮挡回归 | 58 通过，0 失败，67.00 秒 | [日志](../output/manual-modules/final-geometry-regression.log)、[JUnit](../output/manual-modules/final-geometry-regression.xml) |
| 手动编辑 DOM 及既有局部编辑／异步回归（含最终规则提示与候选旧指标隔离） | 4 通过，0 失败，22.62 秒 | [日志](../output/competition-upgrade/manual-editor-final-target-dom.log)、[JUnit](../output/competition-upgrade/manual-editor-final-target-dom.xml) |
| 桌面 JavaScript 全套（含最后的旧指标隐藏修正） | 224 通过、17 项原有跳过、0 失败 | [日志](../output/manual-modules/desktop-node-final.log) |
| 最终规则提示与 DXF 输出 | 3 通过，0 失败，10.85 秒 | [日志](../output/manual-modules/final-impact-output.log)、[JUnit](../output/manual-modules/final-impact-output.xml) |
| AGH release 一致性 | 通过，`Plugin artifacts match` | [日志](../output/manual-modules/agh-plugin-release-check.log) |
| 真实 WebGL 界面及详细预览 | 零页面错误；示例文件摘要未变；只预览、未保存 | [QA](../output/manual-modules/qa.json) |
| 重启后的真实本机 HTTP API | 旋转预览改变 1 块、影响 3 块的遮挡；保留 2 块锁定组件；37 份源文件未变 | [核对结果](../output/manual-modules/live-api-audit.json) |

各组测试有重叠，不能将数量相加。首次关联扫描为 186 项通过、1 项工具清单大小检查未通过，记录保留于[原日志](../output/manual-modules/backend-regression.log)；收尾保持手动入口为工作台 API，并在上方最终 63 项中复验完整 MCP 原契约通过。没有将本轮测试称为整个 Python 仓库的一次全量通过。

主要复验命令：

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest -q tests/test_manual_modules.py tests/test_manual_engineering.py tests/test_manual_sky_visibility.py tests/test_manual_reflow.py tests/test_manual_outputs.py
.\.venv\Scripts\python.exe -X utf8 -m pytest -q tests/test_design_locks.py tests/test_design_edits_api.py tests/test_partial_reflow_shading.py tests/test_shading_geometry.py tests/test_shading_annual.py tests/test_shading_edit.py tests/test_structure.py tests/test_rules.py tests/test_orientation_groups.py
.\.venv\Scripts\python.exe -X utf8 -m pytest -q tests/test_manual_editor_dom.py tests/test_design_edits_dom.py tests/test_design_edits_async_dom.py tests/test_scene_manual_dom.py
node --test tests/desktop/*.test.mjs
.\.venv\Scripts\python.exe -X utf8 scripts/build_agh_plugin.py --check --release
```

## 关键独立期望与修正

- 独立量测板材三维边长、直角、坡面贴合高度与指定中心。板内连续旋转保持真实几何，补放编号与原板编号不冲突。
- 越界、设备／禁区避让、板间距、限高、锁定模块、锁定坡面和锁定空白均有拒绝用例；失败不产生部分保存。
- 真实阴影算例验证无遮挡板为零损失，覆盖半个天空的高墙使水平板天空量减少一半；不同朝向及相同行号的邻板仍能遮挡，板面余弦改变后结果随之变化。
- 验证直射与散射损失总和、各遮挡原因总和及年度结果守恒；荷载按真实旋转板投影分配到风区；DXF 读回角点与模型一致。
- 分离天空计算方法与“手动散排”状态：原方案的通道规则不因比较算法被改写；撤销恢复原规则状态；完整重排恢复规则排布后仍继承天空方法。
- 带锁手动方案局部重排后，新生成的毫米取整板仍保留精度来源；再次合法平移不误报板间隙不足，锁板保持逐字段不变。
- 前端覆盖补放→移动→旋转→撤销→锁定、坐标点选、取消请求和乱序响应。预览使用后端候选，参数变化使旧候选失效；保存后才导航到新版本。

截图通过生产编辑器及真实 WebGL，向本地 TestClient 转发设计与预览请求；模型运行状态使用固定值，不调用模型或提交保存。真实本机 HTTP 服务另行核对。界面中的规则未通过被完整展示。

![真实旋转预览与区域锁](../output/manual-modules/manual-edit-workbench.png)

![修改前后指标及逐组件遮挡变化](../output/manual-modules/manual-edit-impact.png)
