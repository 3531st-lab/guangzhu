---
name: pv-rooftop-design
description: 用光筑 MCP 工具完成屋顶光伏排板、规则修正、方案比较和发电复核，保留可核对的版本链。
---

# 屋顶光伏设计

全程中文。只用 `gz_new_project`、`gz_project_summary`、`gz_set_requirements`、`gz_fetch_weather`、`gz_generate_layout`、`gz_analyze`、`gz_edit_design`、
`gz_compare_options`、`gz_crosscheck_yield`、`gz_record_review`、`gz_export`、`gz_wait`（可带 MCP 前缀）；非 independent 一键模式另可用 `subagent_fork`。不用 shell、文件、网页。
逐个调用、不并发。收到 `pending` 就用同一 `job_id` 调 `gz_wait`，一直等到正式结果；不停下、不重调原工具、不改用别的办法。
万一出现 `Request timed out`，先调用一次 `gz_project_summary`，再按原参数重调原工具，接上后台计算。
审批被拒（包括超时）时，停下并说“〈工具〉的审批没通过，等你点「重新申请」”，不换别的办法绕过。
用户说“重新申请”时，按原参数重新调用这个工具。版本以实际返回为准，每次修改保存父版本。

消息以「【光筑任务书」开头为**一键模式**：JSON 唯一依据，中途不提问，缺项用默认值并写入计划。普通模式遵照用户要求，缺项可询问或说明默认值。

1. 一键先用 `project.id/template/economics` 和任务书给定的 `equipment` 调 `gz_new_project`；`PROJECT_EXISTS` 即停，不能复用旧项目。普通模式用已有项目。
2. 建项目成功（含审批重试成功）后，必须单独调用 `gz_project_summary`；等摘要成功后用一句话说明计划，再调用 `gz_set_requirements` 原样保存需求。计划前只允许建空项目或读摘要，不取天气、不排板。边界和留空编号取摘要。
3. **检查点 A**：gz_set_requirements 返回 contradictions 非空，立即结束本轮工具调用，禁止再调用任何工具；不能用 gz_set_requirements 试写候选。最终做不到时也停止。只在文字里依据本次矛盾提出能解除整组冲突的单项建议，不编数值。
取消冲突下限是合法单项，无需先试保存；依赖该下限的预算不足、屋顶上限冲突同时不成立，其他要求不变。仍有矛盾的候选不得编号为建议；唯一可行候选必须列为建议①，不凑建议②③，无则只说明。建议置前，每条一行、最多三条、合计不超过200字，写原值/单位；说明后置。工具审批不等于同意放宽要求；
只有用户明确同意后才改该项、同步原文和结构化值并重存需求，仍有矛盾必须再停。
4. 本会话成功取 `nasa_hourly` 天气 → 生成初稿 → 分析，不能用旧设计代替。按 `level:hard` 不通过项的完整建议修改、原因写规则编号、再分析；`module_id_ranges` 只是压缩说明，按 `suggestions_format` 展开同前缀末尾数字的闭区间、
保留零填充，换成现有 `module_ids` 参数；不跨前缀、不补区间外缺号、不猜编号、不小批试删，兼容建议在同一次修改提交。普通最多6轮，一键最多 `run.max_rounds`。仍不过按检查点A停止，也说明建议级警告。
`where.worst_count` 原样提交：按本次分析原版本遮挡损失降序、编号升序取前指定数量；同批已删除的组件不重复补删。
U05、U06、U07、G07 不通过时照常按建议修改并重新分析；没有可执行建议时说明冲突，不自行放宽要求。

5. 硬性规则全过后做三方案；一键 `run.compare=false` 则跳过。选 `recommended[run.prefer]`（默认 balanced），把 `why` 告诉用户，不按方案名字自行挑。推荐当前方案时就用当前方案；跳过时用最后通过的版本。`tilt_trials` 仅挑倾角，不能当方案指标；摘要最新版本可能是候选，
`exported_versions` 才表示已导出版本。
摘要里 `roof_type` 是 metal 时不做三方案，也不改倾角；工具返回 `COMPARE_NOT_APPLICABLE` 时说明不适用，用当前通过的版本。
三方案已经比较正南、顺边、东西向人字形和横放补位，仍按 recommended 选。普通模式说“顺着厂房排”用 align=edge，说“东西向”用 layout=ew；说“多装”做三方案并按 max_capacity 推荐选，排板打开 fill_landscape。
6. 最终选定版本须串行：先单独调用 gz_analyze，等待成功结果；再单独调用 gz_crosscheck_yield，等待成功结果；之后才按任务书模式审核或申请 gz_export。不得在同一轮回复并发或批量调用这些工具。**每次三方案追问必须重新调用
`gz_compare_options`**，不能只引用旧结果；电价追问必须调用 `gz_analyze.what_if`，试算标“未保存”，不修改项目代替试算。最终回答和追问的所有数字只照抄本次相关工具返回，不自行推算工具未返回的百分比、增量或差值；`tilt_trials` 仍不能当方案指标。全程中文。
7. **先判断 `run.review.mode=independent`**：本设计会话不创建或调用任何审核员，禁用所有 `subagent_*`（含 fork、spawn、collect）及 `gz_record_review`；直接按第8条申请导出，完成后结束、不等待审核。
外部桌面软件之后另建 Agnes 原生会话发审核任务。否则，一键 `run.review.enabled=true` 时用 `subagent_fork`，model=`run.review.model`；question 原样用任务书审核员任务，只换「〔版本〕」。返回JSON由本会话调用
`gz_record_review`：version填审核版本，reviewer_model填`run.review.model`，verdict、findings逐字照抄。无可用JSON再审核一次，仍无则跳过并写“审核没有给出可用结论”。
revise且有high时按证据改一轮（reason引用审核item原文）、再分析复核、再审核；最多审核两次，仍有high就停止导出。
8. 普通导出按用户指令，一键仅 `run.export=true` 时申请。提醒用户只点「仅允许这次」并等待原生审批；拒绝或超时即停。本会话/永久授权不能作为单次批准；成功后给实际文件清单和校验值。
9. 一键最后七段：结论｜三方案｜规则｜复核｜审核｜导出｜放宽说明（无则写“无”）。所有数字来自工具。七段写给业主看，用中文说法，不写英文字段名、变量名和英文取值（写“朝向正南”“回本 3.5 年”，不写 south、payback_years；规则编号如 U04 可以写）。年发电写“基准年发电估算”（yield_kwh.p50，NASA POWER 2023 天气），不写 P50；五链差异写“复核范围，不是置信区间”；屋面荷载未经结构核定（roof.load_verified 不为真）时写“示意值，待结构核定”。
只有摘要 `roof_type` 是 metal（彩钢瓦）时，三方案段才写“彩钢瓦，不适用”；其他屋顶照写三方案结果。
任务书有「开工前问答」一行时，七段后加第八段「开工前核实」：照抄那一行的「要当心」和「没填」两项，不改写、不加字段名，不自己从 `facts` 推断（没填不等于否定，
没填余电上网不等于只能自用），不写新数字；最后写“逐项核对见方案书「开工前要核实的事」”。把 facts 中已填的 roof_age_years、transformer_kva 传给 gz_new_project.facts，用于翻新和分时资格；其余 facts 用于提醒；月用电量和班次已经在 economics 里，由工具算自用比例，不自己算。

**子审核员**只用摘要、分析、发电复核三个业务只读工具，各一次；复核分页除外：`next_group_offset` 非空时用 `group_offset` 续取全部朝向组，各页合计均为全设计；所有数字照抄。允许 `gz_wait` 持续等待正式结果，最后返回JSON，不调用`gz_record_review`。后备独立审核会话可自行保存审核；均不改方案、不导出。

多坡面或多朝向的组件按坡面编号、倾角、朝向分组。分析、组串和发电复核均按组计算；不要自行合并组串或重算发电。设计员也须按复核返回的 `next_group_offset` 续取，直至为空。

峰谷、税、贷款已经在工具中算好，回本照抄工具返回。U04口径看payback_basis；未标注为税前，不自行换算。
风荷载参数未核验时照抄示意说明；L01按最不利区，W01按夹具实际布点。平屋顶压块后超过屋面承重的支架，工具已自动改用锚栓固定，照抄摘要 wind.anchors 的个数。不能减少抗风所需压块消除承重失败；无可执行建议时请结构人员或厂家复核。

ground/carport称“新建安装面”：空地G08核对实际最低角点，车棚G09核对梁底净高，L01不适用，基础及钢结构须厂家设计。
空地可传lower_edge_m、road_every、road_width_m、fence_setback_m；车棚可传clear_height_m、0–15°tilt_deg，三方案照常按工具推荐。
土地性质与建筑附属同红线仅作待核事实，不自行宣布建设或备案合规；新建方阵不得占用任何耕地。年度地租是投资人支出，不再重复扣屋顶租金。
