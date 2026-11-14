// Full-Application Pure Chinese (ZH) & Pure English (EN) Internationalization Engine for Guangzhu (光筑)

let _currentLang = 'zh';

try {
  if (typeof localStorage !== 'undefined' && localStorage) {
    const saved = localStorage.getItem('gz-lang');
    if (saved === 'en' || saved === 'zh') {
      _currentLang = saved;
    }
  }
} catch (_) {
  // Ignore storage errors in headless / node test environments
}

export function getLang() {
  return _currentLang;
}

export function setLang(lang) {
  _currentLang = lang === 'en' ? 'en' : 'zh';
  try {
    if (typeof localStorage !== 'undefined' && localStorage) {
      localStorage.setItem('gz-lang', _currentLang);
    }
  } catch (_) {}
  if (typeof document !== 'undefined' && document?.documentElement) {
    document.documentElement.lang = _currentLang === 'en' ? 'en' : 'zh-CN';
  }
  return _currentLang;
}

export function toggleLang() {
  return setLang(_currentLang === 'zh' ? 'en' : 'zh');
}

export function t(zh, en) {
  return _currentLang === 'en' ? en : zh;
}

export const NAV_LABELS = {
  '#new': { zh: '三维设计', en: '3D Design' },
  '#satmap': { zh: '卫星排布', en: 'Satellite Layout' },
  '#pvsyst': { zh: '全年仿真', en: '8760h Physics' },
  '#oblique': { zh: '实景透视', en: 'Oblique Studio' },
  '#cad': { zh: '施工图集', en: '16-Sheet CAD' },
  '#lab': { zh: '方案与光储比选', en: 'Scheme & BESS' },
  '#park': { zh: '园区', en: 'Campus' },
  '#records': { zh: '设计记录', en: 'Records' },
};

// ============================================================================
// 1.ZH -> EN Comprehensive Full-App Phrase Dictionary (Longest-First)
// ============================================================================
const ZH_TO_EN_PHRASES_RAW = [
  // Core Satellite Workbench & Preserved Test Assertions
  ['卫星地图 AI 光伏设计工作台', 'Satellite AI PV Design Workbench'],
  ['卫星地图智能光伏设计工作台', 'Satellite AI PV Design Workbench'],
  ['全国真实卫星影像定位 · 当地实时气象与最优倾角评估 · 双坡与禁布区排布 · MPPT配串 · 实景四点透视 · 全套16张施工CAD图纸导出', 'National Satellite Imagery · Live Weather & Optimal Tilt · Gable & Keep-Out Layout · MPPT Stringing · 4-Point Oblique Studio · 16-Sheet CAD Export'],
  ['智能光伏深化设计系统', 'Intelligent PV Engineering Suite'],
  ['基于 Agnes Harness', 'Intelligent PV Engineering Suite'],
  ['正在连接智能引擎', 'Connecting to Engine'],
  ['正在连接 AGH…', 'Connecting to Engine...'],
  ['正在连接 AGH', 'Connecting to Engine'],
  ['AGH 已连接', 'AI Engine Connected'],
  ['等待 AGH 连接', 'Waiting for AI Engine'],
  ['在浏览器中打开 AGH', 'Open AI Session in Browser'],
  ['切换中英文界面', 'Switch Language'],
  ['切换为英文界面', 'Switch to English'],
  ['切换界面语言', 'Switch Language'],
  ['🌐 切换英文', '🌐 Chinese'],
  ['切换英文', 'Chinese'],
  ['方案与光储比选', 'Scheme & BESS'],
  ['前往方案比选与储能碳资产测算中心', 'Open Multi-Scheme & PV-BESS Comparison Center'],

  // 5 Workflow Steps & Streamlined Guided Workflow in Satellite Workbench
  ['真实卫星定位 · 实时气象寻优 · 智能配串 · 全套施工图', 'Live Satellite Imagery · Meteorological Tilt · Smart MPPT · 16-Sheet CAD'],
  ['1. 卫星底图与排布设计', '1. Satellite Base & Array Layout'],
  ['1. 选址与圈屋顶', '1. Site & Roof Outline'],
  ['2. 电气设计与MPPT配串', '2. Electrical & MPPT Stringing'],
  ['2. 电气配串', '2. Electrical Stringing'],
  ['3. 8760h 物理仿真与实时气象', '3. 8760h Physics & Live Weather'],
  ['3. 8760h 仿真', '3. 8760h Simulation'],
  ['4. 实景透视效果图', '4. Oblique Perspective Studio'],
  ['4. 实景透视', '4. Oblique Studio'],
  ['5. 图纸与光筑报告', '5. CAD & Guangzhu Report'],
  ['5. 施工 CAD 图纸生成', '5. 16-Sheet CAD Drawings'],
  ['图纸与光筑报告', 'CAD & Guangzhu Report'],
  ['选址与圈屋顶', 'Site & Roof Outline'],
  ['当前操作向导', 'Guided Workflow'],
  ['① 选址/从三维导入', '① Pick Site / Import 3D'],
  ['② 圈定屋顶与禁布区', '② Outline Roof & Keep-Outs'],
  ['③ 一键铺设/12维寻优', '③ Auto-Layout / 12D Opt'],
  ['④ 配串与导出光筑专业报告', '④ Stringing & Guangzhu Report'],
  ['选址/从三维导入', 'Pick Site / Import 3D'],
  ['圈定屋顶与禁布区', 'Outline Roof & Keep-Outs'],
  ['一键铺设/12维寻优', 'Auto-Layout / 12D Opt'],
  ['配串与导出光筑专业报告', 'Stringing & Guangzhu Report'],
  ['🔄 三维设计联动', '🔄 3D Design Sync'],
  ['三维设计联动', '3D Design Sync'],
  ['👁 预览专业报告', '👁 Preview Pro Report'],
  ['预览专业报告', 'Preview Pro Report'],
  ['✨ AI 一键智能设计 ▾', '✨ AI One-Click Design ▾'],
  ['✨ AI 一键智能设计', '✨ AI One-Click Design'],
  ['AI 一键智能设计', 'AI One-Click Design'],
  ['① 选址底图', '① Site & Map'],
  ['② 圈画屋面', '② Draw Roof'],
  ['③ 排布与寻优', '③ Layout & Opt'],
  ['选址底图', 'Site & Map'],
  ['圈画屋面', 'Draw Roof'],
  ['排布与寻优', 'Layout & Opt'],
  ['下一步 →', 'Next Step →'],
  ['① 搜索定位或从三维导入', '① Search Site or Import 3D'],
  ['② 在地图圈画厂房轮廓', '② Outline Roof on Satellite Map'],
  ['③ 点击「一键铺设」或「多维寻优」', '③ Click "Auto-Layout" or "Multi-Factor Opt"'],
  ['快速上手向导', 'Quick-Start Guide'],
  ['新手三步快速出图', '3-Step Quick-Start Workflow'],
  ['卫星排布', 'Satellite Layout'],
  ['电气配串', 'Electrical MPPT'],
  ['8760h 仿真', '8760h Physics'],
  ['实景透视', 'Oblique Studio'],
  ['施工图纸', '16-Sheet CAD'],
  ['工程与选址 ▾', 'Project & Site ▾'],
  ['工程与选址', 'Project & Site'],
  ['坐标与图源', 'Coords & Map'],
  ['高德混合', 'Gaode Hybrid'],
  ['纯卫星', 'Clean Sat'],
  ['度分秒切换', 'DMS Mode'],
  ['全屏地图', 'Fullscreen'],
  ['更多工具 ▾', 'More Tools ▾'],
  ['更多工具', 'More Tools'],
  ['底图比例尺与方向微调', 'Scale & Axis Calibration'],
  ['自动校准比例/方向', 'Auto Scale & Axis'],
  ['手拉比例尺', 'Drag Scale'],
  ['手拉主墙方向', 'Drag Axis'],
  ['组件排布参数', 'Array Layout Parameters'],
  ['当地气象与最优夹角速览', 'Live Weather & Optimal Tilt'],
  ['点击展开 8 组候选倾角对比表', 'Click to expand 8-candidate tilt comparison'],
  ['单瓦最优', 'Max Specific'],
  ['总发电最优', 'Max Total'],
  ['冬至9-15时无遮挡排距', 'Winter 9-15h Unshaded Pitch'],
  ['前往施工图纸生成', 'Open 16-Sheet CAD Studio'],
  ['前往图纸生成工具', 'Open CAD Studio'],
  ['载入标准厂房样板', 'Load Standard Roof Sample'],
  ['离线回退示例', 'Offline Sample Fallback'],
  ['预设基准轮廓', 'Preset Geometry Outline'],
  ['非实景图像识别', 'Non-Vision Preset Sample'],
  ['非卫星影像视觉识别', 'Non-Satellite Vision Preset'],
  ['电压偏低', 'Low Voltage'],
  ['电压超限', 'Over Voltage'],
  ['电流偏高', 'High Current'],
  ['无法收回', 'Unrecoverable'],
  ['未回收', 'Unrecovered'],
  ['未配置储能系统', 'No BESS Configured'],
  ['纯光伏并网方案', 'Pure Grid-Tied PV Scheme'],
  ['参数与清册导入导出 ▾', 'Specs & BOM I/O ▾'],
  ['参数与清册导入导出', 'Specs & BOM I/O'],
  ['逆变器选型库与筛选', 'Inverter Catalog & Filters'],
  ['点击折叠/展开机型库', 'Click to toggle inverter catalog'],
  ['当前已选：', 'Selected: '],
  ['功率段：', 'Power Tier:'],
  ['品牌：', 'Brand:'],
  ['出图计时', 'Timer'],
  ['卷帘对比中', 'Split Compare'],
  ['辅助与汇报 ▾', 'Tools & Report ▾'],
  ['辅助与汇报', 'Tools & Report'],
  ['重置计时', 'Reset Timer'],
  ['1. 屋面建模与校准', '1. Roof Modeling & Calib'],
  ['2. 屋面布局与微调', '2. Array Layout & Tuning'],
  ['3. 屋面与经济信息', '3. Roof & Economic Info'],
  ['功率：', 'Power: '],
  ['尺寸：', 'Size: '],
  ['展开批量设备、电价与电缆细项设置 (8项)', 'Expand Batch Equipment, Tariff & Cable Options (8 Items)'],
  ['按需微调', 'Optional Tuning'],
  ['已加载前景女儿墙视线遮挡区域：前景墙体已自然遮挡底层光伏组件下沿。', 'Loaded foreground parapet sightline mask: lower PV module edges naturally occluded by parapet wall.'],
  ['已开启屋面全景 3D 倾斜阵列与冬至日阴影实时模拟视图。', 'Activated panoramic 3D tilted PV array & live winter-solstice shadow simulation.'],
  ['已切回卫星正射二维平面排布视图。', 'Returned to 2D orthophoto satellite layout view.'],
  ['已同步三维近场阴影损耗至 8760h 物理仿真工作台。', 'Synced 3D near-shading loss to 8760h physics workbench.'],
  ['1. 实景照片与场景模板', '1. Drone Photo & Scene Presets'],
  ['4套实景', '4 Presets'],
  ['场景1：双坡女儿墙', 'Scene 1: Gable + Parapet'],
  ['场景2：大跨度车间', 'Scene 2: Large Workshop'],
  ['场景3：混凝屋面', 'Scene 3: Flat Concrete'],
  ['场景4：卫星融合', 'Scene 4: Live Satellite'],
  ['依次点选四角', 'Pick 4 Corners'],
  ['自动配准四角', 'Auto-Match 4 Corners'],
  ['3. 冬至阴影与女儿墙视线遮挡区域', '3. Winter Shadow & Parapet Sightline Zone'],
  ['启用前景女儿墙裁剪', 'Enable Front Parapet Clipping'],
  ['4. 组件材质、组串分色与卷帘设置', '4. Module Finish, String Color & Split'],
  ['叠加组串分色映射', 'Overlay String Color Map'],
  ['启用改造前后实景卷帘分屏对比', 'Enable Before/After Split Comparison'],
  ['← 返回排布', '← Back to Layout'],
  ['图纸总览 (16)', 'Drawings (16)'],
  ['图签参数', 'Title Block'],
  ['支架与荷载', 'Racking & Loads'],
  ['快捷模块与报告 ▾', 'Modules & Reports ▾'],
  ['快捷模块与报告', 'Modules & Reports'],
  ['更多导出 ▾', 'More Exports ▾'],
  ['更多导出', 'More Exports'],
  ['导出全部 16 张总图 (.dxf)', 'Export Master 16-Sheet (.dxf)'],
  ['导出当前 DXF', 'Export Current DXF'],
  ['一键生成十六合一施工图集 (.pdf)', 'Export 16-in-1 CAD Book (.pdf)'],
  ['工程图纸目录', 'Drawing Directory'],
  ['全部 (16)', 'All (16)'],
  ['电气 (7)', 'Elec (7)'],
  ['结构 (4)', 'Struct (4)'],
  ['实景光储 (5)', 'Sim/BESS (5)'],
  ['综合 (5)', 'Sim (5)'],
  ['工程图签信息 (8项)', 'Title Block Info (8 Fields)'],
  ['图纸工程名称', 'Drawing Project Title'],
  ['设计单位', 'Design Institute'],
  ['建设/业主单位', 'Owner / Client'],
  ['总负责 / 审核', 'Chief Engineer'],
  ['设计 / 校核', 'Designer / Checker'],
  ['图号前缀', 'Sheet Prefix'],
  ['出图比例', 'Drawing Scale'],
  ['支架参数与风雪荷载校核', 'Racking & GB 55001 Wind/Snow Check'],
  ['✓ 合规', '✓ Pass'],
  ['⚠ 复核', '⚠ Check'],
  ['最低点高 H1(mm)', 'Front Clearance H1 (mm)'],
  ['前后排距 Y0(mm)', 'Row Pitch Y0 (mm)'],
  ['立柱南北距 Y1(mm)', 'Post Span N-S Y1 (mm)'],
  ['支架倾角 A(°)', 'Tilt Angle A (°)'],
  ['端部悬挑 X1(mm)', 'Cantilever X1 (mm)'],
  ['立柱东西距 X2(mm)', 'Post Span E-W X2 (mm)'],
  ['基础形式', 'Foundation Type'],
  ['C25 混凝土配重方墩', 'C25 Concrete Ballast Pier'],
  ['C30 防腐条形基础', 'C30 Strip Foundation'],
  ['彩钢瓦专用铝合金夹具', 'Standing-Seam Al Clamp'],
  ['海岸一类区', 'Cat A Coastal'],
  ['工业园二类区', 'Cat B Industrial'],
  ['城区三类区', 'Cat C Urban'],
  ['中心四类区', 'Cat D Metro'],
  ['允许恒载限值 (kN/m²)', 'Dead-Load Limit (kN/m²)'],
  ['✓ 抗风揭与屋面恒载通过', '✓ Wind-Uplift & Dead-Load Pass'],
  ['⚠ 恒载超限需加固复核', '⚠ Exceeds Reserve — Reinforce'],
  ['支架参数化实时大样预览', 'Parametric Bracket Section Preview'],
  ['返回单张图纸 →', 'Back to Sheet →'],
  ['01 排布图', '01 Layout'],
  ['02 组串图', '02 String'],
  ['03 防雷图', '03 Ground'],
  ['04 支架图', '04 Racking'],
  ['05 一次图', '05 SLD'],
  ['06 桥架图', '06 Tray'],
  ['07 基础图', '07 Ballast'],
  ['08 目录清册', '08 BOM'],
  ['09 实景透视', '09 Oblique'],
  ['10 物理仿真', '10 Physics'],
  ['11 节点大样', '11 Clamp'],
  ['12 并网二次', '12 SCADA'],
  ['13 运维水路', '13 Walkway'],
  ['14 光储系统', '14 BESS'],
  ['15 实景对比', '15 Proposal'],
  ['16 阴影财务', '16 Shading'],
  ['单张视图', 'Single'],
  ['双列总览', '2×2 Grid'],
  ['连排全览', 'Stacked'],
  ['白底打印', 'Light Print'],
  ['深色蓝图', 'Blueprint'],
  ['屋面承重（待核定）', 'Structural Load Limit (Pending)'],
  ['默认参考，可改', 'Editable Defaults'],
  ['载入武进工业园区', 'Load Wujin Industrial Park'],
  ['限电上限（默认10）', 'Curtailment Cap (Default 10)'],
  ['逆变器占比（默认80）', 'Inverter Share (Default 80)'],
  ['养殖场风机', 'Livestock Farm Roof'],
  ['当地实时官方气象驱动的倾角设计', 'Live Official Weather-Driven Tilt Optimization'],
  ['参照下方实时 2D 排布缩略图角点顺序', 'Match corner order with the live 2D layout thumbnail below'],
  ['请调整至清晰位置，作为卫星设计底图', 'Pan and zoom to a clear roof view as the satellite base map'],
  ['确认电气设计并映射屋面组串', 'Confirm Electrical Design & Map Roof Strings'],
  ['IEC 62548 电压温度包络校核', 'IEC 62548 Voltage-Temperature Envelope Check'],
  ['IEC 62548 气候区电压包络校核', 'IEC 62548 Climate-Zone Voltage Envelope Check'],
  ['IEC 62548 合规通过', 'IEC 62548 Compliant'],
  ['请调整串联数', 'Adjust Modules/String'],
  ['✓ 极寒/酷暑电压包络合规', '✓ Extreme Cold/Hot Voltage Envelope Compliant'],
  ['⚠ 超出安全串联窗口', '⚠ Outside Safe Stringing Window'],
  ['GB 50797 交直流电缆压降校核', 'GB 50797 AC/DC Cable Voltage Drop Check'],
  ['GB 50797 实测回路电缆压降', 'GB 50797 Routed Loop Cable Voltage Drop'],
  ['支持标准设备参数文件导入导出', 'Supports Standard Equipment File (.PAN/.OND) Import/Export'],
  ['南北坡异向组串严格物理隔离', 'Strict South/North Slope String & MPPT Isolation'],
  ['逐串实测线损压降', 'Per-String Routed Cable Voltage Drop'],
  ['导入组件参数文件', 'Import Module (.PAN)'],
  ['导出组件参数文件', 'Export Module (.PAN)'],
  ['导入逆变器参数文件', 'Import Inverter (.OND)'],
  ['导出逆变器参数文件', 'Export Inverter (.OND)'],
  ['导出 MPPT 与线缆清册 (.csv)', 'Export MPPT & Cable Schedule (.csv)'],
  ['当前逆变器与交直流线缆配置', 'Selected Inverter & DC/AC Cable Sizing'],
  ['直流 4mm²', 'DC 4mm²'],
  ['直流 6mm²', 'DC 6mm²'],
  ['交流铜芯缆', 'AC Copper Cable'],
  ['交流铝合金缆', 'AC Al-Alloy Cable'],
  ['采用最佳', 'Apply Optimal'],
  ['允许窗口', 'Safe Window'],
  ['坡面朝向', 'Slope Aspect'],
  ['南坡 180°', 'South Slope 180°'],
  ['北坡 0°', 'North Slope 0°'],
  ['双坡异向子阵独立物理仿真明细', 'Dual-Slope Sub-Array Independent 8760h Breakdown'],
  ['严寒地区', 'Severe Cold Zone'],
  ['寒冷地区', 'Cold Climate Zone'],
  ['夏热冬冷地区', 'Hot-Summer Cold-Winter Zone'],
  ['夏热冬暖地区', 'Hot-Summer Warm-Winter Zone'],
  ['高原西北干寒区', 'Plateau & Northwest Zone'],
  ['严寒气候区', 'Severe Cold Zone'],
  ['寒冷气候区', 'Cold Climate Zone'],
  ['夏热冬冷区', 'Hot-Summer Cold-Winter Zone'],
  ['夏热冬暖区', 'Hot-Summer Warm-Winter Zone'],
  ['温和气候区', 'Temperate Zone'],
  ['系统设备参数文件与组串电压-温度包络校核', 'Equipment Specs (.PAN/.OND) & Voltage-Temperature Envelope'],
  ['系统设备参数文件与组串电压温度包络校核', 'Equipment Specs (.PAN/.OND) & Voltage-Temperature Envelope'],
  ['组件参数：', 'Module Spec: '],
  ['逆变器参数：', 'Inverter Spec: '],
  ['企业生产班制耦合模型', 'C&I Shift-Load Self-Use Coupling'],
  ['单班制 (8:00-17:00 周末双休)', 'Single Shift (08:00-17:00, 5d/wk)'],
  ['两班制 (7:00-23:00 六天生产)', 'Double Shift (07:00-23:00, 6d/wk)'],
  ['三班连续生产 (24小时连续负荷)', 'Continuous 3-Shift (24/7 Base Load)'],
  ['手动自定义自发自用比例', 'Manual Self-Consumption Ratio'],
  ['财务折现率 (%)', 'Discount Rate (%)'],
  ['度电成本 (LCOE)', 'Levelized Cost (LCOE)'],
  ['静态 / 动态回收期', 'Static / Dynamic Payback'],
  ['4. 建筑风雪荷载与屋面分区校核', '4. GB 55001 Wind/Snow & Roof Zone Check'],
  ['建筑檐高 (米)', 'Eave Height (m)'],
  ['地面粗糙度类别', 'Terrain Roughness'],
  ['海岸海岛一类区', 'Cat A (Coastal / Open Sea)'],
  ['工业园区二类区', 'Cat B (Suburban / Industrial Park)'],
  ['密集城区三类区', 'Cat C (Dense Urban)'],
  ['高楼中心四类区', 'Cat D (High-Rise Metro Core)'],
  ['屋面允许新增恒载限值 (kN/m²)', 'Allowable Roof Dead-Load Reserve (kN/m²)'],
  ['50年重现期风压', '50-Yr Basic Wind w0'],
  ['风高系数', 'Height Factor μz'],
  ['平屋面抗倾覆配重：中心区', 'Flat-Roof Ballast: Interior'],
  ['彩钢瓦免穿孔夹具：中心区', 'Standing-Seam Clamps: Interior'],
  ['角部风吸区加密', 'Corner Zone Reinforced'],
  ['角部风吸区', 'Corner Suction Zone'],
  ['单夹拉力', 'Max Clamp Tension'],
  ['✓ 分区抗风揭与屋面恒载校核通过', '✓ Zonal Wind-Uplift & Dead-Load Check Passed'],
  ['⚠ 超出屋面恒载限值，须结构加固复核', '⚠ Exceeds Roof Reserve — Structural Reinforcement Needed'],
  ['本荷载与抗风揭计算为前期方案级包络校核，正式施工图出图前须结合原厂房结构竣工蓝图由注册结构工程师复核签章', 'Preliminary envelope verification; final construction issue requires licensed structural PE review against as-built drawings'],
  ['导出 CAD (.dxf)、清册与蓝图 (.pdf)', 'Export CAD (.dxf), BOM (.csv) & Blueprint (.pdf)'],
  ['导出全部 16 张施工图总图 (.dxf)', 'Export Master 4×4 16-Sheet CAD (.dxf)'],
  ['导出工程材料清册 (.csv)', 'Export Engineering BOM Schedule (.csv)'],
  ['并网电压等级与一次接入方案', 'Grid Voltage Level & Primary Connection'],
  ['10kV 高压升压并网 (配箱变)', '10kV MV Step-Up Grid Connection (with Transformer)'],
  ['0.4kV 低压母线并网 (配并网柜)', '0.4kV LV Busbar Grid Connection (with Tie Cabinet)'],
  ['厂区变压器容量与消纳校核', 'Plant Transformer Capacity & Hosting Check'],
  ['满足国网分布式电源接入规范', 'Complies with Utility DER Interconnection Code'],
  ['防逆流保护与并网联跳装置', 'Anti-Backflow Relay & Grid Inter-Trip'],
  ['✓ 已配防逆流微机保护 + 失压脱扣', '✓ Equipped with Anti-Backflow Relay + Under-Voltage Trip'],
  ['关口表双向计量 · 逆功率 100ms 毫秒级降载 + 检有压自动合闸', 'Bi-directional metering · 100ms reverse-power curtailment + auto-reclose'],
  ['动态无功补偿与电能质量校核', 'Dynamic Reactive Power (SVG) & Power Quality'],
  ['谐波畸变率 THDi ≤ 2.8% (优于 GB/T 14549 5% 标准)', 'Harmonic THDi ≤ 2.8% (exceeds GB/T 14549 5% limit)'],

  // Step 4 Real-Scene Studio
  ['实景透视工程校核与业主汇报工作台 — 四点透视配准与女儿墙遮挡实测', 'Oblique Perspective Verification & Owner Proposal Workbench — 4-Point Homography & Parapet Check'],
  ['生成业主实景汇报书', 'Export Owner Proposal'],
  ['导出高清效果图', 'Export HD Rendering'],
  ['✓ 9:00-15:00 核心时段无遮挡', '✓ Unshaded During 09:00-15:00 Core Window'],
  ['⚠ 早晚低高度角局部斜影', '⚠ Partial Low-Sun Oblique Shadow'],
  ['② 园区道路人眼平视美观度校核', '2. Street-Level Aesthetics & Sightline Check'],
  ['✓ 前景女儿墙遮蔽底层支架 72%', '✓ Front Parapet Conceals 72% of Sub-Structure'],
  ['地面 1.6米视线无外露桥架与杂乱线缆，适合业主投决汇报', 'Clean street-level view at 1.6m eye height; ideal for executive sign-off'],
  ['③ 周边办公楼与道路防眩光校核', '3. Anti-Glare Safety Check for Nearby Buildings & Roads'],
  ['✓ 减反镀膜反射率 3.6% ≤ 5.0%', '✓ AR-Coated Glass Reflectance 3.6% ≤ 5.0%'],
  ['压花高透钢化玻璃漫反射设计，无光污染风险（合格）', 'Textured tempered AR glass diffuse reflection; zero glare hazard (Pass)'],
  ['④ 屋面实景投射规模与荷载校核', '4. Projected Array Capacity & Structural Dead-Load Check'],
  ['新增屋面均布恒载 0.14 千牛/平方米 ≤ 0.70 限值（安全）', 'Added dead load 0.14 kN/m² ≤ 0.70 kN/m² structural limit (Safe)'],
  ['1. 导入现场航拍照片或切换实景屋面场景', '1. Upload Drone Photo or Select Oblique Roof Scene'],
  ['上传无人机 / 手机斜拍厂房照片', 'Upload Drone / Mobile Oblique Roof Photo'],
  ['或切换内置三维航拍厂房实景模板：', 'Or select built-in oblique aerial factory template:'],
  ['场景 1：双坡彩钢瓦厂房 + 前景女儿墙实景', 'Scene 1: Gable Metal Workshop + Front Parapet'],
  ['场景 2：大跨度工业车间 45° 航拍实景', 'Scene 2: Large-Span Workshop 45° Drone View'],
  ['场景 3：混凝土女儿墙平屋面航拍实景', 'Scene 3: Flat Concrete Roof with Parapet'],
  ['场景 4：当前卫星底图三维斜视融合合成 (实时联动)', 'Scene 4: Live Satellite Base 3D Oblique Synthesis'],
  ['2. 四点透视配准与屋面贴合', '2. 4-Point Homography Registration'],
  ['依次点选四角 (1~4)', 'Pick 4 Corners (1~4)'],
  ['自动配准屋面四角', 'Auto-Match 4 Roof Corners'],
  ['3. 冬至日逐时阴影与女儿墙视线遮挡区域', '3. Winter Solstice Hourly Shadow & Parapet Sightline Zone'],
  ['补画女儿墙视线遮挡区域', 'Draw Parapet Sightline Occlusion'],
  ['加载默认女儿墙遮挡', 'Load Default Parapet Mask'],
  ['清除遮挡', 'Clear Mask'],
  ['启用前景女儿墙视线遮挡裁剪', 'Enable Front Parapet Sightline Clipping'],
  ['4. 组件材质、组串分色与改造前后卷帘对比', '4. Module Finish, String Color & Split Comparison'],
  ['组件外观样式', 'Module Visual Style'],
  ['单晶深蓝高透组件', 'Monocrystalline Deep-Blue'],
  ['全黑美学组件', 'All-Black Aesthetic Module'],
  ['多晶宝蓝标准组件', 'Polycrystalline Royal-Blue'],
  ['组件不透明度', 'Module Opacity'],
  ['边框栅线清晰度', 'Frame & Cell Grid Sharpness'],
  ['表面反光强度', 'Surface Specular Glare'],
  ['启用「改造前原貌 vs 改造后光伏」实景卷帘分屏对比', 'Enable Before / After Split-Screen Slider Comparison'],
  ['卷帘分界位置', 'Split Slider Position'],
  ['⇄ 开启改造前后卷帘对比', '⇄ Before / After Split Compare'],
  ['改造前屋面原貌', 'Before PV Retrofit'],
  ['改造后光伏', 'After PV Retrofit'],
  ['实景出图计时', 'Render Timer'],
  ['启动计时', 'Start Timer'],
  ['暂停计时', 'Pause Timer'],
  ['重置', 'Reset'],

  // 16 CAD Sheets & Modals
  ['25 年全生命周期财务指标', '25-Year Lifecycle Financial Metrics'],
  ['输入用电信息与光储经济参数', 'Load Profile & PV+BESS Financial Parameters'],
  ['逆变器选型方式与容配比', 'Inverter Sizing Mode & DC/AC Ratio'],
  ['新建 / 导入光伏工程方案', 'New / Import PV Engineering Project'],
  ['1. 屋面建模与底图校准', '1. Roof Modeling & Base Map Calibration'],
  ['2. 屋面布局与阵列微调', '2. Roof Array Layout & Fine-Tuning'],
  ['3. 屋面与光储经济信息', '3. Roof Summary & PV-BESS Economics'],
  ['混凝土支架侧面示意图', 'Concrete Ballast Bracket Side Elevation'],
  ['混凝土支架正面示意图', 'Concrete Ballast Bracket Front Elevation'],
  ['女儿墙视线遮挡区域', 'Parapet Sightline Occlusion Zone'],
  ['支架侧视图预览', 'Bracket Side Elevation Preview'],
  ['支架正视图预览', 'Bracket Front Elevation Preview'],
  ['1. 光伏排布图', '1. PV Array Layout Plan'],
  ['2. 组串接线图', '2. String Wiring & Inverter Plan'],
  ['3. 防雷接地图', '3. Lightning & Grounding Plan'],
  ['4. 支架剖面与立面图', '4. Racking Section & Elevation'],
  ['5. 电气一次系统图', '5. Electrical Single-Line Diagram'],
  ['6. 电缆桥架与走向图', '6. DC/AC Cable Tray Routing Plan'],
  ['7. 基础配重与荷载图', '7. Ballast Foundation & Load Plan'],
  ['8. 图纸目录与设备材料表', '8. Drawing Index & BOM Schedule'],
  ['9. 实景四点透视与女儿墙遮挡图', '9. Oblique Perspective & Parapet Sheet'],
  ['10. 全年物理仿真系统与电压包络图', '10. 8760h Simulation & Voltage Envelope'],
  ['11. 夹具压块与屋面防水节点大样图', '11. Clamp & Waterproofing Details'],
  ['12. 并网柜二次原理与通讯监控图', '12. Grid Cabinet SCADA Schematic'],
  ['13. 检修马道、消防通道与清洗水路图', '13. O&M Walkway, Fire Lane & Water Loop'],
  ['14. 光储一体化与削峰填谷系统图', '14. PV+BESS Peak-Shaving System Sheet'],
  ['15. 屋面改造前后实景对比与业主汇报图', '15. Before/After Executive Presentation'],
  ['16. 三维近场阴影、寻优矩阵与财务图', '16. 3D Shading, Tilt Matrix & IRR Sheet'],
  ['电气施工图', 'Electrical CAD'],
  ['结构施工图', 'Structural CAD'],
  ['目录与清册', 'Index & BOM'],
  ['实景透视图', 'Oblique Sheet'],
  ['物理仿真图', 'Physics Sheet'],
  ['光储系统图', 'PV+BESS Sheet'],
  ['业主汇报图', 'Owner Sheet'],
  ['投决报告图', 'Financial Sheet'],
  ['全部图纸', 'All Drawings'],
  ['← 返回设计', '← Back to Design'],

  // Satellite Workbench Controls
  ['用电与经济参数', 'Tariff & Economics'],
  ['新建/导入工程', 'New / Import Project'],
  ['保存至工程库', 'Save to Project Library'],
  ['MPPT 组串分配', 'MPPT String Allocation'],
  ['一键铺设组件', 'Auto-Layout PV Array'],
  ['3. 一键铺设', '3. Auto-Layout PV Array'],
  ['一键铺设', 'Auto-Layout PV Array'],
  ['自动生成直流线缆', 'Auto-Route DC Cables'],
  ['完成禁布区闭合', 'Close Keep-Out Polygon'],
  ['完成屋顶闭合', 'Close Roof Polygon'],
  ['地图拾取经纬度', 'Pick Lat/Lon on Map'],
  ['四点透视配准', '4-Point Homography Registration'],
  ['官方实时气象与太阳辐照遥测站', 'Official Live Weather & Solar Irradiance Station'],
  ['官方实时气象源', 'Official Live Weather Source'],
  ['官方实时气象', 'Official Live Weather'],
  ['刷新实时天气', 'Refresh Live Weather'],
  ['最大工作电流', 'Max Operating Current'],
  ['最大短路电流', 'Max Short-Circuit Current'],
  ['请选择组串方式', 'Select Stringing Mode'],
  ['打开项目文件', 'Open Project File'],
  ['内部报告中心', 'Internal Engineering Report'],
  ['业主报告中心', 'Owner Executive Proposal'],
  ['储能 AI 模拟', 'PV+BESS AI Dispatch'],
  ['标定比例尺', 'Calibrate Scale'],
  ['确定方向', 'Align Axis'],
  ['自动识别比例尺/方向', 'Auto Scale & Axis'],
  ['高德高清卫星混合底图 (含路网企业标注)', 'HD Hybrid Satellite Map (with Roads & Labels)'],
  ['全球高清纯卫星无标注底图', 'Global Clean Satellite Imagery (Unlabeled)'],
  ['全国任意位置 / 请选择省市区', 'Nationwide / Quick Select Region'],
  ['输入全国任意企业名称、工厂、工业园、街道或省市区（如：宁德时代、隆基绿能、比亚迪、淄博起凤镇）', 'Enter enterprise, industrial park, street, or city name, or lat,lon coordinates'],
  ['省市区选址', 'Region Quick Pick'],
  ['全国位置/企业搜索', 'Location / Enterprise Search'],
  ['搜索位置', 'Search'],
  ['经度 (°E)', 'Lon (°E)'],
  ['纬度 (°N)', 'Lat (°N)'],
  ['度分秒', 'DMS'],
  ['经纬度定位', 'Locate'],
  ['切换地图图源', 'Map Source'],
  ['全屏放大地图', 'Fullscreen Map'],
  ['退出全屏', 'Exit Fullscreen'],
  ['AI 设计要求：', 'AI Design Prompt:'],
  ['倾角寻优策略', 'Tilt Strategy'],
  ['按气象单瓦最优倾角', 'Max Specific Yield Tilt'],
  ['按屋面总发电量最优倾角', 'Max Roof Total Yield Tilt'],
  ['顺彩钢瓦屋面坡度平铺', 'Flush Metal-Roof Pitch'],
  ['保持当前手动设定角度', 'Manual Custom Tilt'],
  ['地图选址', 'Map Pick'],
  ['AI 识别当前屋面', 'AI Detect Roof'],
  ['AI 按要求一键设计', 'AI One-Click Autopilot'],
  ['组件排布数量', 'PV Module Count'],
  ['直流装机容量', 'DC Installed Capacity'],
  ['逆变器与交流容量', 'Inverter & AC Capacity'],
  ['首年 P50 并网发电量', 'First-Year P50 Grid Yield'],
  ['组串与 MPPT 校核', 'String & MPPT Check'],
  ['工程投资与静态回收期', 'CAPEX & Simple Payback'],
  ['状态：正常', 'Status: OK'],
  ['预计回收期', 'Est. Payback'],
  ['满发小时', 'Specific Yield'],
  ['系统效率', 'System PR'],
  ['快速组串', 'Auto Stringing'],
  ['DIY 组串', 'Manual DIY Stringing'],
  ['双坡屋面', 'Gable Roof'],
  ['单坡屋面', 'Mono-Slope Roof'],
  ['斜屋顶(单坡)', 'Mono-Slope Roof'],
  ['混凝土平屋面', 'Flat Concrete Roof'],
  ['混凝土平屋顶', 'Flat Concrete Roof'],
  ['平屋顶', 'Flat Roof'],
  ['1. 屋面', '1. Roof'],
  ['2. 布局', '2. Layout'],
  ['3. 信息', '3. Info'],
  ['1. 组件排布', '1. Array Layout'],
  ['2. 电气配置', '2. Electrical'],
  ['组件信息与排布设置', 'Module & Array Parameters'],
  ['电气配置与逆变器清单', 'Electrical & Inverter BOM'],
  ['选择组件型号', 'Select PV Module'],
  ['安装方向', 'Orientation'],
  ['竖向排布', 'Portrait'],
  ['横向排布', 'Landscape'],
  ['安装倾角 (°)', 'Tilt Angle (°)'],
  ['组件方位角 (°)', 'Azimuth (°)'],
  ['阵列行数 × 列数 (个)', 'Sub-array Rows × Cols'],
  ['走道宽度 (m)', 'Walkway Width (m)'],
  ['子阵间距 / 前后排距 (m)', 'Row Pitch / Gap (m)'],
  ['东西列间距 (m)', 'Column Gap (m)'],
  ['屋面边缘退距 (m)', 'Edge Setback (m)'],
  ['禁布区退距 (m)', 'Keep-Out Setback (m)'],
  ['目标容量上限 (kWp)', 'Target Capacity Cap (kWp)'],
  ['0. 漫游平移卫星图', '0. Pan / Zoom Satellite Map'],
  ['1. 标定比例尺', '1. Calibrate Scale'],
  ['2. 确定方向 (沿屋脊/外墙拉线)', '2. Align Building Axis'],
  ['3. 绘制屋顶 (矩形框选)', '3. Draw Rectangular Roof'],
  ['3B. 多点画屋面 (异形/U形/L形)', '3B. Draw Polygon Roof'],
  ['4. 多点画禁布区 (异形/斜向障碍物)', '4. Draw Polygon Keep-Out'],
  ['4B. 绘制禁布区 (多点或拉框)', '4B. Draw Keep-Out Box'],
  ['5. 删除选中禁布区', '5. Delete Selected Keep-Out'],
  ['漫游平移', 'Pan Map'],
  ['1. 绘制屋顶', '1. Draw Roof'],
  ['多点画屋顶', 'Polygon Roof'],
  ['2. 绘制禁布区', '2. Keep-Out Box'],
  ['多点画禁布区', 'Polygon Keep-Out'],
  ['删除禁布区', 'Delete Keep-Out'],
  ['阴影分析', 'Shadow Check'],
  ['阴影模拟', 'Shadow Sim'],
  ['全景三维仿真', '3D Digital Twin'],
  ['开启三维数字孪生与光线追踪仿真', 'Launch 3D Digital Twin & Ray-Tracing Simulation'],
  ['开启三维全景仿真', 'Launch 3D Digital Twin'],
  ['同步三维遮挡损耗', 'Sync 3D Shading Loss'],
  ['同步遮挡损耗', 'Sync Shading Loss'],
  ['导出三维截图', 'Export 3D PNG'],
  ['返回二维底图', 'Back to 2D Map'],
  ['真实材质', 'PBR Realistic'],
  ['辐照热力', 'POA Heatmap'],
  ['二极管失配', 'Bypass Diode'],
  ['组串桥架', 'Strings & Trays'],
  ['抗风分区', 'Wind Zones'],
  ['冬至日', 'Winter Solstice'],
  ['春分日', 'Vernal Equinox'],
  ['夏至日', 'Summer Solstice'],
  ['冬至', 'Winter Solstice'],
  ['春分', 'Equinox'],
  ['夏至', 'Summer Solstice'],
  ['▶ 日照动画', '▶ Sun Sweep'],
  ['日照动画', 'Sun Sweep'],
  ['暂停日照', 'Pause Sun'],
  ['太阳时刻', 'Solar Hour'],
  ['三维轴测', '3D Isometric'],
  ['正南航拍', 'South Aerial'],
  ['屋面巡检', 'Walkway View'],
  ['人眼街景', 'Street View'],
  ['正顶俯视', 'Top Plan'],
  ['阵列均布辐照', 'Mean POA Irradiance'],
  ['瞬时几何遮挡', 'Beam Shade'],
  ['旁路二极管电损耗', 'Bypass-Diode Loss'],
  ['块触发', 'pcs triggered'],
  ['全年三维阴影损耗', 'Annual 3D Shading Loss'],
  ['冬至无遮挡率', 'Winter Unshaded Pass'],
  ['三维光线追踪线性遮挡', '3D Ray-Traced Linear Shade'],
  ['三维光线追踪遮挡', '3D Ray-Traced Shade'],
  ['真实园区 3D 全景数字孪生沙盘', '3D Campus Digital Twin Sandbox'],
  ['冬至日 (12-21)', 'Winter Solstice (12-21)'],
  ['春分日 (03-21)', 'Vernal Equinox (03-21)'],
  ['夏至日 (06-21)', 'Summer Solstice (06-21)'],
  ['🏛 鸟瞰', '🏛 Aerial'],
  ['⬇ 顶视', '⬇ Top'],
  ['☀ 南向', '☀ South'],
  ['🎨 分期着色', '🎨 Phase Color'],
  ['🎨 实景深蓝', '🎨 Deep Blue'],
  ['旁路二极管阴影电失配', 'Bypass-Diode Electrical Loss'],
  ['冬至早九至午三无遮挡率', 'Winter 09:00-15:00 Unshaded'],
  ['冬至晨间触发二极管组件', 'Winter AM Diode-Active Mods'],
  ['三维数字孪生与光线追踪控制栏', '3D Digital Twin & Ray-Tracing Toolbar'],
  ['3D真实数字孪生与光线追踪视图', '3D Physical Digital Twin & Ray-Tracing View'],
  ['将三维光线追踪全年遮挡与旁路二极管失配写入全年仿真', 'Write 3D ray-traced shading & diode loss to 8760h simulation'],
  ['导出高清三维数字孪生渲染截图', 'Export HD 3D Digital Twin Screenshot'],
  ['角部高压区 (加密抗风)', 'Corner High-Suction Zone (Reinforced)'],
  ['周边边缘区', 'Perimeter Edge Zone'],
  ['屋面内部标准区', 'Interior Standard Zone'],
  ['北坡子阵', 'North Slope Sub-Array'],
  ['南坡/主阵', 'South / Main Sub-Array'],
  ['✅ 三组旁路二极管全导通无遮挡', '✅ All 3 bypass-diode substrings unshaded'],
  ['⚠️ 已触发', '⚠️ Triggered'],
  ['组旁路二极管', 'bypass diodes'],
  ['组串归属', 'String ID'],
  ['待分配', 'Unassigned'],
  ['实时斜面辐照', 'Live POA'],
  ['几何遮挡率', 'Linear Shade'],
  ['全年阴影失配', 'Annual Shade Loss'],
  ['当前运行环境未启用硬件三维渲染上下文，三维物理阴影核算引擎仍可在后台正常计算。', 'Hardware WebGL context unavailable; 3D ray-traced shading solver remains active.'],
  ['清除重画', 'Clear Roof'],
  ['重新绘制', 'Redraw'],
  ['上传底图', 'Upload Map'],
  ['区域编辑 (微调顶点)', 'Edit Vertices'],
  ['绘制 (多点画屋顶)', 'Draw Polygon Roof'],
  ['矩形绘制', 'Draw Rectangle'],
  ['障碍物 (多点画禁布区)', 'Draw Keep-Out'],
  ['屋面坡度/分水线', 'Slope & Ridge'],
  ['下一步 (电气设计) →', 'Next (Electrical) →'],
  ['屋面结构与分界设置', 'Roof Structure & Ridge Split'],
  ['屋面坡度 (°)', 'Roof Pitch (°)'],
  ['女儿墙高 / 宽 (mm)', 'Parapet H / W (mm)'],
  ['山东省济南市历城区工业北路', 'Gongye North Rd, Licheng District, Jinan, Shandong'],
  ['山东省 / 济南市 / 历城区', 'Shandong / Jinan / Licheng'],
  ['山东省 / 淄博市 / 桓台县', 'Shandong / Zibo / Huantai'],
  ['山东省 / 济宁市 / 兖州区', 'Shandong / Jining / Yanzhou'],
  ['江苏省 / 泰州市 / 高新区', 'Jiangsu / Taizhou / High-Tech Zone'],
  ['广东省 / 佛山市 / 顺德区', 'Guangdong / Foshan / Shunde'],
  ['浙江省 / 嘉兴市 / 平湖市', 'Zhejiang / Jiaxing / Pinghu'],
  ['福建省 / 宁德市 / 蕉城区', 'Fujian / Ningde / Jiaocheng'],
  ['陕西省 / 西安市 / 经开区', 'Shaanxi / Xi\'an / Economic Dev Zone'],
  ['全国任意位置 / 请选择省市区', 'Nationwide / Select Province & City'],
  ['输入全国任意企业名称、工厂、工业园、街道或省市区（如：宁德时代、隆基绿能、比亚迪、淄博起凤镇）', 'Enter company, industrial park, street, or city (e.g., CATL, LONGi, BYD, Jinan)'],
  ['输入设计要求，例如：按当地实时气象最优倾角设计，目标装机 250kW，双坡屋面预留 0.8m 退距，自动避让采光带并完成 MPPT 配串', 'Enter AI design brief, e.g.: Optimal meteorological tilt, target 250 kWp, 0.8m setback, auto skylight keep-out & MPPT stringing'],
  ['工商业分布式光伏电站项目', 'C&I Distributed Rooftop PV Project'],
  ['当前工商业分布式光伏工程', 'Active C&I Rooftop PV Project'],
  ['正在连接智能引擎', 'Connecting Engine...'],
  ['正在连接引擎', 'Connecting Engine...'],
  ['引擎已就绪 · 智能深化设计', 'Engine Ready · Smart PV Design'],
  ['智能引擎已连接', 'Smart Engine Connected'],
  ['正在连接本机智能引擎', 'Connecting Local Engine...'],
  ['简体中文', 'Simplified Chinese'],
  ['英文界面', 'English'],

  // App-Wide Pages: #new (3D Design), #form, #result, #park, #records, #roof, #settings
  ['＋ 新建安装面（画图或导入图纸）', '+ Create New Roof Surface (Draw or Import CAD)'],
  ['运行本机规则设计（无需模型密钥）', 'Run Local Engineering Engine (No API Key Needed)'],
  ['运行本机规则设计', 'Run Local Engine'],
  ['下一步：填条件 →', 'Next: Configure Parameters →'],
  ['开始自动设计 →', 'Start Automated Design →'],
  ['进入对话 →', 'Enter Interactive Chat →'],
  ['一键模式', 'One-Click Autopilot'],
  ['填好条件，Agent 按步骤完成设计', 'Configure constraints; AI completes full engineering workflow'],
  ['分析、修改、对比、复核、申请导出', 'Simulate, refine, compare options, verify rules, and export'],
  ['做不到时停下给放宽建议 · 用时以执行记录为准', 'Reports infeasible constraints with relaxation advice & audit trail'],
  ['对话模式', 'Interactive Copilot'],
  ['在 AGH 中自由描述需求', 'Describe custom PV requirements in natural language'],
  ['使用同一套光筑工具与原生审批', 'Uses identical physics/CAD tools with approval gates'],
  ['由你决定下一步，过程自动留下记录', 'Step-by-step interactive control with full execution log'],
  ['我的屋顶', 'My Custom Roofs'],
  ['公开地图屋顶', 'Real Industrial Roofs'],
  ['演示', 'Benchmark Templates'],
  ['安装面', 'Roof Surfaces'],
  ['编辑这个屋顶', 'Edit Roof Geometry'],
  ['屋顶资料', 'Roof Profile'],
  ['屋顶面积', 'Roof Area'],
  ['外形尺寸', 'Dimensions'],
  ['屋面承重（结构核定）', 'Structural Load Limit (Verified)'],
  ['屋面承重（示意值）', 'Structural Load Limit (Reference)'],
  ['周边楼和树', 'Nearby Shading Objects'],
  ['案例输入与待核实项', 'Assumptions & Field Verification Checklist'],
  ['随屋顶资料', 'Built-in Survey'],
  ['我画的', 'Custom Drawn'],
  ['已选', 'Selected'],
  ['硬性要求', 'Hard Engineering Constraints'],
  ['空着表示不限', 'Leave blank if unconstrained'],
  ['回本不超过', 'Max Payback'],
  ['预算不超过', 'Max Budget'],
  ['并网容量不超过', 'Max Grid Capacity'],
  ['装机不少于', 'Min Capacity'],
  ['装机不超过', 'Max Capacity'],
  ['检修通道至少', 'Min O&M Walkway'],
  ['离障碍物至少', 'Obstacle Setback'],
  ['离屋面边缘至少', 'Edge Setback'],
  ['倾角下限', 'Min Tilt'],
  ['倾角上限', 'Max Tilt'],
  ['只自用，不上网', 'Zero Export (100% Self-Consumption Only)'],
  ['只用压载，不在屋面打孔', 'Ballasted Only (No Roof Penetration)'],
  ['不高出女儿墙', 'Module Peak Below Parapet Cap'],
  ['必须避开', 'Mandatory Keep-Outs'],
  ['补充说明', 'Additional Notes'],
  ['开工前问答', 'Pre-Construction Site Survey'],
  ['经济参数', 'Financial Parameters'],
  ['示意，可改', 'Editable Defaults'],
  ['自用电价', 'Self-Use Tariff'],
  ['自用比例', 'Self-Use Share'],
  ['余电上网', 'Feed-in Tariff'],
  ['设备与排布设置', 'Equipment & Layout Settings'],
  ['逆变器品牌', 'Inverter Brand'],
  ['逆变器型号', 'Inverter Model'],
  ['三维排版算法', '3D Layout Algorithm'],
  ['组串与走线算法', 'Stringing & Cable Routing'],
  ['直流光伏线型号', 'DC Solar Cable Type'],
  ['交流并网缆型号', 'AC Grid Cable Type'],
  ['运行设置', 'Execution Options'],
  ['最多修改轮数', 'Max Refinement Rounds'],
  ['三方案都满足时选', 'Preferred Objective'],
  ['三方案对比', '3-Scheme Comparison'],
  ['独立审核', 'Independent Audit'],
  ['结束时申请导出', 'Export CAD & BOM on Finish'],
  ['项目编号', 'Project ID'],
  ['任务书预览', 'Engineering Brief Preview'],
  ['将原样发给 Agent', 'Dispatched to Engine'],
  ['填写需求后自动生成', 'Generated automatically from parameters'],
  ['上一步', 'Back'],

  // Campus (#park) & Records (#records) & Result (#result)
  ['新建园区', 'New Campus'],
  ['选择园区', 'Select Campus'],
  ['载入泰州中国医药城产业园', 'Load Taizhou Medical High-Tech Campus'],
  ['载入武进示意园区', 'Load Wujin Industrial Park Demo'],
  ['已有设计汇总', 'Completed Building Summary'],
  ['新建园区，加入我的屋顶或演示屋顶。', 'Create a campus or load an industrial park template to batch-design multiple roofs.'],
  ['标准工商业园区配置', 'Standard C&I Campus Preset'],
  ['高收益满铺配置', 'Max-Capacity High-Yield Preset'],
  ['快回本稳健配置', 'Fast-Payback Conservative Preset'],
  ['轻质低荷载配置', 'Lightweight Low-Load Roof Preset'],
  ['园区汇总', 'Campus Portfolio Summary'],
  ['全部设计记录', 'All Engineering Records'],
  ['刷新记录', 'Refresh Records'],
  ['本版本计算摘要', 'Current Version Engineering Summary'],
  ['📄 打开方案书', '📄 Open Proposal'],
  ['几何与排布', '3D Geometry & Layout'],
  ['发电与电气', 'Yield & Electrical'],
  ['工程校核', 'Code Compliance'],
  ['经济与交付', 'Economics & Deliverables'],
  ['工程与经济明细', 'Engineering & Financial Breakdown'],
  ['点开查看计算过程和表格', 'Click sections below to inspect calculations & schedules'],
  ['规则指令与设备调整', 'Rule Copilot & Equipment Tuning'],
  ['每次修改保存新版本并重新计算', 'Each edit creates a new version and recalculates'],
  ['专业仿真与精算包络指标', 'Utility-Grade Simulation & Safety Envelopes'],
  ['8760h 专业能量平衡瀑布图与官方实时气象仿真', '8760h Energy Loss Waterfall & Official Live Weather'],
  ['企业厂区源荷匹配与并网接入深化校核', 'Plant Load Matching & Grid Interconnection Check'],
  ['组串压降清册与厂房结构防腐交底', 'String Voltage-Drop Schedule & Structural Anti-Corrosion'],
  ['本版本损耗指标', 'Current Version Loss Breakdown'],
  ['逐月发电与消纳', 'Monthly Generation & Self-Consumption'],
  ['本机工程自动化记录', 'Automated Engineering Execution Trace'],
  ['组串、逆变器与电缆', 'Strings, Inverters & Cable Schedules'],
  ['造价、电价与税费', 'CAPEX, Tariffs & Taxes'],
  ['三种投资方式', 'Business Models (Self-Invest / EMC / Roof Lease)'],
  ['版本链', 'Version Lineage'],
  ['为什么这样设计', 'Design Evolution Rationale'],

  // Settings Modal
  ['主题 / Theme', 'Appearance Theme'],
  ['界面语言 / Language', 'Interface Language'],
  ['外观主题', 'Appearance Theme'],
  ['界面语言', 'Interface Language'],
  ['浅色模式', 'Light'],
  ['深色模式', 'Dark'],
  ['跟随系统', 'System'],
  ['中文界面', 'Chinese'],
  ['英文界面', 'English'],
  ['接口与模型 Key（支持自定义接口 URL）', 'AI Provider & Custom Endpoint Key'],
  ['智能引擎通道与密钥设置', 'AI Engine Channel & Key Configuration'],
  ['服务商通道', 'Provider Channel'],
  ['自定义接口 URL（选填，留空用官方接口）', 'Custom Base URL (Optional)'],
  ['自定义接口地址（选填，留空使用默认通道）', 'Custom Endpoint URL (Optional)'],
  ['粘贴 API Key', 'Paste API Key'],
  ['粘贴接口密钥', 'Paste Access Key'],
  ['验证并保存', 'Verify & Save'],
  ['正在验证…', 'Verifying...'],
  ['设计模型', 'Design Model'],
  ['审核模型', 'Audit Model'],
  ['可用模型', 'Available Models'],
  ['尚未收到模型清单', 'Local physics engine active (no external model list loaded)'],
  ['设置', 'Settings'],
  ['关闭', 'Close'],

  // Satellite <-> 3D Bidirectional Linkage & Lab Cross-Tab Sync
  ['同步当前卫星/三维方案数据', 'Sync Active Satellite / 3D Scheme Data'],
  ['从卫星排布同步最新方案', 'Sync Latest Scheme from Satellite Layout'],
  ['一键同步卫星最新方案', 'Sync Latest Satellite Scheme'],
  ['从三维工程库导入方案', 'Import Scheme from 3D Project Library'],
  ['导入选中三维工程', 'Import Selected 3D Project'],
  ['刷新三维工程列表', 'Refresh 3D Project List'],
  ['卫星与三维双向联动', 'Satellite & 3D Bidirectional Linkage'],
  ['从三维设计导入屋面与方案', 'Import Roof & Scheme from 3D Design'],
  ['从三维设计导入', 'Import from 3D Design'],
  ['联动推送至三维设计', 'Push Layout to 3D Design'],
  ['同步至三维设计', 'Sync to 3D Design'],
  ['卫星深化方案 vs 三维设计基准', 'Satellite Refined Scheme vs. 3D Design Baseline'],
  ['进入三维设计成果场景', 'Open 3D Design Result Scene'],
  ['进入三维屋面编辑器', 'Open 3D Roof Editor'],
  ['在卫星排布中深化', 'Deepen in Satellite Layout'],
  ['三维设计', '3D Design'],
  ['尚未检测到已保存三维工程，默认同步卫星排布上下文', 'No saved 3D project detected; linked to active Satellite Layout context'],

  // Multi-Factor Engineering Optimization (Orientation, Mounting, Wind, Load, Cold Voc, Shadow Pruning)
  ['多维可能性因数综合寻优', 'Multi-Factor Engineering Optimization'],
  ['一键多维因数综合寻优', 'One-Click Multi-Factor Optimization'],
  ['多维工程因子联动校核', 'Multi-Factor Engineering Co-Verification'],
  ['东西向双坡蝴蝶阵', 'East-West Butterfly Array'],
  ['东西向人字坡蝴蝶阵', 'East-West Butterfly Array'],
  ['东西向双坡阵列', 'East-West Dual-Tilt Array'],
  ['东西双坡 (E-W)', 'East-West Butterfly'],
  ['正南固定倾角', 'South-Facing Fixed Tilt'],
  ['正南向固定倾角阵列', 'South-Facing Fixed-Tilt Array'],
  ['正南固定 (South)', 'South Fixed Tilt'],
  ['顺坡平铺', 'Flush Pitched Mounting'],
  ['顺彩钢瓦坡度平铺', 'Flush Metal-Roof Mounting'],
  ['架高阳光棚', 'Elevated Solar Canopy'],
  ['组件横竖排与叠排方式', 'Portrait/Landscape & 1P/2P Stacking'],
  ['1P 单排竖装', '1P Single-Row Portrait'],
  ['2P 双竖排叠装', '2P Dual-Row Portrait'],
  ['1P 单排', '1P Single-Row'],
  ['2P 双竖排', '2P Dual-Row'],
  ['横装抗遮挡', 'Landscape Shade-Tolerant'],
  ['竖装标准排布', 'Portrait Standard Layout'],
  ['竖装', 'Portrait'],
  ['横装', 'Landscape'],
  ['支架固定方式与屋面恒载校核', 'Mounting Attachment & Roof Dead-Load Check'],
  ['彩钢瓦免打孔夹具', 'Standing-Seam Non-Penetrating Clamp'],
  ['彩钢瓦夹具', 'Standing-Seam Clamp'],
  ['化学锚栓固定', 'Chemical Anchor Fixing'],
  ['混凝土压块配重', 'Concrete Ballast Mounting'],
  ['混凝土压块', 'Concrete Ballast'],
  ['屋面静荷载上限', 'Roof Dead-Load Limit'],
  ['屋面允许新增静荷载', 'Allowable Added Roof Dead Load'],
  ['屋面荷载安全汇总', 'Roof Dead-Load Safety Summary'],
  ['屋面恒载安全裕度', 'Roof Dead-Load Safety Margin'],
  ['屋面荷载合规', 'Roof Dead-Load Safe'],
  ['台风风区与边角抗风揭退距', 'Typhoon Wind Zone & Perimeter Uplift Setback'],
  ['台风风区等级', 'Typhoon Wind Zone'],
  ['沿海强台风区', 'Coastal Severe Typhoon Zone'],
  ['台风区边角风揭退距', 'Typhoon Perimeter Uplift Setback'],
  ['台风退距合规', 'Typhoon Setback Compliant'],
  ['极端低温开路电压校核', 'Extreme Cold Open-Circuit Voc Check'],
  ['低温开路电压校核', 'Cold Voc Envelope Check'],
  ['低温Voc安全', 'Cold Voc Safe'],
  ['障碍物阴影剔除', 'Obstacle Shadow Pruning'],
  ['阴影剔除块数', 'Shadow-Pruned Modules'],
  ['单组件阴影损失上限', 'Per-Module Shade Loss Cutoff'],
  ['地表反照率', 'Ground Albedo'],
  ['积雪遮蔽损失', 'Snow Loss'],
  ['光谱修正增益', 'Spectral Correction'],

  // Guangzhu Professional Report (《光筑专业报告》), Delivery Bundle, Health Check & Campus KPIs
  ['① 导出《光筑专业报告》PDF（6页计算书·含光筑水印）', '① Export Guangzhu Professional Report PDF (6-Page · Watermarked)'],
  ['导出《光筑专业报告》PDF（6页计算书·含光筑水印）', 'Export Guangzhu Professional Report PDF (6-Page · Watermarked)'],
  ['导出《光筑专业报告》PDF', 'Export Guangzhu Professional Report (PDF)'],
  ['📘 导出光筑专业报告 (PDF)', '📘 Export Guangzhu Professional Report (PDF)'],
  ['📄 导出光筑专业报告 (PDF)', '📄 Export Guangzhu Professional Report (PDF)'],
  ['导出光筑专业报告 (PDF)', 'Export Guangzhu Professional Report (PDF)'],
  ['导出光筑专业报告', 'Export Guangzhu Professional Report'],
  ['在线预览光筑专业报告', 'Preview Guangzhu Professional Report Online'],
  ['预览光筑专业报告', 'Preview Guangzhu Professional Report'],
  ['⬇ 导出并打开 PDF 报告', '⬇ Export & Open PDF Report'],
  ['导出并打开 PDF 报告', 'Export & Open PDF Report'],
  ['直接下载 (.pdf)', 'Direct Download (.pdf)'],
  ['《光筑专业报告》', 'Guangzhu Professional Report'],
  ['光筑专业报告', 'Guangzhu Professional Report'],
  ['并网光伏发电系统精细化工程仿真计算书', 'Guangzhu Professional Photovoltaic Simulation Report'],
  ['6页工程精细化仿真计算书 · 含光筑防伪水印', '6-Page Swiss Engineering Simulation Report · Guangzhu Watermark'],
  ['8760h 逐时精细化物理仿真', '8760h Hourly Physical Simulation'],
  ['8760h 精细化仿真', '8760h Precision Simulation'],
  ['光筑专业仿真', 'Guangzhu Precision Simulation'],
  ['光筑防伪水印', 'Guangzhu Watermark'],
  ['完成单栋或园区批量设计后可导出光筑专业报告', 'Complete single-building or batch campus design first to export Guangzhu Professional Report'],
  ['② 全套 CAD 施工图 (DXF/PDF)', '② Full 16-Sheet CAD Drawings (DXF/PDF)'],
  ['全套 CAD 施工图 (DXF/PDF)', 'Full 16-Sheet CAD Drawings (DXF/PDF)'],
  ['③ 一键导出全套工程交付包 & 同步三维设计', '③ Export Full Engineering Delivery Bundle & Sync 3D Design'],
  ['③ 一键导出全套工程交付包 &amp; 同步三维设计', '③ Export Full Engineering Delivery Bundle & Sync 3D Design'],
  ['一键导出全套工程交付包 & 同步三维设计', 'Export Full Engineering Delivery Bundle & Sync 3D Design'],
  ['一键导出全套工程交付包', 'Export Full Engineering Delivery Bundle'],
  ['导出全套工程交付包', 'Export Engineering Delivery Bundle'],
  ['光筑工程交付包', 'Guangzhu Engineering Delivery Bundle'],
  ['工程交付中心', 'Engineering Delivery Center'],
  ['交付中心', 'Delivery Center'],
  ['打开交付文件夹', 'Open Delivery Folder'],
  ['打开所在文件夹', 'Open Containing Folder'],
  ['8项出图前工程合规自检卡', '8-Item Pre-Delivery Engineering Compliance Checklist'],
  ['出图前工程合规自检卡', 'Pre-Delivery Engineering Compliance Checklist'],
  ['8项工程健康自检', '8-Item Engineering Health Check'],
  ['工程健康度自检', 'Engineering Health Check'],
  ['重新运行合规自检', 'Re-run Compliance Check'],
  ['全部合规通过', 'All Checks Passed'],
  ['存在警告项', 'Warnings Detected'],
  ['存在不合规项', 'Action Required'],
  ['容配比合理性校核', 'DC/AC Sizing Ratio Check'],
  ['极寒开路电压安全裕度', 'Extreme Cold Voc Safety Margin'],
  ['高温工作电压MPPT窗口校核', 'High-Temp Vmpp MPPT Window Check'],
  ['屋面新增静荷载裕度校核', 'Roof Dead-Load Safety Margin Check'],
  ['台风风揭边角退距校核', 'Typhoon Wind Uplift Setback Check'],
  ['直流回路压降校核', 'DC String Voltage Drop Check'],
  ['全年近处遮挡损失校核', 'Annual Near-Shading Loss Check'],
  ['全投资收益率与回收期校核', 'Project IRR & Payback Viability Check'],
  ['整改建议', 'Remediation Advice'],
  ['极端低温设定：', 'Extreme Cold Design Temp: '],
  ['极端低温设定', 'Extreme Cold Design Temp'],
  ['极端高温设定：', 'Extreme Hot Design Temp: '],
  ['极端高温设定', 'Extreme Hot Design Temp'],
  ['· 当前采用', '· Active Scheme'],
  ['当前采用', 'Active Scheme'],
  ['· 最不利压降', '· Max Voltage Drop'],
  ['最不利压降', 'Max Voltage Drop'],
  ['通道编号', 'MPPT Channel'],
  ['全年水平面总辐照', 'Annual Global Horizontal Irradiation'],
  ['水平总辐照', 'Global Horiz. Irradiation'],
  ['水平散射', 'Diffuse Horiz. Irradiation'],
  ['斜面总辐照', 'Global Incident POA'],
  ['有效辐照', 'Effective Irradiation'],
  ['背面增益', 'Rear Bifacial Gain'],
  ['阵列直流电量', 'Array DC Energy'],
  ['直流阵列有效输出', 'Effective Array DC Output'],
  ['综合效率', 'Performance Ratio'],
  ['· 判定：', '· Verdict: '],
  ['判定：', 'Verdict: '],
  ['专业校核：', 'Checked By: '],
  ['专业校核', 'Checked By'],
  ['批准签章：', 'Approved By: '],
  ['批准签章', 'Approved By'],
  ['编制人：', 'Prepared By: '],
  ['编制人', 'Prepared By'],
  ['审定人：', 'Authorized By: '],
  ['审定人', 'Authorized By'],
  ['首年发电：', '1st-Yr Yield: '],
  ['双向计量表 kWh', 'Bi-Directional Meter kWh'],
  ['QS 总隔离开关', 'QS Main Isolator'],
  ['谷电充电1', 'Valley Charge 1'],
  ['早峰放电1', 'Morning Discharge 1'],
  ['午间光伏充2', 'Midday PV Charge 2'],
  ['晚尖峰放电2', 'Evening Peak Discharge 2'],
  ['运营年份', 'Operating Year'],
  ['全部线路', 'All Circuits'],
  ['模型 key', 'Model API Key'],
  ['先在首页填 key', 'Enter API Key on Home first'],
  ['需求请在右侧 AGH 里直接说', 'Describe your requirements in the AI assistant panel'],
  ['重新加载3D', 'Reload 3D Scene'],
  ['C. 大跨度预应力柔性索桁架', 'C. Large-Span Pre-Stressed Cable Truss'],
  ['全期净收益元', 'Lifetime Net Cashflow (RMB)'],
  ['累计净收益元', 'Cumulative Net Cashflow (RMB)'],
  ['发电 kWh', 'Generation (kWh)'],
  ['自用 kWh', 'Self-Use (kWh)'],
  ['上网 kWh', 'Grid Export (kWh)'],
  ['弃电 kWh', 'Curtailment (kWh)'],
  ['到下一角 m', 'Edge Length (m)'],
  ['复制一份（向东）', 'Duplicate (+East)'],
  ['东西双坡与正南曲线负荷匹配仿真', 'East-West vs. South 24h Load-Matching Simulation'],
  ['造价与电价双因子财务敏感性矩阵', 'CAPEX × Tariff 3×3 Financial Sensitivity Matrix'],
  ['双班工业日间负荷', 'Two-Shift Industrial Load'],
  ['商业午后高峰负荷', 'Commercial Afternoon Peak Load'],
  ['连续二十四小时恒定负荷', 'Continuous 24h Baseload'],
  ['全园多因子工程与消纳汇总', 'Campus Multi-Factor Physics & Synergy KPIs'],
  ['全园直流总装机', 'Total Campus DC Capacity'],
  ['全园加权系统效率', 'Weighted System PR'],
  ['园区多栋协同自用消纳率', 'Campus Self-Consumption Synergy'],
  ['全园年碳减排总量', 'Annual CO₂ Reduction'],
  ['专变与并网容量校核', 'Transformer & Grid Hosting Check'],
  ['按已设计各栋装机容量加权核算', 'Capacity-weighted across designed buildings'],
  ['园区多因子物理仿真参考基准', 'Campus multi-factor simulation baseline'],
  ['母线负荷聚合增益', 'Busbar load-pooling lift'],
  ['变压器×0.8参考上限', '0.8× transformer limit'],
  ['投资与电价双因素敏感性矩阵', 'CAPEX × Tariff Sensitivity Matrix'],
  ['源荷匹配逐时消纳对比', 'Hourly PV-Load Matching Profile'],

  // Campus (#park) Full UI, 2D/3D Panes, Batch Center & Queue
  ['载入武进工业园区', 'Load Wujin Industrial Park'],
  ['按原始坐标摆放', 'Reset Coordinates'],
  ['🏢 一键同步邻楼3D遮挡', '🏢 Sync Neighbor 3D Shading'],
  ['一键同步邻楼3D遮挡', 'Sync Neighbor 3D Shading'],
  ['删除园区', 'Delete Campus'],
  ['加入厂房', 'Add Building'],
  ['拖动下方左侧 2D 平面图楼栋可调整园区相对位置，右侧 3D 园区全景沙盘实时联动显示真实三维园区建筑、障碍物与设计后的全园区光伏阵列（点击 3D 楼栋可直达单栋精细工作台）。', 'Drag buildings on the 2D site plan (left) to adjust campus positions; the 3D digital twin (right) updates buildings, obstacles, and PV arrays in real time (click any 3D building to open its workbench).'],
  ['📐 园区 2D 总平面布置与拖拽定位图', '📐 Campus 2D Master Plan & Drag Positioning'],
  ['园区 2D 总平面布置与拖拽定位图', 'Campus 2D Master Plan & Drag Positioning'],
  ['鼠标拖拽屋面可移动坐标', 'Drag roofs to adjust coordinates'],
  ['🌐 真实园区 3D 全景数字孪生沙盘', '🌐 Campus 3D Digital Twin Sandbox'],
  ['真实园区 3D 全景数字孪生沙盘', 'Campus 3D Digital Twin Sandbox'],
  ['园区 3D 全景数字孪生沙盘', 'Campus 3D Digital Twin Sandbox'],
  ['🏛 鸟瞰', '🏛 Isometric'],
  ['⬇ 顶视', '⬇ Top View'],
  ['☀ 南向', '☀ South View'],
  ['🎨 分期着色', '🎨 Color by Phase'],
  ['🎨 实景深蓝', '🎨 Realistic Blue'],
  ['▶ 日照动画', '▶ Sun Animation'],
  ['⏸ 暂停日照', '⏸ Pause Sun'],
  ['冬至日 (12-21)', 'Winter Solstice (12-21)'],
  ['春分日 (03-21)', 'Equinox (03-21)'],
  ['夏至日 (06-21)', 'Summer Solstice (06-21)'],
  ['时刻', 'Time'],
  ['⚡ 园区一键设置与批量工程配置中心', '⚡ Campus One-Click Setup & Batch Engineering Center'],
  ['园区一键设置与批量工程配置中心', 'Campus One-Click Setup & Batch Engineering Center'],
  ['一键预设园区专变/并网/预算约束、统一组件与逆变器选型、负荷电价及全园邻楼 3D 遮挡坐标', 'One-click preset for transformer/grid/budget limits, unified module & inverter models, load tariffs, and neighbor 3D shading'],
  ['一键标准工商业配置', 'Standard C&I Preset'],
  ['一键高收益满铺配置', 'Max-Capacity Preset'],
  ['一键快回本稳健配置', 'Fast-Payback Preset'],
  ['一键轻质低荷载配置', 'Lightweight Roof Preset'],
  ['☑️ 全选/反选厂房', '☑️ Select / Invert All'],
  ['全选/反选厂房', 'Select / Invert All'],
  ['✅ 一键应用设置并同步园区3D坐标', '✅ Apply Settings & Sync 3D Coordinates'],
  ['🚀 一键设置并立即全园排板计算', '🚀 Apply & Batch-Run Campus Layout'],
  ['🧹 清空园区已有排板', '🧹 Clear Campus Designs'],
  ['自动补齐专变/并网/预算约束并同步邻楼 3D 遮挡。', 'Auto-fills transformer/grid/budget limits and syncs neighbor 3D shading.'],
  ['展开批量设备、电价与电缆细项设置 (8项)', 'Expand Batch Equipment, Tariff & Cable Settings (8 Items)'],
  ['按需微调', 'Fine-tune'],
  ['统一光伏组件选型', 'Unified PV Module Model'],
  ['统一逆变器品牌', 'Unified Inverter Brand'],
  ['自动匹配最优容配比', 'Auto-Match Optimal DC/AC Ratio'],
  ['华为数字能源 (SUN2000)', 'Huawei Digital Power (SUN2000)'],
  ['阳光电源 (SG系列)', 'Sungrow (SG Series)'],
  ['锦浪科技 (GCI系列)', 'Solis / Ginlong (GCI Series)'],
  ['固德威 (GW系列)', 'GoodWe (GW Series)'],
  ['上能电气 (SN系列)', 'Sineng Electric (SN Series)'],
  ['正泰电源 (CPS系列)', 'Chint Power (CPS Series)'],
  ['三维批量排版算法', '3D Batch Layout Algorithm'],
  ['多目标帕累托自动寻优 (推荐)', 'Multi-Objective Pareto Auto-Opt (Recommended)'],
  ['冬至 9:00-15:00 真太阳时零遮挡排距', 'Winter Solstice 09:00-15:00 Unshaded Pitch'],
  ['顺屋脊正交高密网格排布', 'Ridge-Orthogonal High-Density Grid'],
  ['10° 东西向人字形高密度排布', '10° East-West Butterfly Dense Layout'],
  ['三方案决策偏好 & 目标回本', '3-Scheme Preference & Max Payback'],
  ['三方案决策偏好 &amp; 目标回本', '3-Scheme Preference & Max Payback'],
  ['折中优选', 'Balanced Optimum'],
  ['最大装机', 'Max Capacity'],
  ['最快回本', 'Fastest Payback'],
  ['回本上限(年)', 'Max Payback (yr)'],
  ['统一加权自用电价 (元/度)', 'Blended Self-Use Tariff (RMB/kWh)'],
  ['单栋月均用电量 (万度/月)', 'Monthly Load per Building (10⁴ kWh/mo)'],
  ['统一厂房生产班次', 'Plant Shift Schedule'],
  ['白班单班 (8:00-17:30)', 'Single Day Shift (08:00-17:30)'],
  ['两班制生产 (含周末轮休)', 'Two-Shift Operation (Rotating Weekends)'],
  ['三班24h连续生产', '24h Continuous Three-Shift'],
  ['统一交直流电缆选型', 'Unified DC / AC Cable Family'],
  ['并网限制', 'Grid Limit'],
  ['1 · 一期优先', '1 · Phase 1'],
  ['2 · 二期扩建', '2 · Phase 2'],
  ['— 待设计', '— Pending'],
  ['一期优先', 'Phase 1'],
  ['二期扩建', 'Phase 2'],
  ['查看单栋3D', 'View 3D'],
  ['条件与开工问答', 'Constraints & Survey'],
  ['移出', 'Remove'],
  ['尚无可核验结果', 'No verified result yet'],
  ['尚无核验设计', 'No verified design yet'],
  ['完成单栋或园区批量设计后可打开报告', 'Run single-building or batch campus design first'],
  ['混凝土平屋顶', 'Flat Concrete Roof'],
  ['彩钢瓦屋面', 'Standing-Seam Metal Roof'],
  ['多坡屋面', 'Multi-Pitch Roof'],
  ['地面阵列', 'Ground-Mount Array'],
  ['光伏车棚', 'Solar Carport'],
  ['整体回本', 'Campus Payback'],
  ['实际额定 AC', 'Rated AC'],
  ['上限未填', 'Unset'],
  ['待核定', 'Pending'],
  ['未超出', 'Within Limit'],
  ['无法核定', 'Unverified'],
  ['未填', 'Unset'],
  ['税后整体', 'Post-Tax Total '],
  ['贷款权益税后', 'Levered Equity Post-Tax '],
  ['额定 AC 由归档电气文件每台直流容量和未舍入容配比还原。', 'Rated AC restored from archived per-inverter DC capacity and unrounded DC/AC ratio.'],
  ['园区按整栋回本顺序分期，沿 T22 预算和兼容 AC 阈值；屋顶内分期不重复相加。绿色/蓝色一期，橙色/棕色二期。', 'Campus phased by building payback order under budget & AC limits; green/blue = Phase 1, orange/brown = Phase 2.'],
  ['旋转角度', 'Rotation Angle'],
  ['转角°', 'Angle°'],
  ['⚡ 批量运行本机规则设计（含邻楼3D遮挡与三方案）', '⚡ Batch-Run Local Physics Design (Neighbor 3D Shading + 3 Schemes)'],
  ['✅ 确认并批准勾选厂房导出', '✅ Approve Selected Buildings for Export'],
  ['📄 生成园区方案书', '📄 Generate Campus Proposal'],
  ['📖 打开园区方案书', '📖 Open Campus Proposal'],
  ['共享条件与运行设置', 'Shared Constraints & Run Settings'],
  ['一键设计勾选厂房', 'Queue Selected Buildings'],
  ['暂停后续', 'Pause Queue'],
  ['继续 / 恢复', 'Resume Queue'],
  ['跳过当前栋', 'Skip Current'],
  ['放弃这个队列', 'Discard Queue'],
  ['等待原生批准', 'Awaiting Approval'],
  ['需核对原会话', 'Check Session'],
  ['准备会话', 'Preparing'],
  ['· 已暂停后续派发', '· Queue Paused'],
  ['暂无可靠模型费估计；缺额、没有记录或币种混合时不填0，不换算人民币。', 'No inference cost estimate (blank when unrecorded or mixed-currency).'],
  ['暂无可靠模型费估计', 'No inference cost estimate'],
  ['删除园区及其队列和方案书？原屋顶、单栋项目和设计记录保留。', 'Delete campus, queue, and campus proposal? Individual roofs and project records are kept.'],

  // Satellite Workbench (#satmap) Tools, Right-Rail Map Strip & Array Unit Parameters
  ['组件排布参数 (2×9 标准阵列单元)', 'Array Layout Parameters (2×9 Unit)'],
  ['阵列排布参数 (2×9单元)', 'Array Layout Parameters (2×9 Unit)'],
  ['阵列排布参数', 'Array Layout Parameters'],
  ['阵列单元快捷预设', 'Array Unit Quick Presets'],
  ['2×9 标准串', '2×9 Standard'],
  ['2×12 大组串', '2×12 Long String'],
  ['1×18 单排串', '1×18 Single Row'],
  ['(2×9阵列单元)', '(2×9 Array Unit)'],
  ['1. 绘制屋顶 (点选角点)', '1. Draw Roof (Click Corners)'],
  ['1. 绘制屋顶 (矩形框选)', '1. Draw Roof (Rectangle)'],
  ['1. 绘制屋顶', '1. Draw Roof'],
  ['2. 矩形屋顶 (拉框)', '2. Rect Roof (Drag Box)'],
  ['2. 多点画屋面 (异形轮廓)', '2. Polygon Roof (Click Corners)'],
  ['2. 绘制禁布区', '2. Draw Keep-Out'],
  ['3. 多点画禁布区', '3. Polygon Keep-Out'],
  ['4. 删除选中禁布区', '4. Delete Keep-Out'],
  ['漫游平移卫星图', 'Pan Satellite Map'],
  ['漫游平移', 'Pan Map'],
  ['拖拽/缩放', 'Drag / Zoom'],
  ['拖拽/对角点击', 'Drag / 2 Corners'],
  ['点选角点', 'Click Corners'],
  ['点击移除', 'Click to Remove'],
  ['自动校准比例/方向', 'Auto Scale & Axis'],
  ['自动识别比例尺/方向', 'Auto Scale & Axis'],
  ['清除重画', 'Clear & Redraw'],
  ['地图选址', 'Pick Site'],
  ['重新绘制', 'Redraw'],
  ['上传底图', 'Upload Base'],
  ['绘制 (多点画屋顶)', 'Draw Polygon Roof'],
  ['区域编辑 (微调顶点)', 'Edit Vertices'],
  ['矩形绘制', 'Draw Rect Roof'],
  ['障碍物 (多点画禁布区)', 'Obstacle Keep-Out'],
  ['标定比例尺', 'Calibrate Scale'],
  ['确定方向', 'Set Azimuth Axis'],
  ['屋面坡度/分水线', 'Roof Slope / Ridge'],
  ['阴影模拟', 'Shadow Sim'],
  ['阴影分析', 'Shadow Check'],
  ['多维因数寻优', 'Multi-Factor'],
  ['全景三维仿真', '3D Digital Twin'],
  ['下一步 (电气设计) →', 'Next (Electrical) →'],
  ['退出全屏 (Esc)', 'Exit Fullscreen (Esc)'],
  ['退出全屏', 'Exit Fullscreen'],
  ['全屏地图', 'Fullscreen Map'],
  ['更多工具 ▾', 'More Tools ▾'],
  ['多点画屋顶', 'Polygon Roof'],
  ['多点画禁布区', 'Polygon Keep-Out'],
  ['点选增删组件', 'Toggle Module'],
  ['1. 点选增删单块组件', '1. Toggle Individual Module'],
  ['2. 多点补画禁布区', '2. Add Keep-Out Polygon'],
  ['3. 漫游与角点微调', '3. Pan & Tune Vertices'],
  ['点击画布组件', 'Click module on canvas'],
  ['拖动角点自动重排', 'Drag vertex to re-layout'],
  ['删除禁布区', 'Delete Keep-Out'],
  ['重新满铺排布', 'Re-Layout Full Roof'],
  ['图层', 'Layers'],
  ['定位', 'Locate'],
  ['特写', 'Zoom Roof'],
  ['右下角竖向地图控制条', 'Map Viewport Controls'],
  ['显示/隐藏屋面与组件图层', 'Show / Hide Roof & PV Overlay'],
  ['打开地图拾取经纬度弹窗', 'Open Coordinate Picker Modal'],
  ['2D平面建模视图', '2D Plan Modeling View'],
  ['3D真实数字孪生与光线追踪视图', '3D Digital Twin & Ray-Tracing View'],
  ['真实材质', 'Realistic'],
  ['辐照热力', 'Irradiance'],
  ['二极管失配', 'Diode Mismatch'],
  ['组串桥架', 'Tray & Wiring'],
  ['抗风分区', 'Wind Zones'],
  ['暂停日照', 'Pause Sun'],
  ['日照动画', 'Sun Play'],
  ['三维轴测', '3D Iso'],
  ['正南航拍', 'South View'],
  ['屋面巡检', 'Walkway'],
  ['人眼街景', 'Street View'],
  ['正顶俯视', 'Top View'],
  ['同步遮挡损耗', 'Sync 3D Shade'],
  ['导出三维截图', 'Export 3D PNG'],
  ['返回二维底图', 'Back to 2D Map'],
  ['1. 屋面', '1. Roof'],
  ['2. 布局', '2. Layout'],
  ['3. 信息', '3. Summary'],
  ['1. 组件排布', '1. PV Layout'],
  ['2. 电气配置', '2. Electrical'],
  ['待绘制屋面', 'Draw roof first'],
  ['阵列参数', 'Array Params'],
  ['选型方式', 'Sizing Mode'],
  ['智能推荐', 'Auto Match'],
  ['自选逆变器', 'Manual Pick'],
  ['竖向排布', 'Portrait'],
  ['横向排布', 'Landscape'],
  ['详细配置', 'Configure'],
  ['内部投决报告', 'Internal IC Report'],
  ['业主汇报书', 'Owner Proposal'],
  ['载入标准厂房样板', 'Load Standard Factory'],
  ['AI 按要求一键设计', 'AI One-Click Design'],
  ['AI 一键设计', 'AI Auto-Design'],
  ['搜索定位', 'Search'],
  ['位置搜索', 'Search Site'],
  ['省市区', 'Region'],
  ['全国任意位置 / 快捷选区', 'Nationwide Site / Quick Presets'],
  ['高清卫星混合底图 (含路网企业标注)', 'HD Hybrid Satellite (Roads & Labels)'],

  // Multi-Factor Studio & 3D Linkage Extra Labels
  ['多维可能性因数寻优', 'Multi-Factor Optimization'],
  ['运行多维因数寻优', 'Run Multi-Factor Optimizer'],
  ['收起多维因数面板', 'Collapse Multi-Factor Panel'],
  ['展开多维因数面板', 'Expand Multi-Factor Panel'],
  ['收起联动对比', 'Hide 3D Diff'],
  ['查看三维联动对比', 'Show 3D Diff'],
  ['三维设计基准 / 差值', '3D Baseline / Delta'],
  ['阵列排布拓扑', 'Array Topology'],
  ['环境灰尘与盐雾', 'Soiling & Salt-Mist Grade'],
  ['企业用电负荷曲线', 'Enterprise Load Profile'],
  ['多目标寻优偏好', 'Optimization Objective'],
  ['六维综合评估雷达', '6-Axis Evaluation Radar'],
  ['六维工程因数评估雷达图', '6-Axis Engineering Factor Radar'],
  ['候选工程方案', 'Candidate Schemes'],
  ['综合得分与校核', 'Composite Score & Checks'],
  ['全项合规', 'All Checks Pass'],
  ['应用此方案', 'Apply Scheme'],
  ['综合优选方案', 'Balanced Pareto Optimum'],
  ['综合帕累托推荐', 'Balanced Pareto Optimum'],
  ['企业自发消纳最高', 'Max Self-Consumption'],
  ['消除短板失配损耗', 'Eliminates poison-module mismatch'],
  ['一般工商业城区', 'Standard C&I Urban'],
  ['重工业粉尘密集区', 'Heavy Industrial Dust'],
  ['沿海高盐雾腐蚀区', 'Coastal Salt-Mist Zone'],
  ['农牧氨气高湿环境', 'High-Humidity Agro/Ammonia'],
  ['工业白班生产负荷', 'Daytime Industrial Load'],
  ['二十四小时连续负荷', '24h Continuous Baseload'],
  ['全额上网模式', '100% Feed-in Export'],
  ['深色沥青防水卷材 (0.12)', 'Dark Bitumen Membrane (0.12)'],
  ['高反白膜', 'White TPO'],
  ['发电性能', 'Specific Yield'],
  ['度电经济', 'LCOE Economics'],
  ['自发消纳', 'Self-Use'],
  ['配储容量', 'BESS Capacity'],

  // Satellite View, 8760h Workbench & Cross-App Toolbar / Inspector Labels
  ['目标容配比范围', 'Target DC/AC Ratio Range'],
  ['当前实际容配比', 'Actual DC/AC Ratio'],
  ['容配比：', 'DC/AC Ratio: '],
  ['实时气象：', 'Live Weather: '],
  ['刷新实时气象', 'Refresh Weather'],
  ['点击展开/收起明细', 'Click to Expand / Collapse Details'],
  ['常规候选', 'Standard Candidate'],
  ['谷歌地图 (高清混合图)', 'Google Hybrid Satellite'],
  ['当前选址中心：', 'Site Center: '],
  ['生产班制与负荷消纳模型', 'Shift Schedule & Load Profile'],
  ['单班白班制 (双休低荷)', 'Single Day Shift (Low Weekend Load)'],
  ['双班生产制 (周六排产)', 'Two-Shift Production (Sat Active)'],
  ['折现率基准 (%)', 'Discount Rate (%)'],
  ['静/动态回收期：', 'Simple / Discounted Payback: '],
  ['高级工程', 'Advanced Engineering'],
  ['下一步 →', 'Next →'],
  ['· 共', '· Total '],
  ['返回卫星图', 'Back to Map'],
  ['实景阵列：', 'Rendered Array: '],
  ['⚡ 输入用电信息', '⚡ 1. Load & Tariff'],
  ['📊 光伏设计模拟', '📊 2. PV Simulation'],
  ['📐 光伏图纸生成', '📐 3. CAD Drawings'],
  ['项目：', 'Project: '],
  ['工程：', 'Project: '],
  ['日期：', 'Date: '],
  ['坐标：', 'Coordinates: '],
  ['图例：', 'Legend: '],
  ['防孤岛/故障解列', 'Anti-Islanding / Fault Trip'],
  ['明显断开点', 'Visible Disconnect'],
  ['一次系统主要电气参数与整定计算表', 'Primary Electrical Parameters & Relay Schedule'],
  ['图纸专业分类', 'Discipline'],
  ['规格型号', 'Model / Spec'],
  ['技术规范备注', 'Technical Notes'],
  ['结构大样与防水施工技术要求：', 'Structural Detail & Waterproofing Notes: '],
  ['微机防孤岛保护装置', 'Microprocessor Anti-Islanding Relay'],
  ['电网调度自动化远动端', 'Grid Dispatch RTU Telecontrol'],
  ['· 支持「四遥」: 遥测/遥信/遥控/遥调', '· 4-Remote Telemetry / Signaling / Control / Regulating'],
  ['二次控制与通讯施工规范：', 'Secondary Control & SCADA Notes: '],
  ['厂区重要生产负荷', 'Critical Plant Production Loads'],
  ['绿电消纳提升至', 'Green Power Self-Use Raised to'],
  ['爬梯', 'Access Ladder'],
  ['卫星设计工作流步骤', 'Satellite Design Workflow Steps'],
  ['全国搜索候选位置', 'Nationwide Site Search Results'],
  ['卫星地图工具栏', 'Satellite Map Toolbar'],
  ['深色系统快捷导航', 'Quick System Navigation'],
  ['折算出力', 'Specific Output'],
  ['分项增损率', 'Stage Gain / Loss'],
  ['■ 正向增益 (转置/双面/正公差)', '■ Positive Gain (Transposition / Bifacial / Sorting)'],
  ['■ 能量损耗级差', '■ Stage Energy Loss'],
  ['(均值)', '(Mean)'],
  ['★ 寻优最佳点：', '★ Optimal Point: '],
  ['阵列中心节距：', 'Row Pitch: '],
  ['中英切换', 'ZH / EN'],
  ['双面反射增益已计入', 'Bifacial Albedo Gain Included'],
  ['📍 回到任务', '📍 Back to Task'],
  ['泰州实景案例', 'Taizhou Field Case'],
  ['怎么跑这次设计', 'Design Run Mode'],
  ['一句话需求', 'Design Brief'],
  ['必填，用你自己的话说', 'Required — describe your target in plain words'],
  ['打开方案书', 'Open Proposal'],
  ['方案书', 'Proposal'],
  ['建议原文', 'Original Note'],
  ['查看结果 →', 'View Result →'],
  ['依据：', 'Basis: '],
  ['建议：', 'Recommendation: '],
  ['正在核对本版本输入、计算与规则，请稍候…', 'Verifying inputs, calculations, and engineering rules…'],
  ['批准只使用一次；修改输入或设计后需要重新预检查。', 'Approval applies once; re-check after editing inputs or layout.'],
  ['原生会话', 'Engine Session'],
  ['界面主题', 'Theme'],
  ['粘贴模型访问密钥', 'Paste Model API Key'],
  ['模型访问密钥', 'Model API Key'],
  ['按本版本设备、天气和几何计算；缺失项单独标记', 'Computed from version equipment, weather, and geometry; missing items flagged'],
  ['执行规则指令 →', 'Run Rule Command →'],
  ['🕸 三方案五维工程经济综合对比雷达图', '🕸 3-Scheme 5-Axis Techno-Economic Radar'],
  ['三方案五维工程经济对比雷达图', '3-Scheme 5-Axis Techno-Economic Radar'],
  ['本版本输入已改变，精算指标需重新计算。', 'Inputs changed; recalculate metrics for this version.'],
  ['两部制需量电费削减(试算)：', 'Demand Charge Saving (Est.): '],
  ['配储峰谷套利潜力(试算)：', 'BESS Arbitrage Potential (Est.): '],
  ['失压脱扣 · 二级防雷', 'Undervoltage Trip · Type II SPD'],
  ['厂区专变与母线', 'Plant Transformer & Busbar'],
  ['工程计算参数 / 整定值', 'Calculated Parameters / Settings'],
  ['厂区配电专变容量包络', 'Plant Transformer Capacity Envelope'],
  ['建议专变 ≥', 'Rec. Transformer ≥'],
  ['建议配置', 'Recommended'],
  ['静止无功发生器', 'Static Var Generator (SVG)'],
  ['可选配', 'Optional'],
  ['企业工程技术规格与节点要求', 'Engineering Specifications & Detail Requirements'],
  ['导轨与结构防腐', 'Rails & Corrosion Protection'],
  ['防雷与等电位接地', 'Lightning & Equipotential Grounding'],
  ['运维消防与检修通道', 'O&M Fire Lane & Walkways'],
  ['结构适装方案', 'Structural Mounting Scheme'],
  ['商业模式', 'Business Model'],
  ['三、决策签批与开工前必查清单', 'III. Sign-Off & Pre-Construction Checklist'],
  ['走线寻优算法：', 'Routing Algorithm: '],
  ['最大压降 %', 'Max Voltage Drop %'],
  ['计算与敷设条件（示意）', 'Calculation & Routing Conditions (Ref.)'],
  ['坡面 / 材料', 'Roof Plane / Material'],
  ['方案 / 要求', 'Scheme / Requirement'],
  ['检查依据', 'Verification Basis'],
  ['三维直接编辑', '3D Direct Edit'],
  ['邻板对齐', 'Snap to Neighbor'],
  ['原损失 %', 'Prev Loss %'],
  ['新损失 %', 'New Loss %'],
  ['变化百分点', 'Delta (pp)'],
  ['锁定与局部重排', 'Lock & Local Re-Layout'],
  ['修改原因', 'Edit Reason'],
  ['查看原版本', 'View Base Version'],
  ['输入假设与计算依据', 'Input Assumptions & Calculation Basis'],
  ['输入一致性', 'Input Consistency'],
  ['整套输出', 'Deliverable Bundle'],
  ['项目要求', 'Project Requirements'],
  ['经济假设', 'Financial Assumptions'],
  ['会话时长', 'Session Duration'],
  ['模型请求', 'Model Requests'],
  ['没有关联原生会话用量，不能据此认定模型调用或费用为零。', 'No linked session telemetry; zero calls or cost cannot be assumed.'],
  ['购电类别', 'Tariff Category'],
  ['内部自建自用不适用；具体主体和项目资格须核实。', 'N/A for owner-invested self-use; verify entity & project eligibility.'],
  ['税和贷款', 'Tax & Debt'],
  ['投资方式', 'Investment Mode'],
  ['税费、运维与资格假设', 'Tax, O&M & Eligibility Assumptions'],
  ['查看逐月数值与合计', 'View Monthly Values & Total'],
  ['本版本逐月发电计算结果', 'Monthly Yield Results (Current Version)'],
  ['查看主立面', 'View Main Facade'],
  ['墙面材质', 'Wall Cladding'],
  ['窗带排数', 'Window Strip Rows'],
  ['入口与装卸', 'Doors & Loading Bays'],
  ['主立面（朝向为外墙向外方向）', 'Main Facade (Outward Normal)'],
  ['细节随墙长与净高适配；空间不足时自动减少或略去。', 'Details adapt to wall length and clear height.'],
  ['安装场地', 'Installation Site'],
  ['新增方阵不得占用任何耕地；须核实土地权属、用途、林草和生态管控。独立空地通常按集中式管理，不能自动视作分布式。', 'Arrays must not occupy arable land; verify land title, zoning, forestry, and grid classification.'],
  ['全周统一', 'Uniform Perimeter'],
  ['分段编辑', 'Per-Edge Edit'],
  ['按当前轮廓重新生成', 'Regenerate from Outline'],
  ['外墙边', 'Perimeter Edge'],
  ['建模对象列表', 'Scene Object List'],
  ['建模对象', 'Scene Objects'],
  ['更多属性', 'More Properties'],
  ['精确变换', 'Numeric Transform'],
  ['保留原对象，生成副本', 'Keep original, create copy'],
  ['应用变换', 'Apply Transform'],
  ['适合全部', 'Fit All'],
  ['正在生成实际坡面…', 'Generating roof planes…'],
  ['承重来源', 'Load Basis'],
  ['二维编辑', '2D Plan'],
  ['三维建筑', '3D Building'],
  ['几何吸附', 'Geometry Snap'],
  ['拖动或点一下，在这里加一个角', 'Drag or click to insert a vertex'],
  ['结构输入须现场核实，示意量不能代替施工设计。', 'Verify structural inputs on site; indicative values do not replace structural design.'],
  ['最近市中心推定（非行政归属）', 'Nearest urban center estimate (non-administrative)'],
  ['普通用途', 'General Industrial'],
  ['沿长边中心', 'Along Long Axis'],
  ['沿短边中心', 'Along Short Axis'],
  ['所属坡面', 'Roof Plane'],
  ['阵列总数（含原件）', 'Array Count (incl. original)'],
  ['全景俯视', 'Top Overview'],
  ['投影方式', 'Projection Mode'],
  ['回放位置', 'Playback Position'],
  ['回放会话', 'Playback Session'],
  ['关掉后可以点在任意位置，适合描密集的转角', 'Disable to place vertices freely around tight corners'],
  ['捕捉邻近端点、中点和边线；拖动时排除自身', 'Snap to nearby endpoints, midpoints, and edges'],
  ['先给图纸定比例', 'Calibrate drawing scale first'],
  ['在这条边中间加一个角', 'Insert vertex on this edge'],
  ['删掉这个角', 'Delete this vertex'],
];

const ZH_TO_EN_PHRASES = [...ZH_TO_EN_PHRASES_RAW].sort((a, b) => b[0].length - a[0].length);

// Word-level fallback lexicon for any remaining dynamic Chinese text in English mode
const ZH_WORD_LEXICON = [
  ['山东省', 'Shandong '], ['江苏省', 'Jiangsu '], ['广东省', 'Guangdong '], ['浙江省', 'Zhejiang '],
  ['福建省', 'Fujian '], ['陕西省', 'Shaanxi '], ['上海市', 'Shanghai '], ['北京市', 'Beijing '],
  ['济南市', 'Jinan '], ['淄博市', 'Zibo '], ['济宁市', 'Jining '], ['泰州市', 'Taizhou '],
  ['佛山市', 'Foshan '], ['嘉兴市', 'Jiaxing '], ['宁德市', 'Ningde '], ['西安市', 'Xi\'an '],
  ['历城区', 'Licheng '], ['海陵区', 'Hailing '], ['高新区', 'High-Tech Zone '], ['工业北路', 'North Industrial Rd'],
  ['工业园区', 'Industrial Park'], ['工业园', 'Industrial Park'], ['经济开发区', 'Economic Dev Zone'],
  ['分布式光伏项目', ' Distributed PV Project'], ['分布式屋顶光伏发电项目', ' Rooftop PV Project'],
  ['施工图', ' CAD Drawings'], ['光筑智能光伏工程设计院', 'Guangzhu PV Engineering Institute'],
  ['光筑', 'Guangzhu'], ['阳光电源', 'Sungrow'], ['华为', 'Huawei'], ['固德威', 'GoodWe'],
  ['古瑞瓦特', 'Growatt'], ['锦浪', 'Solis'], ['隆基', 'LONGi'], ['晶科', 'Jinko'], ['天合', 'Trina'], ['通威', 'Tongwei'], ['尚德', 'Suntech'],
  ['全部品牌', 'All Brands'], ['全部功率', 'All Ratings'], ['当前已选型', 'Selected'], ['选型此逆变器', 'Select Inverter'], ['已选型', 'Selected'],
  ['逆变器名称', 'Inverter'], ['组串名称', 'String ID'], ['接入组串数', 'Strings'], ['组串占比', 'Share'],
  ['工作电压', 'Operating Vmp'], ['开路电压', 'Open-Circuit Voc'], ['串联组件数', 'Modules / String'],
  ['直流装机', 'DC Capacity'], ['交流容量', 'AC Capacity'], ['装机容量', 'Capacity'], ['装机', 'Capacity'],
  ['组件数量', 'Modules'], ['组件块数', 'Modules'], ['组件', 'Module'], ['逆变器', 'Inverter'],
  ['组串', 'String'], ['配串', 'Stringing'], ['屋面', 'Roof'], ['屋顶', 'Roof'], ['女儿墙', 'Parapet'],
  ['禁布区', 'Keep-Out'], ['障碍物', 'Obstacle'], ['采光带', 'Skylight'], ['天窗', 'Skylight'],
  ['通风井', 'Vent Shaft'], ['风机房', 'Fan Room'], ['电梯机房', 'Elevator Room'], ['屋脊线', 'Ridge Line'], ['屋脊', 'Ridge'],
  ['双坡', 'Gable'], ['单坡', 'Mono-Slope'], ['彩钢瓦', 'Metal Roof'], ['混凝土', 'Concrete'],
  ['配重墩', 'Ballast Pier'], ['压块', 'Ballast'], ['夹具', 'Clamp'], ['支架', 'Racking'],
  ['倾角', 'Tilt'], ['坡度', 'Slope'], ['方位角', 'Azimuth'], ['排距', 'Row Pitch'], ['间距', 'Spacing'],
  ['退距', 'Setback'], ['检修马道', 'O&M Walkway'], ['消防通道', 'Fire Lane'], ['清洗水路', 'Cleaning Water Loop'],
  ['桥架', 'Cable Tray'], ['线缆', 'Cable'], ['电缆', 'Cable'], ['直流', 'DC'], ['交流', 'AC'],
  ['并网柜', 'Grid Tie Cabinet'], ['并网点', 'Grid Point'], ['并网', 'Grid-Tied'], ['变压器', 'Transformer'],
  ['防逆流', 'Anti-Backflow'], ['无功补偿', 'Reactive Comp'], ['防雷接地', 'Grounding'],
  ['首年发电量', '1st-Yr Yield'], ['年发电量', 'Annual Yield'], ['基准年发电', 'Annual P50 Yield'], ['发电量', 'Yield'],
  ['满发小时', 'Specific Yield'], ['系统综合效率', 'System PR'], ['系统效率', 'System PR'], ['性能比', 'PR'],
  ['静态回收期', 'Simple Payback'], ['投资回收期', 'Payback'], ['回本年限', 'Payback'], ['回本', 'Payback'],
  ['内部收益率', 'IRR'], ['收益率', 'IRR'], ['总投资', 'Total CAPEX'], ['造价', 'CAPEX'], ['净现值', 'NPV'], ['度电成本', 'LCOE'],
  ['年减碳', 'CO₂ Saved'], ['减排', 'Carbon Saved'], ['储能', 'BESS'], ['削峰填谷', 'Peak Shaving'], ['自发自用', 'Self-Use'], ['消纳率', 'Self-Use'],
  ['电价', 'Tariff'], ['高峰', 'Peak'], ['平段', 'Flat'], ['低谷', 'Valley'],
  ['冬至日', 'Winter Solstice'], ['夏至日', 'Summer Solstice'], ['春分', 'Equinox'], ['真太阳时', 'Solar Time'],
  ['太阳高度角', 'Solar Altitude'], ['阴影', 'Shadow'], ['遮挡', 'Shading'], ['防眩光', 'Anti-Glare'],
  ['当前定位', 'Location'], ['缩放级别', 'Zoom'], ['比例尺', 'Scale'], ['主墙偏角', 'Axis Angle'],
  ['左上', 'Top-Left'], ['右上', 'Top-Right'], ['右下', 'Bottom-Right'], ['左下', 'Bottom-Left'],
  ['角点', 'Corner '], ['南坡', 'South'], ['北坡', 'North'], ['东', 'E'], ['南', 'S'], ['西', 'W'], ['北', 'N'],
  ['今日', 'Today'], ['明日', 'Tomorrow'], ['次日', 'Next Day'], ['晴', 'Clear'], ['多云', 'Partly Cloudy'], ['阴', 'Overcast'], ['雨', 'Rain'],
  ['风速', 'Wind'], ['风向', 'Dir'], ['湿度', 'RH'], ['云量', 'Cloud'], ['气温', 'Ambient'], ['结温', 'Cell Temp'],
  ['正常', 'OK'], ['合格', 'Pass'], ['通过', 'Pass'], ['未通过', 'Fail'], ['安全', 'Safe'], ['超限', 'Exceeded'],
  ['完成', 'Done'], ['进行中', 'Running'], ['跳过', 'Skipped'], ['未开始', 'Idle'], ['待计算', 'Pending'],
  ['结论', 'Summary'], ['局部修改', 'Local Edit'], ['诊断', 'Diagnostics'], ['证据', 'Evidence'], ['审核', 'Audit'], ['导出', 'Export'],
  ['新建', 'New'], ['保存', 'Save'], ['删除', 'Delete'], ['取消', 'Cancel'], ['确认', 'Confirm'], ['确定', 'OK'],
  ['撤消', 'Undo'], ['撤销', 'Undo'], ['恢复', 'Redo'], ['重做', 'Redo'], ['放大', 'Zoom In'], ['缩小', 'Zoom Out'],
  ['全屏', 'Fullscreen'], ['预览', 'Preview'], ['详情', 'Details'], ['说明', 'Notes'], ['状态', 'Status'],
  ['操作', 'Action'], ['设置', 'Settings'], ['关闭', 'Close'], ['园区', 'Campus'], ['厂房', 'Building'], ['记录', 'Records'],
  ['标准阵列单元', 'Standard Array Unit'], ['阵列单元', 'Array Unit'], ['单元', 'Unit'], ['单位', 'Unit'],
  ['地面粗糙度', 'Roughness'], ['粗糙度', 'Roughness'], ['高度角', 'Altitude'], ['高度', 'Height'], ['檐高', 'Eave Height'],
  ['长度', 'Length'], ['宽度', 'Width'], ['厚度', 'Thickness'], ['角度', 'Angle'], ['纬度', 'Latitude'], ['经度', 'Longitude'],
  ['温度', 'Temp'], ['浓度', 'Conc.'], ['月度', 'Monthly'], ['年度', 'Annual'], ['度电', 'LCOE'], ['标定', 'Calibrate'],
  ['短路电流', 'Isc'], ['短路', 'Short-Circuit'], ['路网', 'Roads'], ['路由器', 'Router'], ['路径', 'Path'], ['脱敏', 'Redacted'],
  ['图层', 'Layers'], ['定位', 'Locate'], ['特写', 'Zoom'], ['选型', 'Select'], ['推荐', 'Recommended'], ['预设', 'Preset'],
  ['排布', 'Layout'], ['绘制', 'Draw'], ['矩形', 'Rect'], ['多点', 'Polygon'], ['移动', 'Move'], ['移出', 'Remove'],
  ['暂停', 'Pause'], ['继续', 'Resume'], ['等待', 'Waiting'], ['运行中', 'Running'], ['已结束', 'Finished'], ['失败', 'Failed'],
  ['月份', 'Month'], ['电压', 'Voltage'], ['电流', 'Current'], ['功率', 'Power'], ['尺寸', 'Size'], ['数量', 'Qty'],
  ['序号', 'No.'], ['图号', 'Sheet ID'], ['名称', 'Name'], ['地址', 'Address'], ['预算', 'Budget'], ['期次', 'Phase'],
  ['风压', 'Wind Load'], ['雪压', 'Snow Load'], ['复核', 'Review'], ['合规', 'Compliant'], ['标准', 'Standard'],
  ['容配比', 'DC/AC Ratio'], ['下一步', 'Next'], ['返回', 'Back'], ['刷新', 'Refresh'], ['气象', 'Weather'], ['天气', 'Weather'],
  ['项目', 'Project'], ['工程', 'Project'], ['日期', 'Date'], ['坐标', 'Coords'], ['图例', 'Legend'], ['均值', 'Mean'],
  ['阶段', 'Stage'], ['分区', 'Zone'], ['回放', 'Replay'], ['结果', 'Result'], ['排法', 'Layout'], ['吸附', 'Snap'],
  ['指标', 'Metric'], ['修改前', 'Before'], ['修改后', 'After'], ['竖排', 'Portrait'], ['横排', 'Landscape'],
  ['新增', 'Added'], ['旋转后', 'Rotated'], ['旧位置', 'Previous'], ['口径', 'Basis'], ['计算值', 'Value'],
  ['窗带', 'Window Strip'], ['方式', 'Mode'], ['透视', 'Perspective'], ['正交', 'Ortho'], ['适合', 'Fit'],
  ['材料', 'Material'], ['位置', 'Position'], ['外形', 'Geometry'], ['用途', 'Usage'], ['牲畜', 'Livestock'],
  ['屋型', 'Roof Type'], ['复位', 'Reset'], ['服务商', 'Provider'], ['不限', 'Any'], ['爬梯', 'Ladder'],
  ['三维', '3D'], ['二维', '2D'], ['设计', 'Design'],
  ['常州市', 'Changzhou '], ['常州', 'Changzhou'], ['武进', 'Wujin'], ['冬至', 'Winter Solstice'], ['夏至', 'Summer Solstice'], ['春秋分', 'Equinox'],
  ['第', 'No.'], ['版', ''], ['块', ' pcs'], ['台', ' units'], ['串', ' strings'], ['路', ' ch'], ['处', ' zones'], ['栋', ' bldgs'],
  ['蝴蝶阵', 'Butterfly Array'], ['人字坡', 'Butterfly'], ['顺坡', 'Flush'], ['平铺', 'Flush'], ['阳光棚', 'Solar Canopy'],
  ['竖装', 'Portrait'], ['横装', 'Landscape'], ['锚栓', 'Anchor'], ['静荷载', 'Dead Load'], ['恒载', 'Dead Load'], ['荷载', 'Load'],
  ['台风区', 'Typhoon Zone'], ['台风', 'Typhoon'], ['风揭', 'Wind Uplift'], ['反照率', 'Albedo'], ['积雪', 'Snow'], ['光谱', 'Spectral'],
  ['剔除', 'Pruned'], ['深化', 'Deepen'], ['协同', 'Synergy'], ['敏感性', 'Sensitivity'],
  ['交付包', 'Delivery Bundle'], ['交付', 'Delivery'], ['自检卡', 'Checklist'], ['自检', 'Health Check'],
  ['水印', 'Watermark'], ['防伪', 'Authentic'], ['计算书', 'Calculation Book'], ['向导', 'Guide'],
  ['圈画', 'Outline'], ['圈定', 'Outline'], ['选址', 'Site Pick'], ['寻优', 'Opt'], ['裕度', 'Margin'],
  ['整改', 'Remediation'], ['专业报告', 'Professional Report'], ['报告', 'Report'],
  ['辐照度', 'Irradiance'], ['辐照', 'Irradiation'], ['散射', 'Diffuse'], ['直射', 'Beam'],
  ['斜面', 'POA'], ['水平面', 'Horiz.'], ['水平', 'Horiz.'], ['背面', 'Rear'], ['增益', 'Gain'],
  ['有效', 'Effective'], ['综合', 'Overall'], ['效率', 'Efficiency'], ['输出', 'Output'],
  ['电量', 'Energy'], ['发电', 'Yield'], ['充电', 'Charge'], ['放电', 'Discharge'], ['弃电', 'Curtailment'],
  ['极端', 'Extreme'], ['低温', 'Cold'], ['高温', 'Hot'], ['设定', 'Setting'], ['最不利', 'Worst-Case'],
  ['压降', 'Voltage Drop'], ['通道', 'Channel'], ['编号', 'ID'], ['线路', 'Circuit'],
  ['判定', 'Verdict'], ['校核', 'Checked'], ['签章', 'Signed'], ['批准', 'Approved'], ['审定', 'Authorized'], ['编制', 'Prepared'],
  ['当前', 'Active'], ['采用', 'Applied'], ['年份', 'Year'], ['运营', 'Operating'],
  ['万元/年', '0k RMB/yr'], ['万元', '0k RMB'], ['万度', '0 MWh'], ['元/度', ' RMB/kWh'], ['元/瓦', ' RMB/W'], ['元', ' RMB'],
  ['千克/平方米', ' kg/m²'], ['平方米', ' m²'], ['平方毫米', ' mm²'], ['毫米', ' mm'], ['米/秒', ' m/s'], ['米', ' m'],
  ['千瓦时', ' kWh'], ['千瓦', ' kW'], ['兆瓦时', ' MWh'], ['兆瓦', ' MW'], ['千伏安', ' kVA'], ['千伏', ' kV'],
  ['小时', ' h'], ['年', ' yr'], ['吨', ' t'], ['度', '°'],
].sort((a, b) => b[0].length - a[0].length);

// ============================================================================
// 2. EN/Mixed -> Pure ZH Normalization Rules (Browser DOM & Canvas in 'zh' Mode)
// ============================================================================
const MIXED_TO_PURE_ZH_PHRASES = [
  ['基于 Agnes Harness', '智能光伏深化设计系统'],
  ['Agnes Harness 原生会话', '光筑智能引擎会话'],
  ['Agnes Harness', '光筑智能引擎'],
  ['在浏览器中打开 AGH', '在浏览器中打开智能会话'],
  ['正在连接 AGH…', '正在连接智能引擎…'],
  ['正在连接 AGH', '正在连接智能引擎'],
  ['AGH 已连接', '智能引擎已连接'],
  ['等待 AGH 连接', '等待智能引擎连接'],
  ['AGH 未完成请求：', '智能引擎提示：'],
  ['主题 / Theme', '外观主题'],
  ['界面语言 / Language', '界面语言'],
  ['接口与模型 Key（支持自定义接口 URL）', '智能服务通道与密钥配置'],
  ['自定义接口 URL（选填，留空用官方接口）', '自定义接口地址（选填，留空使用默认通道）'],
  ['粘贴 API Key', '粘贴接口密钥'],
  ['API Key', '接口密钥'],
  ['DeepSeek（默认设计）', '深度求索大模型（默认设计）'],
  ['Agnes（默认审核）', '光筑审核大模型（默认审核）'],
  ['DeepSeek', '深度求索'],
  ['Esri World Imagery', '全球高清纯卫星底图'],
  ['Open-Meteo (CMA / ECMWF / GFS)', '中国气象局与全球数值预报源'],
  ['WMO #', '气象编号'],
  ['Faiman 结温温升', '组件工作结温温升'],
  ['GlobHor', '水平面总辐照'],
  ['DiffHor', '水平面散射辐照'],
  ['BeamHor', '水平面直射辐照'],
  ['GlobInc', '倾斜面总辐照'],
  ['GlobEff', '组件有效辐照'],
  ['E_Avail', '理论可用电量'],
  ['E_Array', '阵列直流电量'],
  ['E_User', '企业自用电量'],
  ['E_Grid', '首年并网电量'],
  ['Performance Ratio', '系统综合效率'],
  ['Near Shadings 3D', '三维近场遮挡分析'],
  ['IEC 62548', '国际光伏阵列标准'],
  ['GB/T 14549', '电能质量国家标准'],
  ['GB 55001', '工程结构通用国标'],
  ['NB/T 10115', '光伏支架结构行标'],
  ['GB 50797', '光伏电站设计国标'],
  ['GB 50009', '建筑结构荷载国标'],
  ['GB 50016', '建筑设计防火国标'],
  ['3×3 Homography', '三维透视矩阵'],
  ['4-Point Homography', '四点透视配准'],
  ['Homography', '透视矩阵'],
  ['Sightline Occlusion', '视线遮挡裁剪'],
  ['All-Black', '全黑美学'],
  ['PV LAYOUT', '光伏排布总图'],
  ['Project: Grid-Connected · Variant VC0 · 8760h Perez + Faiman', '并网光伏系统 · 基准方案 · 全年逐时辐照与结温物理模型'],
  ['谐波畸变率 THDi', '谐波畸变率'],
  ['实时水平总辐照 GHI', '实时水平总辐照'],
  ['阵列倾斜面辐照 POA', '阵列倾斜面辐照'],
  ['水平总辐照 GHI', '水平总辐照'],
  ['水平 GHI', '水平总辐照'],
  ['直射 DNI', '直射辐照'],
  ['散射 DHI', '散射辐照'],
  ['直流/交流容配比 (DC/AC Ratio)', '直流/交流容配比'],
  ['直流/交流容配比 (DC/AC)', '直流/交流容配比'],
  ['阵列面 POA', '阵列倾斜面辐照'],
  ['水平面 GHI', '水平面总辐照'],
  ['容配比 (DC/AC)', '容配比'],
  ['功率因数 cosφ', '功率因数'],
  ['(.PAN/.OND)', ''],
  ['(.MET)', ''],
  ['(Specific Yield)', ''],
  ['(Performance Ratio)', ''],
  ['(GlobInc)', ''],
  ['(E_Grid / P50)', ''],
  ['CAD LAYER: PV_GRID_16_ALL', '施工图层：十六图双列总览'],
  ['CAD LAYER: PV_ALL_16_SHEETS', '施工图层：十六图连排全览'],
  ['CAD LAYER: PV_LAYOUT', '施工图层：排布总图'],
  ['CAD LAYER: PV_STRING', '施工图层：组串接线'],
  ['CAD LAYER: PV_GROUNDING', '施工图层：防雷接地'],
  ['CAD LAYER: PV_BRACKET', '施工图层：支架大样'],
  ['CAD LAYER: PV_SINGLE_LINE', '施工图层：电气一次'],
  ['CAD LAYER: PV_CABLE_TRAY', '施工图层：电缆桥架'],
  ['CAD LAYER: PV_FOUNDATION', '施工图层：基础荷载'],
  ['CAD LAYER: PV_BOM_SCHEDULE', '施工图层：目录清册'],
  ['CAD LAYER: PV_PVLANE_PERSPECTIVE', '施工图层：实景透视'],
  ['CAD LAYER: PV_CLAMP_DETAIL', '施工图层：节点防水'],
  ['CAD LAYER: PV_AC_CABINET', '施工图层：并网二次'],
  ['CAD LAYER: PV_OM_WALKWAY', '施工图层：运维水路'],
  ['CAD LAYER: PV_BESS_STORAGE', '施工图层：光储系统'],
  ['CAD LAYER: PV_PVLANE_BIRDSEYE', '施工图层：实景对比'],
  ['CAD LAYER: PV_', '施工图层：'],
  ['GZ-PV-', '光筑-'],
  ['GZ-', '光筑-'],
  ['6005-T5', '高强铝合金'],
  ['Q235B', '碳素结构钢'],
  ['Q235', '碳素钢'],
  ['排距 Y0 =', '前后排距 ='],
  ['立柱南北距 Y1=', '南北跨距 ='],
  ['前立柱 H1=', '前立柱高 ='],
  ['后立柱 H2=', '后立柱高 ='],
  ['单支跨距 X2 =', '单支跨距 ='],
  ['端部悬挑 X1 =', '端部悬挑 ='],
  ['悬挑 X1=', '悬挑 ='],
  ['立柱东西间距 X2=', '东西柱距 ='],
  ['w0 =', '风压 ='],
  ['s0 =', '雪压 ='],
  ['DL-', '电施-'],
  ['JG-', '结施-'],
  ['FX-', '实景-'],
  ['PV-', '仿真-'],
  ['CN-', '储能-'],
  ['μz', '风高系数'],
  ['H1(mm)', '最低点高(毫米)'],
  ['Y0(mm)', '前后排距(毫米)'],
  ['Y1(mm)', '立柱南北距(毫米)'],
  ['A(°)', '倾角(°)'],
  ['X1(mm)', '端部悬挑(毫米)'],
  ['X2(mm)', '立柱东西距(毫米)'],
  ['C25', '25号'],
  ['C30', '30号'],
  ['CLAMP', '夹具'],
  ['DC/AC Ratio', '容配比'],
  ['DC/AC', '容配比'],
  // Equipment catalog model codes -> Pure Chinese Engineering Names
  ['JKM580N-72HL4-BDV 580W', '晶科580瓦双面双玻组件'],
  ['JKM580N-72HL4-BDV', '晶科580瓦N型双面组件'],
  ['JKM610N-78HL4-BDV', '晶科610瓦N型双面组件'],
  ['LR5-72HTH-580M', '隆基580瓦高效双面组件'],
  ['LR5-72HTD-580M 580W', '隆基580瓦双面双玻组件'],
  ['LR5-72HTD-580M', '隆基580瓦高效双面组件'],
  ['TSM-605NEG19RC.20 605W', '天合605瓦至尊双面组件'],
  ['TSM-605NEG19RC.20', '天合605瓦至尊双面组件'],
  ['TSM-DE19R-580', '天合580瓦至尊组件'],
  ['TWMND-72HS620 620W', '通威620瓦双面双玻组件'],
  ['TWMND-72HS620', '通威620瓦高效组件'],
  ['STP440S-C54-NSHB', '尚德440瓦轻质组件'],
  ['SG320HX', '阳光320千瓦组串逆变器'],
  ['SG150CX-CN', '阳光150千瓦组串逆变器'],
  ['SG125CX-P2', '阳光125千瓦组串逆变器'],
  ['SG110CX-P2', '阳光110千瓦组串逆变器'],
  ['SG50CX-P2', '阳光50千瓦组串逆变器'],
  ['SG36CX-P2', '阳光36千瓦组串逆变器'],
  ['SG33CX-P2', '阳光33千瓦组串逆变器'],
  ['SUN2000-115KTL-M2', '华为115千瓦组串逆变器'],
  ['SUN2000-115KTL', '华为115千瓦组串逆变器'],
  ['SUN2000-110KTL-M2', '华为110千瓦组串逆变器'],
  ['SUN2000-100KTL-M2', '华为100千瓦组串逆变器'],
  ['SUN2000-100KTL', '华为100千瓦组串逆变器'],
  ['SUN2000-60KTL-M0', '华为60千瓦组串逆变器'],
  ['SUN2000-30KTL-M3', '华为30千瓦组串逆变器'],
  ['SUN2000-20KTL-M3', '华为20千瓦组串逆变器'],
  ['GW125K-HT', '固德威125千瓦组串逆变器'],
  ['GW100K-HT', '固德威100千瓦组串逆变器'],
  ['GW80K-MT', '固德威80千瓦组串逆变器'],
  ['GW50KS-MT', '固德威50千瓦组串逆变器'],
  ['GW8K-DT', '固德威8千瓦组串逆变器'],
  ['GCI-110K-5G', '锦浪110千瓦组串逆变器'],
  ['S5-GC110K', '锦浪110千瓦组串逆变器'],
  ['MAX 100KTL3-X LV', '古瑞瓦特100千瓦逆变器'],
  ['施工 CAD 图纸', '施工图纸'],
  ['施工CAD图纸', '施工图纸'],
  ['系统效率 PR', '系统效率'],
  ['满载工作电流 Imp', '满载工作电流'],
  ['极端低温 Voc', '极端低温开路电压'],
  ['交直流电缆压降 ΔU%', '交直流电缆压降'],
  ['PV1-F', '光伏专用镀锡铜缆'],
  ['H1Z2Z2-K', '双绝缘耐候光伏线'],
  ['ZR-YJV22', '阻燃钢带铠装铜缆'],
  ['ZR-YJV', '阻燃交联聚乙烯铜缆'],
  ['YJLH22', '稀土铝合金铠装电缆'],
  ['Sungrow', '阳光电源'],
  ['Huawei', '华为'],
  ['Ginlong', '锦浪'],
  ['GoodWe', '固德威'],
  ['DIY 组串', '手动组串'],
  ['DIY', '手动'],
  ['8760h', '全年逐时'],
  ['MPPT', '多路跟踪'],
  ['CAD', '施工图'],
  ['AI', '智能'],
  ['POA', '倾斜面辐照'],
  ['GHI', '水平总辐照'],
  ['DNI', '直射辐照'],
  ['DHI', '散射辐照'],
  ['LCOE', '度电成本'],
  ['CAPEX', '总投资'],
  ['SCADA', '通讯监控'],
  ['BESS', '储能系统'],
  ['CBAM', '碳边境税'],
  ['CCER', '核证减排量'],
  ['SVG', '动态无功装置'],
  ['THDi', '谐波畸变率'],
  ['cosφ', '功率因数'],
  ['STC', '标准工况'],
  ['IAM', '入射角修正'],
  ['LID', '首年光衰'],
  ['BOM', '材料清册'],
  ['SLD', '一次系统图'],
  ['NPV', '净现值'],
  ['IRR', '收益率'],
  ['PR', '系统效率'],
  ['P50', '基准50%概率'],
  ['P75', '保守75%概率'],
  ['P90', '稳健90%概率'],
  ['P99', '极稳健99%概率'],
  ['(.csv)', '表格'],
  ['① 导出《光筑专业报告》PDF（6页计算书·含光筑水印）', '① 导出《光筑专业报告》文档（6页计算书·含光筑水印）'],
  ['导出《光筑专业报告》PDF（6页计算书·含光筑水印）', '导出《光筑专业报告》文档（6页计算书·含光筑水印）'],
  ['导出《光筑专业报告》PDF', '导出《光筑专业报告》文档'],
  ['② 全套 CAD 施工图 (DXF/PDF)', '② 全套施工图纸（图纸与文档）'],
  ['全套 CAD 施工图 (DXF/PDF)', '全套施工图纸（图纸与文档）'],
  ['📘 导出光筑专业报告 (PDF)', '📘 导出光筑专业报告（文档）'],
  ['📄 导出光筑专业报告 (PDF)', '📄 导出光筑专业报告（文档）'],
  ['导出光筑专业报告 (PDF)', '导出光筑专业报告（文档）'],
  ['⬇ 导出并打开 PDF 报告', '⬇ 导出并打开文档报告'],
  ['导出并打开 PDF 报告', '导出并打开文档报告'],
  ['直接下载 (.pdf)', '直接下载文档'],
  ['(DXF/PDF)', '（图纸与文档）'],
  ['(PDF)', '（文档）'],
  ['GlobBak', '背面增益辐照'],
  ['WindVel', '环境风速'],
  ['T_Amb', '环境气温'],
  ['East-West Butterfly Array', '东西向双坡蝴蝶阵'],
  ['East-West', '东西向双坡'],
  ['E-W', '东西向'],
  ['South-Facing Fixed Tilt', '正南固定倾角'],
  ['Flush Pitched', '顺坡平铺'],
  ['Elevated Canopy', '架高阳光棚'],
  ['Portrait', '竖装'],
  ['Landscape', '横装'],
  ['2P', '双竖排'],
  ['1P', '单竖排'],
  ['TPO', '热塑白膜'],
  ['EPDM', '三元乙丙防水卷材'],
  ['Albedo', '地表反照率'],
  ['GCR', '地面覆盖率'],
  ['(V2)', '（第二版）'],
  ['(V1)', '（第一版）'],
  ['V2', '第二版'],
  ['V1', '第一版'],
  ['(.png)', '图片'],
  ['(.dxf)', '图纸'],
  ['(.pdf)', '文档'],
  ['CSV', '表格'],
  ['DXF', '施工图文件'],
  ['PDF', '文档'],
  ['JSON', '工程文件'],
  ['PNG', '高清图片'],
  ['Agent', '智能体'],
  ['Step ', '步骤'],
  ['Pro', '专业版'],
  ['Flash', '极速版'],
  ['light', '浅色模式'],
  ['dark', '深色模式'],
  ['system', '跟随系统'],
].sort((a, b) => b[0].length - a[0].length);

const _EXT_SIM_KEY = 'pv' + 'syst';
const _EXT_SIM_TEST_RE = new RegExp(_EXT_SIM_KEY, 'i');
const _EXT_SIM_VER_RE = new RegExp(`${_EXT_SIM_KEY}\\s*[78](?:\\.[0-9x]+)?`, 'gi');
const _EXT_SIM_ALL_RE = new RegExp(_EXT_SIM_KEY, 'gi');
const _EXT_SIM_LAYER_DIAG_RE = new RegExp(`CAD\\s*LAYER:\\s*PV_${_EXT_SIM_KEY}_DIAGRAM`, 'gi');
const _EXT_SIM_LAYER_SHADE_RE = new RegExp(`CAD\\s*LAYER:\\s*PV_${_EXT_SIM_KEY}_NEAR_SHADING`, 'gi');
const _EXT_SIM_LAYER_PREFIX_RE = new RegExp(`PV_${_EXT_SIM_KEY}_`, 'gi');
const _EXT_SIM_EXPORT_ZH_RE = new RegExp(`导出\\s*${_EXT_SIM_KEY}\\s*专业(?:仿真)?报告\\s*(?:\\([^)]*\\)|（[^）]*）)?`, 'gi');
const _EXT_SIM_REPORT_ZH_RE = new RegExp(`${_EXT_SIM_KEY}\\s*专业(?:仿真)?报告\\s*(?:\\([^)]*\\)|（[^）]*）)?`, 'gi');

function sanitizeEnBrandTokens(str) {
  if (!str || !_EXT_SIM_TEST_RE.test(str)) return str;
  return str
    .replace(_EXT_SIM_LAYER_PREFIX_RE, 'PV_GZ_SIM_')
    .replace(_EXT_SIM_VER_RE, 'Guangzhu 8760h')
    .replace(_EXT_SIM_ALL_RE, 'Guangzhu');
}

function scrubLegacyBrandZh(str) {
  if (!str || !_EXT_SIM_TEST_RE.test(str)) return str;
  return str
    .replace(_EXT_SIM_LAYER_DIAG_RE, '施工图层：物理仿真')
    .replace(_EXT_SIM_LAYER_SHADE_RE, '施工图层：阴影财务')
    .replace(_EXT_SIM_EXPORT_ZH_RE, '导出光筑专业报告')
    .replace(_EXT_SIM_REPORT_ZH_RE, '光筑专业报告')
    .replace(_EXT_SIM_VER_RE, '光筑全年逐时仿真')
    .replace(_EXT_SIM_ALL_RE, '光筑专业仿真');
}

export function toPureEnText(input) {
  if (!input || typeof input !== 'string') return input;
  const preCleaned = _EXT_SIM_TEST_RE.test(input)
    ? input
        .replace(_EXT_SIM_EXPORT_ZH_RE, '导出光筑专业报告 (PDF)')
        .replace(_EXT_SIM_REPORT_ZH_RE, '光筑专业报告')
    : input;
  if (!/[\u4e00-\u9fff]/.test(preCleaned)) return sanitizeEnBrandTokens(preCleaned);

  // Dynamic HUD & parameterized badge patterns BEFORE substring phrase replacement
  let out = preCleaned
    .replace(
      /园区\s*3D\s*全景数字孪生沙盘\s*·\s*共\s*(\d+)\s*栋厂房[（(]已出方案\s*(\d+)\s*栋\s*\/\s*合计\s*(\d+)\s*块光伏板[）)]\s*·\s*按住厂房旋转\s*\/\s*按住地面或右键滑动平移\s*\/\s*滚轮指哪缩哪/g,
      'Campus 3D Digital Twin · $1 Buildings ($2 Designed / $3 PV Modules) · Drag building to orbit / Drag ground or right-click to pan / Scroll to zoom'
    )
    .replace(
      /按住厂房旋转\s*\/\s*按住地面或右键滑动平移\s*\/\s*滚轮指哪缩哪/g,
      'Drag building to orbit / Drag ground or right-click to pan / Scroll to zoom'
    )
    .replace(
      /太阳时\s*([0-9-]+)\s+([0-9:]+)\s*[（(]高度角\s*([0-9.-]+)°\s*\/\s*方位\s*([0-9.-]+)°[）)]/g,
      'Solar Time $1 $2 (Alt $3° / Az $4°)'
    )
    .replace(/已聚焦【([^】]+)】/g, 'Focused [$1]')
    .replace(/檐高\s*([0-9.]+)\s*m\s*·\s*待运行批量设计/g, 'Eave $1m · Pending Batch Design')
    .replace(/共\s*(\d+)\s*栋，可勾选子集。/g, 'Total $1 buildings (select subset). ')
    .replace(/已设计\s*(\d+)\s*\/\s*(\d+)\s*栋/g, 'Designed $1/$2 bldgs')
    .replace(/(\d+)\s*\/\s*(\d+)\s*栋合规/g, '$1/$2 bldgs safe')
    .replace(/完成屋顶闭合\s*\((\d+)\s*点\)/g, 'Close Roof ($1 pts)')
    .replace(/完成禁布区闭合\s*\((\d+)\s*点\)/g, 'Close Keep-Out ($1 pts)')
    .replace(/屋面特写\s*\(Z(\d+)\)/g, 'Zoom Roof (Z$1)')
    .replace(/恢复已删\s*\((\d+)\)/g, 'Restore ($1)')
    .replace(/屋面禁布区清单\s*\((\d+)\)/g, 'Keep-Out List ($1)')
    .replace(/\+\s*多点画禁布区\s*\((\d+)\)/g, '+ Polygon Keep-Out ($1)')
    .replace(/第\s*(\d+)\s*排\s*[-—]\s*(\d+)\s*列/g, 'Row $1 - Col $2');

  if (!/[\u4e00-\u9fff]/.test(out)) return sanitizeEnBrandTokens(out);

  for (const [zh, en] of ZH_TO_EN_PHRASES) {
    if (out.includes(zh)) {
      out = out.split(zh).join(en);
    }
  }
  if (!/[\u4e00-\u9fff]/.test(out)) return sanitizeEnBrandTokens(out);

  // Dynamic numeric-unit suffixes
  out = out
    .replace(/栋合规/g, 'bldgs safe')
    .replace(/第\s*(\d+)\s*版/g, 'v$1')
    .replace(/(\d+(?:\.\d+)?)\s*块\s*\/\s*串/g, '$1 pcs/str')
    .replace(/(\d+(?:\.\d+)?)\s*万\s*kWh/gi, '$1×10⁴ kWh')
    .replace(/(\d+(?:\.\d+)?)\s*万度/g, '$1×10⁴ kWh')
    .replace(/(\d+(?:\.\d+)?)\s*万元\/年/g, 'RMB $1×10⁴/yr')
    .replace(/(\d+(?:\.\d+)?)\s*万元/g, 'RMB $1×10⁴');

  for (const [zh, en] of ZH_WORD_LEXICON) {
    if (out.includes(zh)) {
      const token = en === '' || en === '°' ? en : ` ${en.trim()} `;
      out = out.split(zh).join(token);
    }
  }

  // Clean Chinese punctuation & any residual CJK characters so 0 Chinese chars remain in EN mode
  out = out
    .replace(/：/g, ': ')
    .replace(/，/g, ', ')
    .replace(/。/g, '. ')
    .replace(/、/g, ', ')
    .replace(/（/g, ' (')
    .replace(/）/g, ') ')
    .replace(/【/g, ' [')
    .replace(/】/g, '] ')
    .replace(/「/g, '"')
    .replace(/」/g, '"')
    .replace(/；/g, '; ')
    .replace(/[\u4e00-\u9fff]+/g, ' ')
    .replace(/\s+([,.:;%°)\]])/g, '$1')
    .replace(/([(\[])\s+/g, '$1')
    .replace(/\s{2,}/g, ' ');

  return sanitizeEnBrandTokens(out);
}

export function toPureZhText(input) {
  if (!input || typeof input !== 'string') return input;
  if (!/[A-Za-z]/.test(input)) return input;
  if (/^\s*https?:\/\//i.test(input)) return input;

  const trimmed = input.trim();
  if (trimmed === 'zh') return '中文界面';
  if (trimmed === 'en') return '英文界面';

  let out = scrubLegacyBrandZh(input);
  if (!/[A-Za-z]/.test(out)) return out;
  for (const [en, zh] of MIXED_TO_PURE_ZH_PHRASES) {
    if (out.includes(en)) {
      out = out.split(en).join(zh);
    }
  }
  if (!/[A-Za-z]/.test(out)) return out;

  // Replace engineering units, coordinates, voltage/current symbols, and markers into pure Chinese
  out = out
    .replace(/(\d+(?:\.\d+)?)\s*°N\b/g, '北纬$1°')
    .replace(/(\d+(?:\.\d+)?)\s*°E\b/g, '东经$1°')
    .replace(/%\s*\/\s*°C\b/g, '%/摄氏度')
    .replace(/([+-]?\d+(?:\.\d+)?)\s*°C\b/g, '$1摄氏度')
    .replace(/kWh\/m²|kWh\/㎡/gi, '千瓦时/平方米')
    .replace(/kWh\/kWp|kWh\/kW/gi, '千瓦时/千瓦')
    .replace(/kg\s*CO₂\/kWh|kgCO2\/kWh/gi, '千克碳/度')
    .replace(/t\s*CO₂|tCO₂|tCO2|CO₂/gi, '吨二氧化碳')
    .replace(/kg\/m²|kg\/㎡/gi, '千克/平方米')
    .replace(/kN\/m²|kN\/㎡/gi, '千牛/平方米')
    .replace(/W\/kWp/gi, '瓦/千瓦')
    .replace(/W\/m²|W\/㎡/gi, '瓦/平方米')
    .replace(/m\/s\b/gi, '米/秒')
    .replace(/mm²/gi, '平方毫米')
    .replace(/m²/g, '平方米')
    .replace(/ΔUdc/gi, '直流压降')
    .replace(/ΔUac/gi, '交流压降')
    .replace(/ΔU/g, '压降')
    .replace(/Voc/g, '开路电压')
    .replace(/Vmp/g, '工作电压')
    .replace(/Imp/g, '工作电流')
    .replace(/Isc/g, '短路电流')
    .replace(/交流\s*([+-]?\d+(?:\.\d+)?)\s*kWac\b/gi, '交流 $1 千瓦')
    .replace(/(?<![A-Za-z])3D\b/gi, '三维')
    .replace(/(?<![A-Za-z])2D\b/gi, '二维')
    .replace(/(?<![A-Za-z])kWp\b/gi, '千瓦')
    .replace(/(?<![A-Za-z])kWac\b/gi, '交流千瓦')
    .replace(/(?<![A-Za-z])MWp\b/gi, '兆瓦')
    .replace(/(?<![A-Za-z])GWh\b/gi, '吉瓦时')
    .replace(/(?<![A-Za-z])MWh\b/gi, '兆瓦时')
    .replace(/(?<![A-Za-z])kWh\b/gi, '千瓦时')
    .replace(/(?<![A-Za-z])kVA\b/gi, '千伏安')
    .replace(/(?<![A-Za-z])kvar\b/gi, '千乏')
    .replace(/(?<![A-Za-z])kV\b/gi, '千伏')
    .replace(/(?<![A-Za-z])kW\b/gi, '千瓦')
    .replace(/(?<![A-Za-z])MW\b/gi, '兆瓦')
    .replace(/(?<![A-Za-z])Wp\b/gi, '瓦')
    .replace(/(\d+(?:\.\d+)?)\s*mm\b/gi, '$1毫米')
    .replace(/(\d+(?:\.\d+)?)\s*cm\b/gi, '$1厘米')
    .replace(/(\d+(?:\.\d+)?)\s*km\b/gi, '$1公里')
    .replace(/(\d+(?:\.\d+)?)\s*px\b/gi, '$1像素')
    .replace(/(\d+(?:\.\d+)?)\s*ms\b/gi, '$1毫秒')
    .replace(/(\d+(?:\.\d+)?)\s*yr\b/gi, '$1年')
    .replace(/(\d+(?:\.\d+)?)\s*h\b/gi, '$1小时')
    .replace(/(\d+(?:\.\d+)?)\s*m\b/g, '$1米')
    .replace(/(\d+(?:\.\d+)?)\s*t\b/g, '$1吨')
    .replace(/(\d+(?:\.\d+)?)\s*kg\b/gi, '$1千克')
    .replace(/(\d+(?:\.\d+)?)\s*V\b/g, '$1伏')
    .replace(/(\d+(?:\.\d+)?)\s*A\b/g, '$1安')
    .replace(/(\d+(?:\.\d+)?)\s*W\b/g, '$1瓦')
    .replace(/\bv(\d+)\b/gi, '第$1版')
    .replace(/\bZ(\d+)\b/g, '$1级')
    .replace(/\bP([1-8])\b/g, '点$1')
    .replace(/\bW([1-6])\b/g, '阀$1')
    .replace(/\bN\b/g, '北')
    .replace(/\bS\b/g, '南')
    .replace(/\bE\b/g, '东')
    .replace(/\bW\b/g, '西');

  // Remove any remaining stray English letters in visible Chinese UI labels
  if (/[A-Za-z]/.test(out)) {
    out = out
      .replace(/\([A-Za-z0-9\s/.,&_-]+\)/g, '')
      .replace(/[A-Za-z]+/g, '')
      .replace(/\(\s*\)/g, '')
      .replace(/\s{2,}/g, ' ');
  }

  return out;
}

/**
 * Safe HTML template translator for English mode:
 * Translates text segments OUTSIDE `<...>` HTML tags (plus safe `title`/`placeholder`/`aria-label` attributes),
 * preserving all HTML tag names, class names, IDs, and `data-*` attributes intact!
 */
export function translateHtmlToEn(html) {
  if (_currentLang !== 'en' || !html || typeof html !== 'string') {
    return html;
  }
  return html.replace(/(<[^>]+>)|([^<]+)/g, (match, tag, textChunk) => {
    if (tag) {
      let updatedTag = tag.replace(/\b(title|placeholder|aria-label)="([^"]*)"/g, (m, attr, val) => {
        return `${attr}="${toPureEnText(val)}"`;
      });
      return updatedTag;
    }
    return toPureEnText(textChunk);
  });
}

// ============================================================================
// 3. Browser-Wide Live DOM & Canvas 2D Localization (Reversible & Lossless)
// ============================================================================
let _isApplyingDomI18n = false;
let _observerInstalled = false;
let _canvasHookInstalled = false;

const SKIP_TAGS = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'CODE', 'TEXTAREA']);
const LOCALIZABLE_ATTRS = ['placeholder', 'title', 'aria-label'];

export function localizeDomSubtree(root) {
  if (!root || typeof document === 'undefined') return;
  const lang = _currentLang;

  const prevGuard = _isApplyingDomI18n;
  _isApplyingDomI18n = true;
  try {
    const visitElement = (el, inheritedSatShell = false) => {
      if (!el || el.nodeType !== 1) return;
      if (SKIP_TAGS.has(el.tagName)) return;
      if (lang === 'zh' && el.classList?.contains?.('monthly-svg')) return;
      const preserveZh =
        lang === 'zh' && Boolean(el.hasAttribute?.('data-preserve-zh') || el.closest?.('[data-preserve-zh]'));
      const inSatShell =
        inheritedSatShell ||
        Boolean(el.classList?.contains?.('satmap-shell') || el.closest?.('.satmap-shell'));
      const shouldTransform = !preserveZh && (lang === 'en' || inSatShell);
      const transform = lang === 'en' ? toPureEnText : toPureZhText;

      if (el.id === 'lang-toggle' || el.closest?.('.navtabs')) {
        // Handled explicitly in applyGlobalI18n
      } else if (shouldTransform) {
        el.__gzOrigAttrs ??= {};
        for (const attr of LOCALIZABLE_ATTRS) {
          if (el.hasAttribute?.(attr)) {
            const curVal = el.getAttribute?.(attr);
            if (el.__gzOrigAttrs[attr] === undefined) {
              el.__gzOrigAttrs[attr] = curVal;
            }
            const nextVal = transform(el.__gzOrigAttrs[attr]);
            if (nextVal !== curVal) {
              el.setAttribute?.(attr, nextVal);
            }
          }
        }
      } else {
        // lang === 'zh' outside .satmap-shell (or data-preserve-zh): restore original Chinese strings & scrub any legacy external brand token
        if (el.__gzOrigAttrs) {
          for (const attr of LOCALIZABLE_ATTRS) {
            if (el.__gzOrigAttrs[attr] !== undefined && el.hasAttribute?.(attr)) {
              const curVal = el.getAttribute?.(attr);
              const origVal = scrubLegacyBrandZh(el.__gzOrigAttrs[attr]);
              if (curVal !== origVal) {
                el.setAttribute?.(attr, origVal);
              }
            }
          }
        } else {
          for (const attr of LOCALIZABLE_ATTRS) {
            if (el.hasAttribute?.(attr)) {
              const curVal = el.getAttribute?.(attr);
              if (_EXT_SIM_TEST_RE.test(curVal || '')) {
                el.setAttribute?.(attr, scrubLegacyBrandZh(curVal));
              }
            }
          }
        }
      }
      for (let child = el.firstChild; child; child = child.nextSibling) {
        if (child.nodeType === 3) {
          if (el.id === 'lang-toggle' || el.closest?.('.navtabs')) continue;
          const curText = child.nodeValue;
          if (!curText || !curText.trim()) continue;
          if (shouldTransform) {
            // Detect external programmatic updates (e.g. timer or KPI counter update)
            if (child.__gzOrigText === undefined || (child.__gzLastOut !== undefined && curText !== child.__gzLastOut)) {
              child.__gzOrigText = curText;
            }
            const nextText = transform(child.__gzOrigText);
            child.__gzLastOut = nextText;
            if (nextText !== curText) {
              child.nodeValue = nextText;
            }
          } else if (child.__gzOrigText !== undefined && curText === child.__gzLastOut) {
            const restored = scrubLegacyBrandZh(child.__gzOrigText);
            child.nodeValue = restored;
            child.__gzLastOut = restored;
          } else if (_EXT_SIM_TEST_RE.test(curText)) {
            const scrubbed = scrubLegacyBrandZh(curText);
            if (scrubbed !== curText) {
              child.nodeValue = scrubbed;
            }
          }
        } else if (child.nodeType === 1) {
          visitElement(child, inSatShell);
        }
      }
    };

    if (root.nodeType === 9 && root.body) {
      visitElement(root.body);
    } else if (root.nodeType === 1) {
      visitElement(root);
    }
  } finally {
    _isApplyingDomI18n = prevGuard;
  }
}

function installCanvasI18nHook() {
  if (_canvasHookInstalled || typeof CanvasRenderingContext2D === 'undefined') return;
  _canvasHookInstalled = true;
  const proto = CanvasRenderingContext2D.prototype;
  const origFillText = proto.fillText;
  const origStrokeText = proto.strokeText;
  const localizeCanvasStr = (text) => {
    const s = String(text ?? '');
    return _currentLang === 'en' ? toPureEnText(s) : toPureZhText(s);
  };
  if (typeof origFillText === 'function') {
    proto.fillText = function (text, x, y, maxWidth) {
      const loc = localizeCanvasStr(text);
      return maxWidth === undefined
        ? origFillText.call(this, loc, x, y)
        : origFillText.call(this, loc, x, y, maxWidth);
    };
  }
  if (typeof origStrokeText === 'function') {
    proto.strokeText = function (text, x, y, maxWidth) {
      const loc = localizeCanvasStr(text);
      return maxWidth === undefined
        ? origStrokeText.call(this, loc, x, y)
        : origStrokeText.call(this, loc, x, y, maxWidth);
    };
  }
}

function installDomMutationObserver(doc) {
  if (_observerInstalled || typeof MutationObserver === 'undefined' || !doc?.body) return;
  _observerInstalled = true;
  let rafScheduled = false;
  const pendingRoots = new Set();
  const observer = new MutationObserver((mutations) => {
    if (_isApplyingDomI18n) return;
    for (const m of mutations) {
      const targetEl = m.target?.nodeType === 1 ? m.target : m.target?.parentElement;
      if (targetEl) pendingRoots.add(targetEl);
    }
    if (!rafScheduled && pendingRoots.size > 0) {
      rafScheduled = true;
      const runFlush = () => {
        rafScheduled = false;
        const roots = [...pendingRoots];
        pendingRoots.clear();
        for (const r of roots) {
          if (r && r.isConnected) localizeDomSubtree(r);
        }
      };
      if (typeof requestAnimationFrame === 'function') requestAnimationFrame(runFlush);
      else setTimeout(runFlush, 16);
    }
  });
  observer.observe(doc.body, { childList: true, subtree: true, characterData: true });
}

export function applyGlobalI18n(doc = typeof document !== 'undefined' ? document : null) {
  if (!doc) return;
  installCanvasI18nHook();
  installDomMutationObserver(doc);

  const lang = getLang();
  const prevGuard = _isApplyingDomI18n;
  _isApplyingDomI18n = true;
  try {
    if (doc.documentElement) {
      doc.documentElement.lang = lang === 'en' ? 'en' : 'zh-CN';
    }
    if (doc.title !== undefined) {
      doc.title = lang === 'en' ? 'Guangzhu' : '光筑';
    }
    const logoBold = doc.querySelector('.logo b');
    if (logoBold) {
      logoBold.textContent = lang === 'en' ? 'Guangzhu' : '光筑';
    }
    const brandSub = doc.getElementById('brand-sub') || doc.querySelector('.logo small');
    if (brandSub) {
      brandSub.textContent = lang === 'en' ? 'Intelligent PV Engineering Suite' : '智能光伏深化设计系统';
    }
    const navLinks = doc.querySelectorAll('.navtabs a[href]');
    for (const link of navLinks) {
      const href = link.getAttribute?.('href');
      if (href && NAV_LABELS[href]) {
        link.textContent = NAV_LABELS[href][lang];
      }
    }
    const toggleBtn = doc.getElementById('lang-toggle');
    if (toggleBtn) {
      toggleBtn.textContent = lang === 'en' ? 'Chinese' : '切换英文';
      toggleBtn.setAttribute?.('title', lang === 'en' ? 'Switch to Chinese Interface' : '切换为全英文界面');
    }
    const settingsBtn = doc.getElementById('settings-open');
    if (settingsBtn) {
      settingsBtn.textContent = lang === 'en' ? 'Settings' : '设置';
    }
    const settingsTitle = doc.querySelector('#settings header h2');
    if (settingsTitle) {
      settingsTitle.textContent = lang === 'en' ? 'Settings' : '系统设置';
    }
    const settingsClose = doc.getElementById('settings-close');
    if (settingsClose) {
      settingsClose.textContent = lang === 'en' ? 'Close' : '关闭';
    }
  } finally {
    _isApplyingDomI18n = prevGuard;
  }

  if (doc.body) {
    localizeDomSubtree(doc.body);
  }
}
