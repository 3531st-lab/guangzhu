# 精确建模工作台验证记录

执行日期：2026-11-03。对应本地分支 `feat/competition-upgrade-20261103` 的源码工作台，承接[首批参赛改进](COMPETITION_UPGRADE_VALIDATION_2026-11.md)及厂房外观；本轮操作、软件参考和范围见[建模说明](MODELING_WORKBENCH_2026-11.md)。既有 v0.2.0 安装包未重新发布。

## 可打开的示例

本机服务为 `http://127.0.0.1:8765`。打开[精确建模工作台示例](http://127.0.0.1:8765/#roof/my-precision-workbench)，可编辑双坡主厂房、低跨平顶附楼、6 个采光带、附楼机房和 10 段带缺口的女儿墙。示例使用合成尺寸、示意承重，不是实测客户项目。

双击根目录 `start.cmd` 启动源码工作台；在其他环境创建独立示例：

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts/modeling_workbench_demo.py --id my-modeling-example
```

脚本拒绝覆盖已有编号。选择机房或 Ctrl 多选采光带，预览相对移动／旋转／镜像，应用后可一步撤销；标准视图及正交投影用于检查几何。女儿墙面板可改分段长度、高度及缺口，保存后重新打开检查。

![精确建模工作台](../output/modeling-workbench/modeling-workbench-editor.png)

![正交俯视与对象多选](../output/modeling-workbench/modeling-workbench-top-selection.png)

## 测试证据

环境为 Windows、Python 3.12.10、Node.js 24.16.0；浏览器测试使用 Playwright 和实际 WebGL。

| 验证范围 | 实际结果 | 记录 |
| --- | --- | --- |
| 分段女儿墙后端专项 | 46 通过，0 失败，5.97 秒 | [日志](../output/competition-upgrade/parapet-backend-tests.log) |
| 女儿墙、坡面、组合屋顶、电气与遮挡关联回归 | 141 通过，0 失败，175.19 秒 | [日志](../output/competition-upgrade/parapet-rotated-path-regression.log) |
| 组合屋顶、保存重开、锁定与存储回归 | 72 通过，0 失败，27.43 秒 | [日志](../output/competition-upgrade/parapet-storage-locks-regression.log) |
| 对象编辑、组合屋顶、厂房外观 DOM／WebGL | 15 通过，0 失败，121.36 秒 | [日志](../output/modeling-workbench/object-editor-dom.log)、[JUnit](../output/modeling-workbench/object-editor-dom.xml) |
| 女儿墙面板、保存重开、撤销与条件表 DOM | 5 通过，0 失败，52.21 秒 | [日志](../output/modeling-workbench/parapet-editor-final.log)、[JUnit](../output/modeling-workbench/parapet-editor-final.xml) |
| 场景相机、外观与移除轮廓 WebGL | 3 通过，0 失败，35.82 秒 | [日志](../output/modeling-workbench/scene-webgl-tests.log) |
| 桌面 JavaScript 全套 | 212 通过，17 项原有跳过，0 失败，2.46 秒 | [日志](../output/modeling-workbench/desktop-node-final.log) |
| AGH release 产物一致性 | 通过，`Plugin artifacts match` | [日志](../output/modeling-workbench/agh-plugin-release-check.log) |
| 启动后的本机 API | 10 段、10 片真实墙面、3 个屋面；API 墙面逐顶点等于遮挡几何；示例文件未变 | [JSON](../output/modeling-workbench/live-api-audit.json) |

各行覆盖有重叠，数量不可相加。141 项回归启动时，后端专项包含 42 项；随后新增的 4 项非法原始轮廓 API 校验由最终 46 项专项覆盖，因此现在重跑下方关联回归会收集 145 项。本轮没有再次运行整个 Python 仓库全量测试，首批全量扫描情况仍按原验证记录保留。

主要复验命令：

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest -q tests/test_parapets.py
.\.venv\Scripts\python.exe -X utf8 -m pytest -q tests/test_parapets.py tests/test_t32_geometry.py tests/test_t32_overlap.py tests/test_t32_integrations.py tests/test_t32_engineering.py tests/test_electrical.py tests/test_compound_roof.py tests/test_shading_geometry.py
.\.venv\Scripts\python.exe -X utf8 -m pytest -q tests/test_compound_roof.py tests/test_myroofs.py tests/test_design_locks.py tests/test_t29_store.py
.\.venv\Scripts\python.exe -X utf8 -m pytest -q tests/test_model_objects_dom.py tests/test_compound_editor_dom.py tests/test_facade_editor_dom.py tests/test_parapet_editor_dom.py tests/test_scene_workbench_dom.py tests/test_scene_facade_dom.py tests/test_scene_removed_outline_dom.py
node --test tests/desktop/*.test.mjs
.\.venv\Scripts\python.exe -X utf8 scripts/build_agh_plugin.py --check --release
```

## 核对的具体行为

- 分段墙的解析射线与阴影：2 m 高、10 m 长的墙在 45° 太阳高度下投影面积为 20 m²，墙段外与缺口不产生该墙遮挡；旋转、坡屋面、屋脊和高低跨墙底有独立坐标期望。
- `None` 沿用全周墙高，`[]` 明确无墙，显式分段按各段高度；后端、二维标记、三维墙面、锁定签名和保存重开保持一致。旧屋顶序列化与锁定签名兼容。
- 修改轮廓使旧边号失效时不能直接保存；须明确重新生成。异步重新生成期间禁用保存，避免写入旧边号。
- 选择不会改动模型；变换预览不写入，取消不留副本，应用可一次撤销；更改对象或变换参数后旧预览失效。保存仍进行原有屋面归属和工程几何校验。
- 正交模式使用真正的 OrthographicCamera，前后不同距离的同尺寸物体显示比例相同；高屋脊与墙顶参与取景。投影切换、窗口缩放、标准视图及同几何跨二维／三维恢复均有验证。
- 分段女儿墙不再借用旧全周高度推算组件最高点；条件表禁用自动限高并提示核对缺口，自然语言提取也不自动填入旧值。

界面截图使用生产编辑器与真实 WebGL，通过本地 TestClient 转发屋顶和几何请求，模型服务状态及天气提示使用固定值；没有执行模型调用或发电分析。截图时的对象选择、真实正交相机、镜头恢复、零页面错误与项目摘要见[界面 QA](../output/modeling-workbench/modeling-workbench-editor-qa.json)。启动后的真实本机 HTTP API 另行核对共享墙面几何。

本轮验证的是建模与工程参数联动，不代表新的 Agent 任务成功率、完整 BIM 能力或项目已通过专业审核。保存新几何后应生成对应设计版本并重新执行分析；厂房装饰仍仅用于外观，园区邻栋仍使用保守外包络。
