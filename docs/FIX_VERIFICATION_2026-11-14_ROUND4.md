# 光筑（Guangzhu）第四轮全仓深度审计闭环、跨入口极限反例加固、三赛材料同步与安装态重打包验收报告（2026-11-14 · Round 4）

本报告在第三轮验收报告 [FIX_VERIFICATION_2026-11-13_ROUND3.md](file:///c:/Users/%E5%8D%8E%E7%A1%95/Documents/ChatGPT/guangzhu/docs/FIX_VERIFICATION_2026-11-13_ROUND3.md) 基础上，针对第四轮全仓深度审计与极限反例排查（Wave 1 研发加固 `#72`/`#73`/`#74`、Wave 2 全仓 163 套 Python + 36 套 Node + 真浏览器 E2E 独立核验及缺陷回归闭环 `#82 -> #83 -> #86`、Wave 3A 空载计时账本与三赛文书重导出 `#90`、Wave 3B 安装包重编译与桌面双压缩包原子同步 `#91`），严格按 **“编号 → 代码文件与行号及 SHA-256 → 修前/修后实际输出 → 验证命令 → 输入输出路径与 SHA-256 → 仍未覆盖的真实边界”** 逐项如实记录。

---

## 一、只读与受保护边界零改动核验

对照 [snapshot-close.json](file:///c:/Users/%E5%8D%8E%E7%A1%95/Documents/ChatGPT/guangzhu/output/recheck-20261113/snapshot-close.json)、第一轮三维哈希基线与历史复审守护快照实测 SHA-256（汇总于 [wave2_qa_summary.json](file:///c:/Users/%E5%8D%8E%E7%A1%95/Documents/ChatGPT/guangzhu/output/recheck-20261114-round4/wave2_qa_summary.json)）：
- **26 个三维与壳层核心文件**（`pro-3d-twin-engine.js`、`scene*.js`、`scene.css`、`roofedit*.js`、`roofedit-objects.css`、`parapet-editor*`、`roof-parapets.js`、`facade-editor*`、`design-edit*`、`module-transform-geometry.js`、`park-scene-3d.js`、`app.js`、`index.html`［`e80b434b8fcdb1ce53f811f7dc7f1311555fc0af238823e69acb14d36f95c1cf`］）：**0 字节改动（26/26 SHA-256 100% 一致）**。
- **全部 12 份设备与工程目录 CSV**（`data/catalog/*.csv`）：**0 字节改动（12/12 SHA-256 100% 一致）**。
- **全部历史审查档案与原始复审证据目录**（`output/recheck-20261112/`、`output/recheck-20261113/`、`docs/*2026-11-04..13*`、`FIX_VERIFICATION_2026-11-12_ROUND2.md`、`FIX_VERIFICATION_2026-11-13_ROUND3.md`、`output/benchmark-ledger-20261112.json`、`output/release-manifest-20261112.json`、`output/release-manifest-20261113.json`、`output/wave2a-qa-summary.json` 共 566 个历史归档文件）：**0 字节改动（SHA-256 100% 一致）**。

---

## 二、逐项修复与独立反例实证台账

### 1. `R4-01`（`#72`）—— 《光筑专业报告》非法/极值输入硬校验、跨入口字段兼容、运维费量纲修正与零容量六页诚实降级

- **代码文件与行号及 SHA-256**：
  - [pvsyst_report.py](file:///c:/Users/%E5%8D%8E%E7%A1%95/Documents/ChatGPT/guangzhu/backend/guangzhu/report/pvsyst_report.py#L641-L789)（`_validate_report_payload_inputs`、`_check_num_field`、`_assert_no_nonfinite_floats` 拦截非字典请求体、任意嵌套 `NaN`/`Inf`、`bool` 冒充数值、负装机/负块数/负荷载/负损耗/负造价及越界经纬度；第 `1522` 行极区纬度安全钳制防 `pvlib` 晴空 `NaN`）
  - [pvsyst_report.py](file:///c:/Users/%E5%8D%8E%E7%A1%95/Documents/ChatGPT/guangzhu/backend/guangzhu/report/pvsyst_report.py#L1106-L1225)、[pvsyst_report.py](file:///c:/Users/%E5%8D%8E%E7%A1%95/Documents/ChatGPT/guangzhu/backend/guangzhu/report/pvsyst_report.py#L2392-L2444)、[pvsyst_report.py](file:///c:/Users/%E5%8D%8E%E7%A1%95/Documents/ChatGPT/guangzhu/backend/guangzhu/report/pvsyst_report.py#L4429-L4865)（消除单组件 `hot_vmpp_v` 覆盖组串 `string_hot_vmpp_v` 冲突；修正第 6 页年运维费 `dc_kw * 0.042 / 10.0` 万元/年 10 倍量纲偏差并计入第 13 年逆变器备品金；全量兼容创新实验室与卫星联动别名及显式 `0.0`/`None`；当 `dc_kw == 0` 或 `module_count == 0` 时强制六页 HTML 与 PDF 全链路输出 `0 块 / 0 串 (0S) / 0 台`、6 项国标全标 `UNVERIFIED`、`all_pass = False`、盖 `RECHECK REQUIRED` 章）—— SHA-256: `ba164c197326695785097f85cc355a6edeaf712efede37375c3cc31b2cb865c4`（`257,907` bytes）
- **修前 / 修后实际输出**：
  - **修前**：`satmap-3d-linkage.js` 展开单块组件 `hot_vmpp_v`（约 `38.4V`）覆盖整串热态电压；第 6 页现金流将 `42 元/kWp/年` 误算为 `0.42 万元/kWp/年`；`0 kWp` 请求若携带旧字段 `inverter_count=1, modules_per_string=18` 会在局部栏残留 `1 台` 或 `18S`；负数或 `NaN` 输入未统一抛 `ValueError`（HTTP `422`）。
  - **修后**：整串热态电压准确保持约 `690.7V`；25 年现金流运维支出与 `satmap_multifactor.py`、`pro-engineering-core.js` 完全一致；`dc_kw=0, module_count=0, inverter_count=1, modules_per_string=18` 在 HTML 与 6 页 PDF 第 1/2/5/6 页统一输出 `0 块`、`0 串`、`0 台`、`all_pass=False`、`RECHECK REQUIRED`，且全文与 PDF 元数据 **0 处** `PVsyst`；非法负值与 `NaN` 100% 返回 HTTP `422`。
- **验证命令**：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/test_pvsyst_professional_report.py tests/test_round4_deep_audit.py -k "zero_capacity or pvsyst" -q
  ```
- **输入输出路径与 SHA-256**：
  - 验证套件：[test_pvsyst_professional_report.py](file:///c:/Users/%E5%8D%8E%E7%A1%95/Documents/ChatGPT/guangzhu/tests/test_pvsyst_professional_report.py)、[test_round4_deep_audit.py](file:///c:/Users/%E5%8D%8E%E7%A1%95/Documents/ChatGPT/guangzhu/tests/test_round4_deep_audit.py)（`727a4ee646421b1486237df670c0dc35cacc3a6bdd50112cc12057fea1f0b2cc`）
  - 安装态内嵌 Python 实跑产物：[zero_cap_0kwp_recheck_6p.pdf](file:///c:/Users/%E5%8D%8E%E7%A1%95/Documents/ChatGPT/guangzhu/output/recheck-20261114-round4/installed_smoke/zero_cap_0kwp_recheck_6p.pdf)（6 页，`1,532,508` bytes，SHA-256: `e49283ee99d210c86c47b592471188f8aceb702945a60b26eb30d2758f9e8b24`）
- **仍未覆盖的真实边界**：极高纬度（`|lat| > 66.5°` 极昼/极夜区）物理仿真采用 `±66.5°` 晴空安全包络近似，系统聚焦中国及中低纬度工商业厂房场景。

---

### 2. `R4-02`（`#73` Fix 1 & Fix 2）—— `simulate_pvsyst` 直调热损系数 `E11` 透传与 `/api/pvsyst/simulate` 全参数联动

- **代码文件与行号及 SHA-256**：
  - [pvsyst_engine.py](file:///c:/Users/%E5%8D%8E%E7%A1%95/Documents/ChatGPT/guangzhu/backend/guangzhu/pvsyst_engine.py#L412-L538)、[pvsyst_engine.py](file:///c:/Users/%E5%8D%8E%E7%A1%95/Documents/ChatGPT/guangzhu/backend/guangzhu/pvsyst_engine.py#L988-L1004)（`simulate_pvsyst` 将 `uc_w_m2k=effective_uc, uv_w_m2k_ms=effective_uv` 直传 `fetch_live_weather`，并严格校核 `sub_arrays` 非布尔有限数值）—— SHA-256: `ad77f7f264455ced2a4a27486edfab8af34e420b9e7f09e8f191d704a35a5713`（`53,779` bytes）
  - [live_weather.py](file:///c:/Users/%E5%8D%8E%E7%A1%95/Documents/ChatGPT/guangzhu/backend/guangzhu/live_weather.py#L90-L106)、[live_weather.py](file:///c:/Users/%E5%8D%8E%E7%A1%95/Documents/ChatGPT/guangzhu/backend/guangzhu/live_weather.py#L415-L465) —— SHA-256: `d38773d34212a96f71763cdf00a44f2f9d26a27b31f9f97fdbf600c6d79f8c66`（`28,576` bytes）
  - [satmap_design.py](file:///c:/Users/%E5%8D%8E%E7%A1%95/Documents/ChatGPT/guangzhu/backend/guangzhu/satmap_design.py#L4345-L4455)（`api_pvsyst_simulate` 完整转发 `orientation_mode`、`snow_loss_pct`、`spectral_corr_pct`、`stc_eff_pct`、`bifacial_factor`）—— SHA-256: `61a1d7a06fe6708aea6e610578e738c1f4ffab72981fd44716c354216f15354c`（`206,014` bytes）
- **修前 / 修后实际输出**：
  - **修前**：直接调用 `pv.simulate_pvsyst(..., uc_w_m2k=10 vs 60, offline=True)` 时年并网电量改变，但内部调用 `fetch_live_weather` 漏传 `uc_w_m2k`/`uv_w_m2k_ms` 导致 `live_weather.hourly_48h` 保持不变；`POST /api/pvsyst/simulate` 漏转发 `orientation_mode`、`snow_loss_pct`、`stc_eff_pct`、`spectral_corr_pct`。
  - **修后**：直调 `simulate_pvsyst(32.4568, 119.9182, dc_kw=100, ac_kw=110, offline=True)` 时，`uc=10 -> 60` 使年发电量由 **`135,413.0 kWh`** 升至 **`153,068.0 kWh`**（`+17,655.0 kWh`），同时 48h 逐时交流功率总和由 **`790.14 kW·h`** 升至 **`884.83 kW·h`**（20 个日照时刻功率严格区分）；`POST /api/pvsyst/simulate` 在 `south_fixed`（`152,598.0 kWh`）与 `east_west`（`133,041.0 kWh`）、`snow_loss_pct=0` vs `8`、`stc_eff_pct=18%`（`555.6 m²`）vs `23%`（`434.8 m²`）、`spectral_corr_pct=-2` vs `+2` 下均产生物理单调响应。
- **验证命令**：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/test_round4_deep_audit.py -k "e11 or simulate" -q
  ```
- **输入输出路径与 SHA-256**：
  - 安装态内嵌 Python 实测记录：[installed_smoke_results.json](file:///c:/Users/%E5%8D%8E%E7%A1%95/Documents/ChatGPT/guangzhu/output/recheck-20261114-round4/installed_smoke/installed_smoke_results.json)（`35284e0d095100dfa006eac08c9f83ae003e725cb39a833fa308e34da973bf76`）
- **仍未覆盖的真实边界**：离线模式下 `live_weather` 基于内置典型气象年日照包络确定性合成 48h 功率曲线，不等同现场气象站分钟级实测辐射。

---

### 3. `R4-03`（`#73` Fix 3）—— 全后端接口 HTTP `422` 边界硬拦截与测试状态隔离

- **代码文件与行号及 SHA-256**：
  - [api.py](file:///c:/Users/%E5%8D%8E%E7%A1%95/Documents/ChatGPT/guangzhu/backend/guangzhu/api.py#L1606-L1895)（`_validate_pro_report_body` 及专业报告/仿真路由统一将 `GzError`、`(ValueError, TypeError)` 映射为 HTTP `422`，彻底消除未捕获 `500`；测试请求头 `X-Guangzhu-Test` 状态隔离）—— SHA-256: `f0ba5b5648430e8c35810b6fbb1e13973b9619f34a04003afe9f22a877d5fbad`（`101,350` bytes）
  - [satmap_multifactor.py](file:///c:/Users/%E5%8D%8E%E7%A1%95/Documents/ChatGPT/guangzhu/backend/guangzhu/satmap_multifactor.py#L44-L92)、[satmap_multifactor.py](file:///c:/Users/%E5%8D%8E%E7%A1%95/Documents/ChatGPT/guangzhu/backend/guangzhu/satmap_multifactor.py#L203-L393)（`validate_satmap_common_inputs`、`resolve_wind_snow_params` 拒绝 `bool`、`NaN`/`Inf`、负功率/负荷/电价/造价、越界 `soiling_pct`/`albedo` 及冲突风雪别名）—— SHA-256: `c6e3b4bf5a78530448ba67f381d108ae77c7221d6120fc3cbd882ef2715b44c7`（`147,205` bytes）
- **修前 / 修后实际输出**：
  - **修前**：部分卫星/仿真/报告端点传入原始 `NaN`、`True`（`bool` 是 `int` 子类）、负 `dc_kw` 或冲突风压字段（`w0_kn_m2=0.4` vs `structural_params.basic_wind_w0_kn_m2=0.9`）时可能返回 `200` 静默吞并或抛 `500`。
  - **修后**：跨 `/api/pvsyst/simulate`、`/api/pvsyst/live-weather`、`/api/satmap/design`、`/api/satmap/optimize-multifactor`、`/api/satmap/save-project`、`/api/satmap/sync-to-3d`、`/api/guangzhu/pro-report*` 全部非法/冲突输入 **100% 返回 HTTP `422`（零 `500`）**。
- **验证命令**：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/test_round4_deep_audit.py -k "strict_422 or weather" -q
  ```
- **输入输出路径与 SHA-256**：
  - 验证套件：[test_round4_deep_audit.py](file:///c:/Users/%E5%8D%8E%E7%A1%95/Documents/ChatGPT/guangzhu/tests/test_round4_deep_audit.py)（`727a4ee646421b1486237df670c0dc35cacc3a6bdd50112cc12057fea1f0b2cc`）
  - 真浏览器隔离端口 `51089` 冒烟核验：[e2e_summary.json](file:///c:/Users/%E5%8D%8E%E7%A1%95/Documents/ChatGPT/guangzhu/output/recheck-20261114-round4/e2e_summary.json)（`25a2c83d089f61b8146a53e057fedd82664e30298fd21ce0c7f144a30e389502`）
- **仍未覆盖的真实边界**：API 面向单机桌面 WebView2 / 本机回环地址服务设计，未内置公网多租户鉴权与分布式限流网关。

---

### 4. `R4-04`（`#73` Fix 4）—— 12 维多因素五候选方案完整电气拓扑与三维工程保存 100% 对账一致

- **代码文件与行号及 SHA-256**：
  - [satmap_multifactor.py](file:///c:/Users/%E5%8D%8E%E7%A1%95/Documents/ChatGPT/guangzhu/backend/guangzhu/satmap_multifactor.py#L1565-L2395)（采用与三维 `electrical.py` 同构的坡面切串 `_slice_slope_lengths` 与真实目录机型阶梯贪心配逆变器，完整填充全部 5 个候选方案的 `modules_per_string`、`string_count`、`inverter_count`、`ac_kw`、`dc_ac_ratio`、`mppt_ports_used`、`mppt_ports_total`、`module_id`、`inverter_id`、`setback_m`）
  - [satmap_design.py](file:///c:/Users/%E5%8D%8E%E7%A1%95/Documents/ChatGPT/guangzhu/backend/guangzhu/satmap_design.py#L2549-L2996)（`save_to_guangzhu_project` 精确解析 `580W` 等扩展目录型号、`modules_per_string`、退距与架空跨越障碍物净空）
- **修前 / 修后实际输出**：
  - **修前**：部分多因素候选方案缺少完整 `inverter_id` / `modules_per_string` 字段，采纳后保存为三维工程时存在组件数或逆变器台数二次重配偏差（`matched == False`）。
  - **修后**：`flush_lightweight_clamp`、`elevated_canopy_bridge`、`south_landscape_antishade_2p`、`east_west_butterfly`、`south_fixed_ballast_1p` 全部 5 个候选方案均携带完整非空电气分配字段，逐一保存至三维工程全部达成 `allocation_reconciliation.matched == True`（`diffs == []`）。
- **验证命令**：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/test_round4_deep_audit.py -k "multifactor" -q
  ```
- **输入输出路径与 SHA-256**：同 `R4-03`（`test_round4_deep_audit.py` `727a4ee6...`、`e2e_summary.json` `25a2c83d...`）。
- **仍未覆盖的真实边界**：复杂异形多边形屋面在卫星端矩形网格排布转入三维自由屋面后，若物理屋脊线与卫星描边存在大角度拓扑差异，仍按对账回执如实提示差异。

---

### 5. `R4-05` & `R4-06`（`#74` + Wave 2 `#82 -> #83`）—— 前端极限空值/零容量诚实性、跨项目隔离与两项实测回归修复

- **代码文件与行号及 SHA-256**：
  - [satmap-3d-linkage.js](file:///c:/Users/%E5%8D%8E%E7%A1%95/Documents/ChatGPT/guangzhu/desktop/web/satmap-3d-linkage.js#L17-L29)、[satmap-3d-linkage.js](file:///c:/Users/%E5%8D%8E%E7%A1%95/Documents/ChatGPT/guangzhu/desktop/web/satmap-3d-linkage.js#L163-L308)、[satmap-3d-linkage.js](file:///c:/Users/%E5%8D%8E%E7%A1%95/Documents/ChatGPT/guangzhu/desktop/web/satmap-3d-linkage.js#L473-L540)、[satmap-3d-linkage.js](file:///c:/Users/%E5%8D%8E%E7%A1%95/Documents/ChatGPT/guangzhu/desktop/web/satmap-3d-linkage.js#L1126-L2025)、[satmap-3d-linkage.js](file:///c:/Users/%E5%8D%8E%E7%A1%95/Documents/ChatGPT/guangzhu/desktop/web/satmap-3d-linkage.js#L2665-L3920)（`finiteNum`/`finiteOrNull` 区分合法 `0` 与 `null`/空白/`bool`；冷态 `Vmpp <= mppt_v_max` 限制最大安全串长；台风退距 `wind_ok` 按实际 `edgeSetbackM` 校核；8 项工程体检无伪造默认通过值；离线回退报告显著标 `OFFLINE UNVERIFIED PREVIEW`；清空 0 组件后导出不静默重排；按 `projectId` 分桶隔离 `latestScheme`；`#83` 修复 `/api/satmap/3d-catalog` 返回 `200` 空列表后误调不存在的 `GET /api/my-roofs` 导致浏览器 `404`）—— SHA-256: `7c48cb4dbf451a628d36a26aafb7c27a222174b8e3fc7af2ae1e7e8aed3cd2a3`（`183,811` bytes）
  - [innovation-lab.js](file:///c:/Users/%E5%8D%8E%E7%A1%95/Documents/ChatGPT/guangzhu/desktop/web/innovation-lab.js#L4-L16)、[innovation-lab.js](file:///c:/Users/%E5%8D%8E%E7%A1%95/Documents/ChatGPT/guangzhu/desktop/web/innovation-lab.js#L275-L775)、[innovation-lab.js](file:///c:/Users/%E5%8D%8E%E7%A1%95/Documents/ChatGPT/guangzhu/desktop/web/innovation-lab.js#L1225-L1530)（`dcKw=100, dcAcRatio=0.8 -> ac_kw=125` 精确换算；离线回退报告与三页签零 `NaN`/`undefined`/`PVsyst` 及严格中英纯度）—— SHA-256: `c545b33dc59d51de813442e8dcefc4ebefbaa5235f17032227071262bd5052ac`（`130,767` bytes）
  - [satmap-view.js](file:///c:/Users/%E5%8D%8E%E7%A1%95/Documents/ChatGPT/guangzhu/desktop/web/satmap-view.js#L2202-L2236) —— SHA-256: `c69cbce359d8a2b62781562a8d99cd36bba578d03caacb625baf9d883eeb1476`（`642,395` bytes）
  - [pro-engineering-core.js](file:///c:/Users/%E5%8D%8E%E7%A1%95/Documents/ChatGPT/guangzhu/desktop/web/pro-engineering-core.js#L21-L315)（`#83` 新增 `KNOWN_MODULE_PRESETS` 与 `KNOWN_INVERTER_PRESETS`，在保留显式 `null` 满载窗口与欧效的同时，修复仅含 `{id: equip.module_id}` 的三维工程规格在 `enrichModuleSpec` 下缺失 `vmp_v`/`voc_v` 引发 `#result/...` SVG `NaN` 控制台错误）—— SHA-256: `52b5705cdf8c140f10a8bda724d3be826fb6c86ab9f85e35031d9a9fa986199b`（`70,851` bytes）
  - [pvsyst-workbench.js](file:///c:/Users/%E5%8D%8E%E7%A1%95/Documents/ChatGPT/guangzhu/desktop/web/pvsyst-workbench.js#L888-L982)、[pvsyst-workbench.js](file:///c:/Users/%E5%8D%8E%E7%A1%95/Documents/ChatGPT/guangzhu/desktop/web/pvsyst-workbench.js#L1935-L2073) —— SHA-256: `dfccbf45e8b2545fc793d9eac8591990036f9701bc082f5a191af72815470ba9`（`194,605` bytes）
- **修前 / 修后实际输出**：
  - **修前**：`Number(null)` 在 `finiteNum` 中被误判为 `0` 覆盖默认参数；客户端多因素回退在 `12 m²` 小微屋面仍硬保底 16 块组件；Wave 2 全仓实跑 `test_t35_demo.py` 与 Chrome E2E 捕获到 `#result/...` 折叠工作台对仅带 `module_id` 的工程输出 `<rect width="NaN">` 控制台报错，以及三维导入弹窗在 `my_roofs: []` 时请求不存在的 `/api/my-roofs` 产生 `404`。
  - **修后**：`R4-UI-01..05` 全部反例断言通过；`test_t35_demo.py` 与无头 Chrome 全链路 E2E 达成 `console.error = 0`、`pageerror = 0`、`http_4xx = 0`、`http_5xx = 0`。
- **验证命令**：
  ```powershell
  node --test tests/desktop/round4-deep-audit.test.mjs
  .venv\Scripts\python.exe -m pytest tests/test_t35_demo.py tests/test_holistic_optimizations.py -q
  ```
- **输入输出路径与 SHA-256**：
  - 前端反例套件：[round4-deep-audit.test.mjs](file:///c:/Users/%E5%8D%8E%E7%A1%95/Documents/ChatGPT/guangzhu/tests/desktop/round4-deep-audit.test.mjs)（`19,847` bytes，SHA-256: `e511713783e4920cd4d788d375367217808b92112c7b47818bed5f8691a73cc1`）
- **仍未覆盖的真实边界**：浏览器端离线简版预览与客户端启发式回退仅用于后端不可达时的应急交互提示，正式工程交付须以已启动后端物理引擎导出的签章文件为准。

---

### 6. `R4-07`（Wave 3A `#90`）—— 空载计时账本重跑与三大赛事文书 DOCX/PDF 全量同步重导出

- **代码文件与行号及 SHA-256**：
  - 三赛说明稿：[DEMO.md](file:///c:/Users/%E5%8D%8E%E7%A1%95/Documents/ChatGPT/guangzhu/docs/materials/three-competitions-2026/DEMO.md)（`947fbad77b68881e6cabae4bba1b46a6d7d08dc2a46b39e8908daa0af9602906`）、[JIANGSU.md](file:///c:/Users/%E5%8D%8E%E7%A1%95/Documents/ChatGPT/guangzhu/docs/materials/three-competitions-2026/JIANGSU.md)（`844a804700bb332aae49ec7b0eb1bf1d7fad2caa62f2322ca92b40e17c05355e`）、[OPC.md](file:///c:/Users/%E5%8D%8E%E7%A1%95/Documents/ChatGPT/guangzhu/docs/materials/three-competitions-2026/OPC.md)（`f84b50d20303032951a8a16a3d00b13686f871a4033c872c728a9b1be2bad6b4`）、[HUMMINGBIRD.md](file:///c:/Users/%E5%8D%8E%E7%A1%95/Documents/ChatGPT/guangzhu/docs/materials/three-competitions-2026/HUMMINGBIRD.md)（`d9851e6a23d79276f881bd142be79a738a8279d0aefcf1996da3704cf068f6d0`）
  - 计划书生成脚本：`docs/materials/business-plans-2026/build_jiangsu_and_opc_plans.py`、`build_hummingbird_business_plan.py`
- **修前 / 修后实际输出**：
  - **修前**：`output/benchmark-ledger-20261113.json` 记录的 16 份源码哈希与测试统计停留于 Round 3 Wave 2B（`bench-20261114T032107Z`），尚未同步 Round 4 最新源码哈希与全仓 163 文件实跑测试计数。
  - **修后**（全新空载 `run_id: bench-20261114T090543Z`，`16/16` 后端与报告源码哈希 `0` 差异，`failures = 0`，五件套跨格式一致性 **`84/84` 项通过、`0` 错位**）：
    - `T-01`（卫星工作台 787 块 / 456.46 kWp + 6p Pro PDF + DXF + 4 张汇总 SVG）：真冷启 **`8.6203s`**｜进程首调 **`2.1588s`**｜热跑中位 **`1.7836s`**（`1.7541–1.8737s`）；
    - `T-02`（祥泰仓离线 AGH 三轮迭代闭环）：真冷启 **`18.1597s`**｜进程首调 **`14.5954s`**｜热跑中位 **`14.9171s`**（`13.2988–15.4127s`）；
    - `T-03`（三维全套本地五件套导出）：真冷启 **`8.9788s`**｜进程首调 **`6.2574s`**｜热跑中位 **`4.9023s`**（`4.8932–5.0429s`）；
    - `T-03b`（`SG50CX-P2` `90×580W = 52.20 kWp DC / 50.0 kW AC / 1 台` 五件套）：真冷启 **`14.9270s`**｜进程首调 **`5.7570s`**｜热跑中位 **`5.8261s`**（`5.6959–6.0509s`）；
    - 三份大赛 `.docx`/`.pdf` 经 Word COM 两遍目录重排核验 **`114/114` 目录条目页码匹配（`0` 未匹配）**，同步写入 Round 4 全仓实跑统计并保留全部诚实边界说明。
- **验证命令**：
  ```powershell
  .venv\Scripts\python.exe scripts/run_timed_benchmark_ledger_20261113.py
  py -3 scripts/export_three_competition_plans_docx_pdf.py
  ```
- **输入输出路径与 SHA-256**：
  - 实测计时账本：[benchmark-ledger-20261113.json](file:///c:/Users/%E5%8D%8E%E7%A1%95/Documents/ChatGPT/guangzhu/output/benchmark-ledger-20261113.json)（`55,144` bytes，SHA-256: `ddde482221a49ac992036e5ef0989a2ce3b1a7516961966e231c6626809516ed`）
  - 蜂鸟计划书（`37` 页，TOC `65/65`）：PDF `f83287530bc8001c6e78076d3f17e2447f92ab2a195e6397f1a956f491fca87a`（`4,426,363` bytes）｜DOCX `2f55b13d72d6d0f1dce5c74b281dceb29fcb0855f0bba3517e35dad2650a38ed`（`7,639,766` bytes）
  - 江苏技术验证书（`24` 页，TOC `30/30`）：PDF `5f904b91928a681ff80f4dcb4806d9bfb1fd2438bc3c90d336bdfecc8782d1af`（`3,919,307` bytes）｜DOCX `741f7761aa47fa7090ec3198848cc6e26e10c9bd44686994b301d6970d58e151`（`7,235,396` bytes）
  - 泰州 OPC 说明书（`16` 页，TOC `19/19`）：PDF `9af708e7f1733335fa5aa02b64434e979a5f1af51cbe8d8d5a3fa991b1b672d5`（`2,705,741` bytes）｜DOCX `f1860ac8453add8be2b254ddc51cf7517c64d8660bb1adfb73605608e6250926`（`4,687,448` bytes）
- **仍未覆盖的真实边界**：计时账本在 `offline=True` 下测量确定性物理与规则引擎耗时（`0 Token`），不含外网大模型 API 网络往返延迟与人工精细描边耗时。

---

## 三、Wave 2 全仓回归审计与 Wave 3B 独立安装态重打包核验

### 1. 全仓自动化测试横扫与空载性能预算（[wave2_qa_summary.json](file:///c:/Users/%E5%8D%8E%E7%A1%95/Documents/ChatGPT/guangzhu/output/recheck-20261114-round4/wave2_qa_summary.json)，SHA-256: `869fe4d395ff97936c56f02d7a9232f5e1eb79f7e444d95a84aacc604ab7189e`）
- **Round 4 新增深度反例测试套件**：
  - Python `tests/test_round4_deep_audit.py`：**`6/6 passed`**（`36,278` bytes，SHA-256: `727a4ee646421b1486237df670c0dc35cacc3a6bdd50112cc12057fea1f0b2cc`）
  - Node `tests/desktop/round4-deep-audit.test.mjs`：**`5/5 passed`**（`19,847` bytes，SHA-256: `e511713783e4920cd4d788d375367217808b92112c7b47818bed5f8691a73cc1`）
- **全仓 Python 测试横扫（`163` 个 `tests/test_*.py` 文件）**：共收集 `2,455` 项（`pyproject.toml` 默认反选 `2` 项 `@pytest.mark.network`，实选 `2,453` 项）→ **`2,328 passed, 125 skipped, 0 failed, 0 errors`**（JUnit XML 存档于 `output/recheck-20261114-round4/pytest-full-repo.xml`，SHA-256: `7d9eba18e90cc44faef837b39de742c015ec657a8537467f7738d732d74ba9f6`；`125` 项跳过均为仓库未随附的历史大体积归档快照、`T16_FULL_SDK=1` 开关及 Windows 符号链接权限跳过，与 2026-11-11 历史 `2,381` 批次明确区分）。
- **全仓 Node `.mjs` 测试横扫（`36` 个测试套件 + `2` 个辅助模块）**：
  - `32` 个 `tests/desktop/*.test.mjs`：`311` 项 → **`294 passed, 17 skipped, 0 failed`**（`17.53s`）；
  - `4` 个 `tests/embed_harness/*.test.mjs` + `tests/ui_shots/*.test.mjs`：`42` 项 → **`30 passed, 12 skipped, 0 failed`**（`0.25s`），2 个辅助模块（`ledger-fixture.mjs`、`replay.mjs`）导入校验通过。
- **SOLO 空载性能预算实测**：
  - `tests/test_shading_annual.py::test_500_module_annual_analysis_under_five_seconds_and_energy_balances`：**`1.081s`**（`< 5.0s` 预算通过，整文件 `2 passed in 3.77s`）；
  - `tests/test_analysis.py::test_offline_complete_analysis_recalculates_shading_under_ten_seconds`：**`6.325s`**（单测独立运行 **`5.814s`**，`< 10.0s` 预算通过，整文件 `8 passed in 26.58s`）。
- **真浏览器无头 Chrome 全链路 E2E 核验**（[e2e_summary.json](file:///c:/Users/%E5%8D%8E%E7%A1%95/Documents/ChatGPT/guangzhu/output/recheck-20261114-round4/e2e_summary.json)，`6,904` bytes，SHA-256: `25a2c83d089f61b8146a53e057fedd82664e30298fd21ce0c7f144a30e389502`）：隔离临时目录 + 随机端口 `51089` + `1440×900` 视口实跑 `#satmap` 五步全流程、三维导入、12 维多因素寻优与采纳、6 页专业报告弹窗（`15/15` 图标图像加载正常、`0` 溢出）、8 项工程体检、交付包下载、同步跳转 `#result/...` WebGL 三维场景、`#lab` 帕累托切换与 `<dialog>` 报告弹窗、`#park` 园区总览及全页面中英文切换，达成 **`uncaught_pageerror = 0`、`console.error = 0`、`cdp_exception = 0`、`http_5xx = 0`、`http_4xx_in_browser = 0`、`visible_pvsyst = 0`、`window.open_popup = 0`**。

### 2. Windows 安装包重编译、静默升级与三端哈希一致性（[release-manifest-20261114-round4.json](file:///c:/Users/%E5%8D%8E%E7%A1%95/Documents/ChatGPT/guangzhu/output/release-manifest-20261114-round4.json)）
- **构建与静默升级命令**：
  ```powershell
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_installer.ps1
  Start-Process -FilePath "c:\Users\华硕\Documents\ChatGPT\guangzhu\dist\guangzhu-setup.exe" -ArgumentList "/VERYSILENT","/SUPPRESSMSGBOXES","/NORESTART" -Wait
  ```
- **全新安装包产物**：[dist/guangzhu-setup.exe](file:///c:/Users/%E5%8D%8E%E7%A1%95/Documents/ChatGPT/guangzhu/dist/guangzhu-setup.exe)
  - 字节大小：**`150,390,244` bytes**
  - 新 SHA-256：**`9b238b16b3b364e74d210ac840bd9a83899a10f1095a06e1cbd3c797134d9f4e`**（已替换第三轮包 `c7a4d797cf16230ddd5c2683ae9aa86bc20ced535d05c64d1d685e90d2a1c412`）
  - `build-manifest.json` SHA-256：**`a7e989116bed0921bb65348bf0efedf59d8723438f7e962121826fc645507915`**
- **静默升级与三端一致性**：
  - 安装目录 `C:\Users\华硕\AppData\Local\Programs\guangzhu` 静默升级 `ExitCode = 0`；
  - `build-manifest.json` 所列 **`548/548`** 个 `application_files` 在本机安装目录与构建暂存目录 **0 差异**；仓库同路径可比对的 **`414/414`** 个文件及本轮全部 **`11/11`** 个改动源码文件（`pvsyst_engine.py`、`live_weather.py`、`satmap_multifactor.py`、`satmap_design.py`、`api.py`、`pvsyst_report.py`、`satmap-3d-linkage.js`、`innovation-lab.js`、`satmap-view.js`、`pvsyst-workbench.js`、`pro-engineering-core.js`）满足 `repo_sha256 == stage_sha256 == installed_sha256 == manifest_sha256` **100% 一致**；校验通过后立即安全清理临时暂存目录 `build\光筑-3b3fe3ebed4a418b875dc033458403e9`（清理后 C 盘可用空间 **`7.762 GB`**）。

### 3. 已安装内嵌 Python 隔离冒烟核验（[installed_smoke_results.json](file:///c:/Users/%E5%8D%8E%E7%A1%95/Documents/ChatGPT/guangzhu/output/recheck-20261114-round4/installed_smoke/installed_smoke_results.json)，SHA-256: `35284e0d095100dfa006eac08c9f83ae003e725cb39a833fa308e34da973bf76`）
使用 `C:\Users\华硕\AppData\Local\Programs\guangzhu\runtime\python\python.exe`（校验 `guangzhu.__file__` 严格位于安装目录且 `sys.path` 不含开发仓库）针对临时隔离目录完成三组实测：
1. **`E11` 直调热损系数联动**：`pv.simulate_pvsyst(32.4568, 119.9182, dc_kw=100, ac_kw=110, uc_w_m2k=10 vs 60, offline=True)` 实测年并网电量 `135,413.0 kWh` vs `153,068.0 kWh`，48h 实况功率总和 `790.14 kW·h` vs `884.83 kW·h`（20 个时刻严格区分）。
2. **`SG50CX-P2` + 90×`580W` 五件套全链路对账**：
   - `9×10S`（`sg50_10s/`）：`allocation_reconciliation.matched == True`，`2 台 / 100.0 kW AC / 52.2 kWp DC`；`bom.xlsx`（`f06be3b5...`）逆变器=`2`、组件=`90`；`layout.dxf`（`58600e55...`）组件图元=`90`；`drawing.pdf`（`4` 页，`a9c0bc9e...`）、`report.pdf`（`3` 页，`ba7069d0...`）、`guangzhu-pro.pdf`（`6` 页，`1,580,707` bytes，SHA-256: `fbd486768edc6ff2bbbfc7f32f1016dac6bf9817a658bdf4e5c15447489e8641`，`0` 处 `PVsyst`）。
   - `auto 5×18S`（`sg50_auto/`）：`allocation_reconciliation.matched == True`，`1 台 / 50.0 kW AC / 52.2 kWp DC`；`bom.xlsx`（`9f4de8ac...`）逆变器=`1`、组件=`90`；`layout.dxf`（`7abbee41...`）组件图元=`90`；`drawing.pdf`（`4` 页，`377e9cf2...`）、`report.pdf`（`3` 页，`8d820c03...`）、`guangzhu-pro.pdf`（`6` 页，`1,579,626` bytes，SHA-256: `b09e8f35538e611bf00e3314203c3ad94a94849de588f47c4c804f73ca97a927`，`0` 处 `PVsyst`）。
3. **`0 kWp / 0 块` 六页报告诚实降级**：即使传入陈旧 `inverter_count=1, modules_per_string=18`，HTML 与 6 页 [zero_cap_0kwp_recheck_6p.pdf](file:///c:/Users/%E5%8D%8E%E7%A1%95/Documents/ChatGPT/guangzhu/output/recheck-20261114-round4/installed_smoke/zero_cap_0kwp_recheck_6p.pdf)（`1,532,508` bytes，SHA-256: `e49283ee99d210c86c47b592471188f8aceb702945a60b26eb30d2758f9e8b24`）准确输出 `0 块 / 0 串 / 0 台`、6 项国标 `UNVERIFIED`、`all_pass == False`、印章 `RECHECK REQUIRED`（`0` 处 `PVsyst`）。

### 4. 桌面交付目录与双提交压缩包原子同步核验
- `C:\Users\华硕\Desktop\向光而筑—工厂屋顶光伏智能自动设计系统  ——石天\光筑windows安装包.exe`：`150,390,244` bytes，SHA-256 `9b238b16b3b364e74d210ac840bd9a83899a10f1095a06e1cbd3c797134d9f4e`（与 `dist\guangzhu-setup.exe` 100% 一致）。
- `C:\Users\华硕\Desktop\向光而筑—工厂屋顶光伏智能自动设计系统  ——石天\光筑—项目计划书.pdf`：`4,426,363` bytes，SHA-256 `f83287530bc8001c6e78076d3f17e2447f92ab2a195e6397f1a956f491fca87a`（与蜂鸟最新 37 页 PDF 100% 一致）。
- `C:\Users\华硕\Desktop\向光而筑—工厂屋顶光伏智能自动设计系统  ——石天.zip`：`422,912,124` bytes，SHA-256 **`218c67f487d71572045e120efd2f4aca80a413917dcc199ab3aff5284915c382`**（`10/10` 个条目全部显式置位 UTF-8 标志位 bit 11、`testzip()` CRC-32 全绿、直接从 ZIP 流读取内部 `.exe` 实测 SHA-256 为 `9b238b16b3b364e74d210ac840bd9a83899a10f1095a06e1cbd3c797134d9f4e`）。
- `C:\Users\华硕\Desktop\光筑_佐证材料_整理版.zip`：原子更新最新三赛 6 份 `.pdf`/`.docx`、最新空载计时账本 `benchmark-ledger-20261113.json`（`ddde4822...`）、Round 4 边界核验 6 页 PDF、Wave 2 全仓与 E2E 汇总（`wave2_qa_summary.json`、`e2e_summary.json`）、安装态冒烟汇总（`installed_smoke_results.json`）、发布清单 `release-manifest-20261114-round4.json` 及本报告 `FIX_VERIFICATION_2026-11-14_ROUND4.md`，并完整保留既有全部真实演示视频与系统截图（全部条目显式置位 UTF-8 bit 11 且通过 CRC-32 校验；最终容器字节大小与 SHA-256 记录于 `output/release-manifest-20261114-round4.json` 的 `desktop_sync.evidence_zip` 字段）。

---

## 四、诚实保留的尚未覆盖真实边界

1. **干净 Windows 虚拟机全新首次安装/卸载与数字签名信誉**：本轮已完成重编译安装包、本机 `%LOCALAPPDATA%\Programs\guangzhu` 静默升级、`548/548` 应用文件三端哈希核对及内嵌 Python 隔离冒烟，但尚未在无开发环境的全新干净 Windows 虚拟机中实测首次安装、桌面快捷方式冷启、卸载清理及 Windows SmartScreen 代码签名信誉提示。
2. **macOS 真机 `.dmg` 编译与挂载运行验证**：当前构建与测试宿主为 Windows 11，桌面交付目录中的 `光筑macOS安装包.dmg` 尚未在 macOS 真机环境中重新编译、挂载及启动验证。
3. **真实外部客户试用、商业成交与持证工程师双盲复核**：目前尚无已签约付费商业订单（三赛文书如实保持零商业付费收入表述）；人工与传统软件耗时对比仍定位为行业常规作业经验估算（待同输入持证工程师双盲计时复核）；软件输出定位为厂房光伏方案辅助设计与自动校核工具，不替代持证结构/电气工程师的现场勘察鉴定与施工图签章。
4. **在线付费大模型 API Token 计量与外网多轮实测台账**：本轮计时账本（`bench-20261114T090543Z`）全部在 `offline=True` 下测量本地确定性物理与规则引擎耗时（`0 Token`）；外网商业大模型 API 真实调用延迟、Token 费用流水及在线异常恢复率仍待正式接入付费 API 后另行核录。
