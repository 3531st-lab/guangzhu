# T10 内嵌验收页

仓库根目录运行（不会启动或修改 AGH）：

```powershell
.venv/Scripts/python.exe tests/embed_harness/server.py
```

打开 `http://127.0.0.1:8765`。AGH 需已在 `http://127.0.0.1:4177` 运行并启用插件。
服务仅绑定回环地址，静态文件白名单不提供项目文件。预制任务书由当前环境的 `python -m guangzhu.brief` 生成，不在 JS 复制模板。选择样例、模型后点「生成任务书」，核对文本再点「开始自动设计」。初始自动生成的文本采用默认审核编号；模型清单到达后应重新生成，确保使用当前选择的线路。

测试页不调用模型，不代替原生审批；所有审批都在右侧 AGH 原生卡片操作。生成任务书、传话和进度每条日志自动落盘到 `reports/assets/T10-spike/messages/<日志段>.messages.jsonl`；「导出日志与状态」另写 `.snapshot.json`，便于查 10 步、原文和 `session_id`。只创建以 `t10-` 开头的项目编号。可用 `--log-dir` 改日志输出目录。

- S2b：点开始后核对 `gz.session` 与原生第一条消息。任务书原文保存在 outgoing `gz.start.brief`。
- S7：展开任务书卡；两种普通消息按钮只填入文本，点「发送追问」才实际发送。
- S8：保持「iframe 640 px 验证」勾选；在 1440×900 窗口检查，点击顶部链接检查直接打开状态。
- S9：跟进、停止、打开会话各有按钮；勾选对话模式测试 `brief:null`；「缺失工作区」产生可控的 `gz.error`，不创建会话。未知类型用当前桌面源发；错误来源用独立 sandbox iframe 的 `null` 源向 AGH 发 `gz.hello`。日志里的 probe 请求编号不应收到任何 `re` 对应的回应。
- 「做不到」样例收到 `建议①②③` 时出现按钮，按原文字段发同会话追问；「到此为止」只在日志中标记，不发消息。
- 进入新会话后审批历史重新计算。正式是否满足单次导出审批仍以执行记录核对器为准。

离线验证：

```powershell
node --test tests/embed_harness/*.test.mjs
.venv/Scripts/python.exe -m pytest -q tests/test_embed_harness.py
node tests/embed_harness/replay.mjs reports/assets/T10-spike/messages/<日志段>.messages.jsonl
```

`computeSteps(nodes, {run, op, approvals, now})` 为纯函数；`approvals` 是当前会话收到的 `gz.approval` 消息历史，测试页添加毫秒 `received_at`，`now` 由调用者传入当前毫秒。每次导出单独核对：投影的决定节点须位于该次工具调用之后、下一次工具调用之前；等待信号时间须位于该次工具的 `started_at` 与 `ended_at` 之间，且不能被两次调用重复使用。无时间戳的历史等待信号不作为批准证据。返回 `steps`（数字、标题、状态、原始数字指标、轮次）、`warning`、`stopped`、`lastText`、`suggestions`。状态值为 `not_started/running/completed/issue/skipped`。不从没有出现在传话协议中的计费信息推算费用。

实际返回基准在 `actual-results.test.mjs` 中直接读取原始 ledger，而非重新拼一份带虚构字段的样例。`T09/changzhou-008` 没有建项目或审核调用，因此只断言八步完成，不能据此宣称 T10 一键十步通过；建项目字段另以已保存的 T10 MCP 冒烟返回检查，并明确它不是模型运行。

| 返回事件 seq | 指标与原值 |
| --- | --- |
| 48 | 保存了 4 个结构化字段，其中 3 项约束、1 项 notes；矛盾数组为空 |
| 66 | 全年水平面辐射 1359.53341 kWh/m²；cache_hit=true；source=NASA POWER UTC hourly；used=cache |
| 86 | 初稿 v1、390 块、214.5 kW |
| 104/142/180/218 | v1 16/22 hard1 → v2 16/22 hard1 → v3 17/22 hard0 → v9 16/22 hard0；通过数不等于总数减失败数，因为有不适用项 |
| 200 | 最快回本方案 v9：192.5 kW、4.0013 年、24.5337% |
| 236 | a链 1150.2628 kWh/kWp；跨天气来源最大差 218.5317，同 NASA a/b/c 最大差 27.0692；保留工具原始 note |
| 277 | files 映射有 4 项；另有 manifest；四数据文件哈希前缀为 27279909、5e637088、1c299ae7、81f5e2cc，manifest 前缀 1bfd3c0f |

`T09/agnes-review-003` 的 seq174 实际 `gz_record_review` 只返回 `ok/version/file`，没有 verdict/findings。因此缺少子审核 JSON 时，页面显示结论待核对、问题数未提供。能解析子审核 JSON 时只标为“审核员结论/问题数”，是否原样写入仍由执行记录核对器验证。缺字段不显示虚构的 0 或“满足要求”。

修复后的 S9 消息基准为 `t10-embed-20261002153216096.messages.jsonl`。记录显示 `brief:null` 创建新会话 `5d29b42c-75e5-48a7-92ad-24aa5e84b370`，首次投影为空且 idle；多行和 HTML 字符两次追问在同会话发送，原文逐字检查。未知类型、sandbox 的 null-origin 探针均无对应 `re` 回复，随后至少30秒仍有正常回传；无效工作区请求收到 `gz.error/INVALID`。早前修复前日志保留，不计为通过。消息测试不代替任务书/普通消息的截图验收。

`gz.cancel` / `gz.open` 的真实补测在 `t10-embed-20261002154318514.messages.jsonl`：15:47:00 发 cancel 后当前会话从 running 变为 idle；15:47:13 发 open 后重新打开上述 null-brief 会话，UUID和两条文字节点均与原日志一致。`bridge-evidence.test.mjs` 同时核对这两项。被取消的 `t10-changzhou-003` 实际调用了 `subagent_spawn`、没有导出，ledger 以 aborted 结束；它只提供控制消息证据，不计入三次成功运行。

独立审核后备无需新增页面功能：保存设计会话编号，将「设计模型」选择为 Agnes、「审核方式」选择为后备独立会话，填另一个 `t10-` 编号，在任务书框粘审核文本并点开始；也可勾选 `brief:null` 建空审核会话，再发送追问。非标准 JSON 任务文本采用当前审核方式设置；`run.review.mode=independent` 时，当前审核会话的 `gz_record_review` 成功即完成第9步，不要求 `subagent_fork`。切回设计会话时，在「会话编号」填原编号并点打开，待投影恢复后发送需要的追问。07第15节规定的后备是导出后另开 Agnes 审核会话，由该审核员调用 `gz_record_review` 并在网页批准；页面同样支持发只读审核文本、再切回设计会话传回原文的手动操作，但两种流程的实际验收结论必须分开记录。

此临时测试页一次展示一个会话的投影，不把独立审核的工具节点拼到设计会话，也不自动建立两个会话的父子关系。设计会话已有步骤在原投影和日志中保留；重新打开设计会话会恢复其工具投影，审核完成证据仍在独立审核会话/日志中。运行选项按已确认的 start 请求与 session UUID 缓存，打开已知会话恢复它自己的选项；未缓存的旧会话默认使用 `{}`，不会继承上一会话的 skip 或审核模式。日志回放遵循相同关联方式，不把尚未确认新会话的选项套到旧投影。

页面刷新后如需恢复设计会话的运行选项，重新选择原项目编号/样例/审核方式，点击「生成任务书」，保持生成正文不变，再填原UUID点「打开」。这只发送 `gz.open`，不会发送任务书、追问或更改AGH模型。收到该UUID的成功建项目/摘要工具返回后，必须只有一个实际project_id且等于当前Python生成任务书及项目框，才恢复run；错项目、多个项目、正文被编辑或缺少实际项目证据都不恢复。日志新增 `run.open-options` 和 `run.restored` 元数据，不另持久保存投影、任务书全文或凭据；回放也执行同一项目匹配。用户设置的显示选项不替代原会话任务书的业务指令。第9步仍保留独立审核证据边界，T14 再实现按同一项目关联的合并展示。

正式实跑证据见 `reports/assets/T10-spike/step-evidence.md`。`t10-runs.test.mjs` 回放常州006、L形001、旋转001（并保留失败尝试004的设计阶段证据），每次将五个显示数字逐项指向原生call/result序号与JSON字段，同时比较全部工具返回原文、10步状态、分析轮次及snapshot。004因导出后追问没有新compare，不计正式成功。

`t10-followup.test.mjs` 检查常州006两句原话各自触发新工具、what_if不计设计轮次、试算前后123文件整树SHA256不变。回答每个数字的核对表由 `reports/assets/T10-spike/006-followup-numbers.md` 保存。`t10-review.test.mjs` 检查三个实际Agnes会话都仅调用摘要/分析/复核/record各一次，保存的verdict/findings原样对应调用参数，且配对设计核对结果通过；不会把审核会话自身没有排板/导出的四步核对失败当作设计失败。
