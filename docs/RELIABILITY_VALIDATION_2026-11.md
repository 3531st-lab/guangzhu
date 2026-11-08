# 光筑 0.3.0 可靠性修复与安装验收

验收日期：2026-11-04。对应 [Antigravity 改动审查](ANTIGRAVITY_REVIEW_2026-11-04.md)，保留并修复新增的设计入口、设备选择、快捷操作与案例。此版本尚未发布至 GitHub Release；现有公开 v0.2.0 包不包含这些修复。

## 修复范围

| 审查项 | 当前实现与证据 |
| --- | --- |
| 完整页面启动 | 修正屋顶编辑模块语法错误；浏览器加载真实 app、scene、bridge 等模块，验证主页、编辑器、结果和园区路由。 |
| 原生窗口启动 | 实际试装发现就绪探针受 AGH 启动延迟影响，误报自身端口被占用；改用独立的快速安装身份接口，仍拒绝其他安装或其他服务。修复后原生窗口成功打开；最终干净安装结果另列。 |
| 升级配置恢复 | 实际覆盖安装发现旧 MCP 连接未就绪时，读取工具目录的错误绕过重连；改为先检查连接状态再读取目录。HTTP 错误分别记录安全状态码，不再误报为端口无法连接。 |
| AGH 就绪等待 | 首次原生启动曾失败，旧日志无法确定具体触发项；回归另确认短探测会过早放弃的缺口。HTTP、后台连接与进程存活改在同一 120 秒窗口内共同确认，成功后不做会推翻结果的额外 HTTP 探测。新增仅记录状态布尔值、时间和退出码的诊断，不记录凭据或命令参数。 |
| 嵌入页面字体 | 实际安装版浏览器检查发现插件相对字体路径返回 404；改用 AGH 提供的皮肤资源路径。字体修复当轮的重打包与前一包比较，524 项应用文件中仅插件字体 CSS 内容变化，其他运行文件摘要一致。 |
| 窄窗口结果侧栏 | 全量回归发现 390 像素视口被网格最小宽度撑至 532 像素；约束侧栏与工程区网格列，并让设备选择控件按可用宽度折列。没有隐藏内容；三种尺寸均验证控件可操作，完整离线演示原用例复验通过。 |
| 项目数据保护 | 新自动设计使用新编号；重复编号、无效模板及禁止覆盖请求在写入前拒绝；不删除既有项目。模板原有约束保留，只覆盖明确输入。 |
| 审核与导出 | 免 Key 路径称为规则预检查；预览具体版本后由用户批准导出。单次批准绑定设计、项目输入及计算文件；改输入或重复消费旧凭据将拒绝。独立审核只接受核验过且版本与输入匹配的真实归档。 |
| 报告版本 | 指定版本贯穿设计、分析、对比与审核；默认本地结果使用最后选定的版本。比较生成的更大版本号不替代用户选择。 |
| 铝缆计算 | 从同一目录记录读取材质、截面、载流量、电阻和价格；计算、BOM、费用及图纸一致。 |
| 图表 | 遮挡读取真实结果；月度发电由逐时结果汇总，自用、上网和限发使用同一计算口径。缺数据显示未计算，不代入固定比例。 |
| 下载 | 只返回经批准已生成的文件；缺文件、版本失效和未批准给出明确错误，不在下载时绕过流程生成。 |
| 快捷修改 | 容量操作使用存储层支持的 schema，遵守组件锁定；无法达到要求时说明原因。 |
| 厂商品牌 | Ginlong、Solis、Ginlong Solis 和锦浪规范为同一厂商标识。 |
| 凹屋顶通道 | 通道按实际屋顶边界裁切；L/U/T 型及旋转轮廓通过生成、保存和重新打开。 |
| 扩展组件 | 八款组件明确为代理模型，保存来源、拟合方法、参数摘要和已测误差；未声称厂家认证或已知全年误差。 |
| 案例与园区 | 四个泰州产业案例标为合成，负荷、电价与结构假设可查；园区汇总只使用位置、屋顶和输入仍匹配的选定结果，正式导出还要求当前批准记录。 |
| 安装与分发 | 安装包包含新前端、后端及合成园区种子；首次安装初始化园区，升级保留已有编辑。公共插件只包含内置模板，不带入本机园区或私人屋顶。 |

旧计算结果保留原文件。计算引擎版本及设备目录摘要已加入输入签名；修复前结果需要重新计算才能作为当前有效结果使用。

## 已完成的专项验证

下面各套件有重叠，不应相加当作独立任务数量。

- 当前源码的全部四组 Node 测试：**334 通过、36 跳过、0 失败**，覆盖 33 个测试文件；[完整计数与跳过项](../output/reliability-repair-20261104/node-delivery-summary.json)。其中桌面前端 252/17、嵌入桥接 22/5、插件 52/7、补充界面逻辑 8/7（分别为通过/跳过）。对应[桌面日志](../output/reliability-repair-20261104/frontend-node-delivery.log)、[桥接日志](../output/reliability-repair-20261104/embed-node-delivery.log)、[插件日志](../output/reliability-repair-20261104/plugin-node-delivery.log)、[补充日志](../output/reliability-repair-20261104/ui-shots-node-delivery.log)。
- 小窗口首页：11 通过，覆盖 1280×680、1100×650、两种配置状态及页面往返；[日志](../output/reliability-repair-20261104/home-layout-green.log)。
- 原生启动、安装身份与版本：33 通过；[日志](../output/reliability-repair-20261104/native-startup-green.log)。
- 升级配置修复后的安装配置、原生启动与案例初始化：108 通过；[日志](../output/reliability-repair-20261104/setup-upgrade-green.log)、[JUnit](../output/reliability-repair-20261104/setup-upgrade-green.xml)。三个新增回归先复现连接恢复与错误分类缺陷，再验证修复。
- AGH 就绪时序修复后的进程归属、桌面、配置和安装相关测试：150 通过；[日志](../output/reliability-repair-20261104/agh-readiness-related.log)、[JUnit](../output/reliability-repair-20261104/agh-readiness-related.xml)。新增 8 项回归先失败后通过，覆盖瞬时探测失败、重复 HTTP 探测、截止时间、进程退出和外部实例保护。
- 完整应用浏览器：6 通过；[日志](../output/reliability-repair-20261104/frontend-browser-final.log)。该套件加载完整前端与真实 Three.js，部分 API 返回受控边界数据；不能单凭它证明完整工程计算。
- 凹屋顶通道：10 通过；[日志](../output/reliability-repair-20261104/frontend-corridors-final.log)。
- 设备与全年发电专项：53 通过，包含八款组件的全年逐时计算；[验证数据](../output/reliability-repair-20261104/equipment-validation.json)、[说明](../output/reliability-repair-20261104/equipment-repair.md)。
- 本地导出与报告核心回归：13 通过；后续单次批准、同版输入变化及归档幂等边界：9 通过；[核心日志](../output/reliability-repair-20261104/backend-focused.log)、[边界日志](../output/reliability-repair-20261104/backend-final-edges.log)。
- 插件生成与私人园区排除：11 通过；[日志](../output/reliability-repair-20261104/plugin-regression.log)。
- 差异空白检查：`git -c core.whitespace=cr-at-eol diff --check` 通过。仓库 `* -text` 保留 Windows 换行字节，未对有摘要绑定的数据做批量换行改写。

Node 的 36 项跳过由源码中 34 处无条件 `test.skip` 声明产生，其中一处循环生成 3 项；不是本次运行根据系统或资源状态自动跳过。逐项核对涉及历史运行/捕获/账本 26 项、AGH 投影 5 项、消息录样 3 项、舍入输入 1 项、投影与运行混合依赖 1 项，列出的 26 个唯一必需归档路径均不存在。它们未执行，不计入 334 项通过；恢复原始归档后还需显式启用测试，不能仅凭补文件视为通过。声明行、依赖路径和核对依据见上述 Node 汇总。

## 源码四案例端到端验收

[验收脚本](../scripts/acceptance_demo.py)在隔离目录内执行真实排布、逐时发电、遮挡、电气和荷载计算，没有替换数值计算。四例共 **197/197 项检查通过**；[机器回执](../output/reliability-repair-20261104/acceptance-source.json)、[完整日志](../output/reliability-repair-20261104/acceptance-source.log)。这些为源码运行结果，不能替代安装版验收。

| 合成案例 | 最终版本 | 直流容量 |
| --- | --- | --- |
| 医药洁净厂房 | v5 | 173.25 kW |
| 海工车间 | v5 | 268.40 kW |
| 文旅坡屋面 | v4 | 102.85 kW |
| 农业冷链仓 | v17 | 168.30 kW |

流程覆盖自动设计、锁定与修改、容量和设备选择、铜/铝电缆、无效请求不改文件、版本报告、导出预览与单次批准、真实 DXF/XLSX 解析及重新打开。冷链方案比较选定 v12，即使存在更大的候选 v14，也不会误用最大版本号；随后修改及复算产生 v17。计算耗时按日志记录，不宣传为三秒完成。

## 全量回归与实际安装

默认全量 2,381 个节点及必要复验已完成：**2,256 通过、125 跳过、0 失败、0 遗漏**，25 个批次的退出结果、JUnit 与逐节点记录均核对一致。目前正在显式运行 4 项默认关闭的大型本地 SDK 实算测试；它们将覆盖原有 4 项跳过，不增加节点总数。最后发现的结果侧栏溢出已修复并通过源码回归，更新后的安装包仍待构建与实际安装验收，因此这里尚不是最终交付统计。

两项默认排除的实时公共天气接口测试已单独执行，NASA、PVGIS 均通过；新建空缓存，结果标记为真实下载，没有模型调用。[联网测试日志](../output/reliability-repair-20261104/network-live-final.log)、[JUnit](../output/reliability-repair-20261104/network-live-final.xml)。这 2 项不与默认 2,381 节点重复计数。

大型 SDK 验收还记录了一次测试环境对齐：参考计算所在的自建 pytest 进程最初为 Windows 系统管理的执行速度策略，而产品 SDK 启动时会显式禁用该进程的执行速度节流。2026-11-04 15:09:06 UTC，仅将已核实的测试进程对齐为产品的 `control=1/state=0`，优先级保持原值，未修改全局电源设置、产品、测试或超时断言。[只读核对](../output/reliability-repair-20261104/sdk-power-readonly-audit-150636.json)与[前后状态回执](../output/reliability-repair-20261104/sdk-pytest-execution-policy-alignment.after.json)均保留。按[微软定义](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-setprocessinformation)，原 `0/0` 不能证明 EcoQoS 已启用；不能把两条路径的耗时差全归因于节流，也不能把这次中途调整前后的计时当作严格性能对比。原始耗时没有改写。

当前[安装包](../dist/guangzhu-setup.exe)为 **149,634,024 字节**，SHA256 为 `50AADBDDD06651A0ED409FAA254864E7C50DA0D1E7BD910FFF4563666DE70B63`。它使用官方 AGH 与内置 Python 运行时；4,856 个文件的构建检查和真实离线计算自检通过。自检用于验证运行时，不代表自检样例的每项工程规则均合格。[包大小与摘要](../dist/guangzhu-setup.size.json)、[构建日志](../output/reliability-repair-20261104/build-installer-final.log)均已保存。

该包已修复实际浏览器验收发现的字体路径 404。与[字体修复前归档包](../output/reliability-repair-20261104/candidate-before-font-route-fix/guangzhu-setup.exe)比较，仅插件 CSS 中两处字体 URL 变化；其余运行文件和依赖元数据一致，见[安装清单差异](../output/reliability-repair-20261104/font-package-manifest-diff.json)。旧包及其验收证据保留，未作为新包证据冒用。

实际覆盖安装完成后，[完整性回执](../output/reliability-repair-20261104/installed-integrity.json)核对了 524/524 个安装清单文件、174/174 个源码对应文件及 26/26 个升级前数据文件。安装配置成功，没有候选包曾出现的自动配置警告。[安装日志](../output/reliability-repair-20261104/install-final.log)与[安装结果](../output/reliability-repair-20261104/install-final-result.json)保留了真实退出结果和包摘要。

当前字体修复后的安装版通过实际 HTTP 接口重新执行四案例，**197/197 项检查通过**，总用时 286.349 秒，没有模型调用，也没有替换物理计算函数。[最终回执](../output/acceptance-installed-final.json)、[完整日志](../output/acceptance-installed-final.log)对应项目 `accept-d4f4954a-*`。四例完整工程汇总与规则结果和源码版逐对象一致，主数值差均为 0；升级基线 26 个文件仍全部一致，见[一致性回执](../output/acceptance-installed-final-parity.json)。医药、海工、文旅、冷链分别用时 60.735、46.364、32.360、146.608 秒，这些是当前机器上的观测值，不是对其他机器或输入的耗时承诺。字体修复前的 197 项结果另存于[归档目录](../output/reliability-repair-20261104/candidate-before-font-route-fix)。

字体修复前的原生程序从安装目录连续启动三次，AGH、12 个工具、插件、工作区、设计 Skill 与离线自检均通过，分别耗时 75.27、36.64、31.64 秒（从启动后的观察程序开始计时）。三次均实际观察原生首页并正常关闭，进程及 8766/4178 端口自行释放；第二次清理超过最初 10 秒检查窗口，未强制结束进程。证据保存在[旧包验收目录](../output/reliability-repair-20261104/candidate-before-font-route-fix)。

字体修复后的新包已完成再次实际安装、启动和正常关闭后的重启，身份与安装清单摘要 `6b997c40a4284b66b4f64536a055613e6620de541918e8aee09d1633511ec144` 一致；上述内置组件步骤分别在 61.19、34.02 秒内就绪，真实首页和升级前自建屋顶均可见。[新包启动](../output/reliability-repair-20261104/native-final-cycle-4.json)、[重启](../output/reliability-repair-20261104/native-final-cycle-5.json)、[安装身份](../output/reliability-repair-20261104/native-final-identity.json)。模型 Key 未配置，模型步骤单独记为待配置，不计为通过。

重启后，通过原生首页“本机已生成 3D 方案”实际打开 `my-1104-180016-1104-2020`，界面显示“v9 · 已导出版本”和 64 块组件，三维场景正常可见。设计摘要与浏览器验收时一致，DXF、XLSX 摘要及升级基线 26 文件均未变化，见[重开校验](../output/reliability-repair-20261104/native-reopen-after.json)。两次原生窗口均正常关闭，进程及 8766/4178 端口自行释放，没有强制结束进程；[关闭 4](../output/reliability-repair-20261104/native-final-close-4.json)、[关闭 5](../output/reliability-repair-20261104/native-final-close-5.json)。

字体修复前的首次实际安装版浏览器验收为 6/8 项通过，原始结果与录像保存在[首次浏览器证据目录](../output/reliability-repair-20261104/installed-browser-final)。一项失败是验收脚本把 URL 字符串误当作含 `fragment` 属性的对象；另一项在页面切换后标题断言失败，稍后截图已有正确项目，但原记录缺少失败瞬间的值，不能确定具体原因。脚本已修正 URL 处理，并等待明确的项目及版本标题、增加现场日志；新包另行复验。该轮真实字体 404 已按上表修复，原失败记录未删除。

字体修复后首轮浏览器复验为 4/9 项通过。真实字体、首页、园区、屋顶保存重开通过；五项失败均由新增标题匹配过严造成：它误拒绝“未导出·查看版本 v9”和“v1（历史版本）”。失败时的项目、版本及页面值已记录；未改产品代码或等待时限。修正后的匹配按确切项目与独立版本标记核对，7 种实际状态正例和 8 种错误项目/版本反例均已验证。该轮[完整证据](../output/reliability-repair-20261104/installed-browser-final-recheck)及运行时脚本原文保留，后续完整复验如下。

随后完整重跑为 **8/9 项通过**：首页、真实点击规则设计→预览→批准→下载 DXF/XLSX→刷新重开、四案例的三维/热力/月度/历史/报告、园区、37° 旋转 U 形屋顶保存重开均通过。界面生成项目 `my-1104-180016-1104-2020` 的 v9，64 块组件；两份下载文件与批准清单的 SHA256 一致，刷新后设计摘要不变。[完整回执](../output/reliability-repair-20261104/installed-browser-final-recheck2/browser-acceptance.json)、[原速录像](../output/reliability-repair-20261104/installed-browser-final-recheck2/acceptance-original-speed.webm)、[实际下载文件](../output/reliability-repair-20261104/installed-browser-final-recheck2/downloads)可复查。该轮无 HTTP 错误、无页面脚本异常；导航时终止的长连接请求单独保留。唯一未通过项为隐藏 iframe 内的字体注册等待超时，原始退出码 1 与 8/9 结果均保留。

随后仅复验字体：首页与字体两项 **2/2 通过**，未重跑工程计算，也未改产品。实际 iframe 的宿主处于 `visibility:hidden`，在约 253 毫秒观察窗内未触发动画帧回调，而计时器正常；这支持默认动画帧轮询不适合隐藏页面的判断。脚本改为每 100 毫秒检查，保持原 45 秒上限。两款真实字体均从 `unloaded` 变为 `loaded`，两条皮肤资源 URL 返回 200，无 HTTP、页面或请求错误。[字体专项回执](../output/reliability-repair-20261104/installed-browser-fonts-final/browser-acceptance.json)、[完整浏览器证据说明](../output/reliability-repair-20261104/BROWSER-ACCEPTANCE-FINAL.md)。最终九项验收范围都有通过证据，但没有把不同轮次拼成虚构的单轮 9/9。

此前的单进程全量 Python 测试因 Windows 访问冲突结束，没有完整 JUnit，不能算作通过；[原始日志](../output/reliability-repair-20261104/full-python-final.log)保留。后续改为串行、隔离的小批运行并逐节点归并。高内存压力下出现的两个 WebGL 操作用例超时，在原 30 秒等待、原 fixture 和原产品代码下低负载复验，2 项均通过、共 70.43 秒；[复验日志](../output/reliability-repair-20261104/webgl-timeout-recheck-20261104-serial/pytest.log)与原失败记录均保留。这不能证明最初的 Windows 访问冲突根因已经确定。

分批验证还纠正了旧测试中的异步等待协议、无效小时数据、目录字段/Excel 格式断言，以及测试运行器的临时目录隔离方式。[六项复验](../output/reliability-repair-20261104/backend-contract-rechecks.xml)全部通过，未删去原业务与工程结果断言。最终独立节点总数以完整归并表为准，各专项与后续复验不能叠加计数。

另一个批次最初出现 8 项失败：5 项旧 Excel 校验仍只接受截面字符串，3 项遮挡夹具保存的 JSON 字节格式与完成清单要求不同。修正测试 helper 后，Excel 仍精确核对归档型号、目录 ID、数量、单位和篡改拒绝，并兼容旧格式；遮挡夹具仅采用真实写入器的序列化格式，原有组件数量、预算和选定 ID 断言保留。没有修改产品代码或新增测试节点。该批完整复验为 **179 通过、1 项历史归档跳过**，默认排除的 2 项联网测试另行记录；[复验日志](../output/reliability-repair-20261104/backend10-contract-recheck.log)、[JUnit](../output/reliability-repair-20261104/backend10-contract-recheck.xml)、[原夹具诊断](../output/reliability-repair-20261104/worst-count-fixture-diagnosis.json)均保留。

DXF 界面旧测试默认把小矩形当作禁区，而当前“自动”模式将其识别并完整保存为屋顶设备，原坐标和尺寸没有丢失。该测试改为明确选择“禁区”，保留毫米换算、面积、坐标、保存和无页面异常断言，原节点复验 **1 项通过**；[原保存数据与诊断](../output/reliability-repair-20261104/dxf-role-test-diagnosis.json)、[复验日志](../output/reliability-repair-20261104/dxf-role-contract-recheck.log)。这项修正没有修改产品行为。

窄窗口修复先在未改产品时复现了 390×844 视口宽度 532 的失败，再用保留的真实计算结果确认网格约束原因。修复后的 1440×900、1366×768、390×844 均满足原滚动边界，各尺寸的 27 个控件可触达、5 个选择框可改选恢复、输入可填写。[布局修复证据](../output/reliability-repair-20261104/t35-responsive-repair.json)与[完整原用例复验](../output/reliability-repair-20261104/t35-overflow-fixed.log)分开记录；后者实际完成计算、导出、三维操作、导航恢复与 PDF 流程，1 项通过。

相关首页测试另复现了窗口缩放后首次滚轮无效：原 200 毫秒后没有滚动事件，期间也没有页面重绘。每次新建页面的对照中，仅改变滚动传递样式仍失败；原产品在两帧绘制完成后发送同一次滚轮事件即可成功，详见[事件与对照证据](../output/reliability-repair-20261104/home-wheel-causal-diagnosis.json)。只为测试增加视口绘制同步，保持原坐标、滚动量、200 毫秒等待及业务断言；两种配置状态复验 **2 项通过**。这支持测试输入就绪时序的判断，不声称已确定浏览器内部实现原因。

## 使用与参赛边界

- 规则自动设计、规则指令解析和 AGH 模型路径分别展示；本地批准导出不等于独立工程审核。
- 当前泰州案例没有真实测绘、客户授权、已建电站或经营收入证据。它们用于软件演示，不能作为客户落地或收入佐证。
- 缓存齐全的场景可离线计算；首次新地点可能需要联网取天气。没有实际断网验证的路径不能宣传为完全离线。
- 设备代理参数、屋面承载、固定方式、接网和经济假设仍需专业复核。结果用于方案讨论，不是施工许可或工程安全认证。
- 本轮未为获奖概率、节约人力百分比或“3 秒完成”等宣传补造数字。真实客户、签字承诺与参赛人资格须由参赛者按实际情况补齐。

三项比赛分别使用[江苏技术稿](materials/three-competitions-2026/JIANGSU.md)、[OPC 工作流与路演稿](materials/three-competitions-2026/OPC.md)、[蜂鸟经营稿](materials/three-competitions-2026/HUMMINGBIRD.md)。资格、来源和待补项见[证据表](materials/three-competitions-2026/EVIDENCE.md)。没有代为报名或提交。
