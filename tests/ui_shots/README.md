# T14 实际 UI 验收

浏览器实际操作仅由 root 通过 CUA 进行。没有启动外部 Playwright 连接用户电脑；`measure.js`是同等 DOM 量测函数和视口矩阵，文件存在不代表矩阵已经执行。截图与实际量测写入 `reports/assets/T14-ui/`，并与 v5 reference 同路由、同主题、同视口对比。

1. 首页：接口提供三个真实模板，最近四条按结束时间降序且排除审核会话；记录页仍列全部成功、失败、审核和不可读记录。选择真实屋顶后进入表单，填写项目编号和条件，检查 Python 原文。
2. 运行四状态必须来自实跑：开始后的运行横幅；原生卡产生的可见“等你批准”提示；模型实际停下并给出建议；导出/独立审核完成后的核对结果。不得读取或修改隐藏运行状态、构造成功结果制作验收图。检查点“到此为止”只结束本地并归档，不发送同意。
3. `gz_export` 成功且模型 idle 后自动归档；设计四步通过、review enabled 时自动新 Agnes 会话执行后端审核任务。审核结束另归档并关联原设计，失败如实保留；不自动修改设计或强迫 approve。原生审批只在 iframe 内选择。
4. 每页在1440×900、1920×1080均要求根页面 x/y overflow=0；390×844只要求 x=0。局部内容允许滚动。先在浅/深色设置切换，再截图和执行只读 `measurePage()`，页面错误另由 CUA 浏览器记录收集。结果和回放的ID必须来自 `/api/runs` 实际记录。
5. 持久 iframe：开始前与切换首页/记录/回运行后的 `#agh` 元素是同一个，背景握手仍生效。15秒没有ready时，运行页显示复制任务书且每秒读文件进度；文件状态不能当严格账本核对。
6. 离线回放只读已导出timeline，滑块0是未开始，末值为全部事件；断开AGH不影响结果/回放。3D季节/模式/时间与真实版本切换分别量测，热图年度损失不随时间滑块变化。

离线函数测试：`node --test tests/ui_shots/frontend-data.test.mjs`。它读取既有真实模板、T10账本，不发起模型调用；通过不等于视觉验收通过。

## 冻结 54 图的可复现离线检查

从仓库根目录执行（Python 环境需有 Pillow）：

```powershell
python tests/ui_shots/audit_saved_evidence.py --root . --output reports/assets/T14-ui/saved-evidence-check-NEW
```

`--root` 是含已提交证据的仓库，可以是干净 clone；`--output` 必须是新目录，可以在 clone 外。脚本不会改输入图片、manifest、旧 audit、产品源码或 Git index。失败返回 1，通过返回 0，输出新 `audit.json`、`audit.md`。

范围固定为 `dynamic-after-fix` 的源码实跑四态 24 图和 `clone-static-after-fix` 的克隆静态五页 30 图。`frozen54.inputs.json` 锁定 66 份原输入（含 32 张动态候选、30 张静态图、两 manifest 和两来源文件）的 SHA；图片 SHA 已与先前逐图凭据交叉一致。程序仍独立读取图片像素，检查前后可见 DOM/真实项目会话/主题/根溢出/console 原数组/Runtime 范围，忽略 `accepted` 和旧 `passed`。动态审批选同一工具的完整六组合批，不把额外有效审批图当失败。

结果明确 `scope=offline_saved_evidence`、`fresh_dynamic_collection=false`。旧来源哈希与冻结凭据相互核对，**不会要求它们等于后加用量底栏的当前源码**；当前差异另列，旧 54 图不覆盖新底栏。冻结 tree 对象若在当前 Git 对象库中可用，会额外只读核对 blob；不可用时如实记录，不假称复原了旧 tree。克隆静态采样没有保存 Runtime 起点 cursor，不能据空响应声称全程零异常。旧 30 条未知错误采样不回填。克隆执行本命令属于冻结证据复核，不能改称克隆重新采集了四种 live 状态。

本入口的定向回归：

```powershell
python -m pytest tests/ui_shots/test_saved_evidence.py -q
node --test tests/ui_shots/capture-driver.test.mjs
```

## CUA 捕获入口

`capture_driver.mjs` 是依赖注入的 `createCaptureDriver(adapters).captureCurrent(request)`。它不创建浏览器客户端，不启动 Playwright/服务/模型，不触发设计、不批准工具，也不注入页面状态。操作员在实际页面出现目标状态后才调用；四态由真实业务产生。

2026-10-03 UTC，root 已从干净 clone 导入本模块，通过实际 CUA 回调采集设计/审核归档用量的两主题三视口 12 图及两张展开图，见 [本轮来源](../../reports/assets/T14-ui/clone-usage-footer-009/service-provenance.json)。这是当前产品的归档页脚采集，不是重新运行四种 live 状态；冻结 54 图仍按上面的历史证据范围检查。

由当前已授权 CUA 会话提供回调：`measure`（只读 DOM，可用导出的 `measureCapturePage`）、`setTheme`（点击可见主题按钮）、`setViewport`、`screenshot`（显式 clip）、`logs`（公开 `tab.dev.logs`）、`runtimeCursor`/`runtimeEvents`（已载入文档的 CDP Runtime 事件接口）、`saveImageExclusive`、`saveRowExclusive`（新文件，存在则拒绝）。回调须基于当次 CUA 返回的公开 API 文档绑定；模块没有猜测私有 endpoint 或连接用户浏览器。读取 `.head` 等选择器应与当前可见 DOM 确认。

请求示例仅说明参数，不自动执行：

```javascript
await driver.captureCurrent({id:'unique-shot-001',state:'approval',
  project:'真实项目编号',sessionPrefix:'真实8位UUID前缀',theme:'light',
  width:1440,height:900,sourceBinding:'本轮来源凭据.json'});
```

静态请求将 `state/project/sessionPrefix` 换成真实 `route/heading/subtitle`。每次先取 fresh Runtime cursor，再切主题/视口，只读测量→显式 clip 截图→再测量→采原始错误数组。前态不符不截图，后态变化保留图但判不合格；错误窗口和原始响应均保存。每张用唯一 id，保存回调必须排他写入；六张审批图由操作员在同一真实审批窗口快速调用，不能自动批准或等超时凑图。该模块的 mock 单元测试不是实际截图凭据。
