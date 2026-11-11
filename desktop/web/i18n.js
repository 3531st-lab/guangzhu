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

  // 5 Workflow Steps in Satellite Workbench
  ['真实卫星定位 · 实时气象寻优 · 智能配串 · 全套施工图', 'Live Satellite Imagery · Meteorological Tilt · Smart MPPT · 16-Sheet CAD'],
  ['1. 卫星底图与排布设计', '1. Satellite Base & Array Layout'],
  ['2. 电气设计与MPPT配串', '2. Electrical & MPPT Stringing'],
  ['3. 8760h 物理仿真与实时气象', '3. 8760h Physics & Live Weather'],
  ['4. 实景透视效果图', '4. Oblique Perspective Studio'],
  ['5. 施工 CAD 图纸生成', '5. 16-Sheet CAD Drawings'],
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
  ['第', 'No.'], ['版', ''], ['块', ' pcs'], ['台', ' units'], ['串', ' strings'], ['路', ' ch'], ['处', ' zones'], ['栋', ' bldgs'],
  ['万元/年', '0k RMB/yr'], ['万元', '0k RMB'], ['万度', '0 MWh'], ['元/度', ' RMB/kWh'], ['元/瓦', ' RMB/W'], ['元', ' RMB'],
  ['平方米', ' m²'], ['平方毫米', ' mm²'], ['毫米', ' mm'], ['米/秒', ' m/s'], ['米', ' m'],
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
  ['CAD LAYER: PV_PVSYST_DIAGRAM', '施工图层：物理仿真'],
  ['CAD LAYER: PV_CLAMP_DETAIL', '施工图层：节点防水'],
  ['CAD LAYER: PV_AC_CABINET', '施工图层：并网二次'],
  ['CAD LAYER: PV_OM_WALKWAY', '施工图层：运维水路'],
  ['CAD LAYER: PV_BESS_STORAGE', '施工图层：光储系统'],
  ['CAD LAYER: PV_PVLANE_BIRDSEYE', '施工图层：实景对比'],
  ['CAD LAYER: PV_PVSYST_NEAR_SHADING', '施工图层：阴影财务'],
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

export function toPureEnText(input) {
  if (!input || typeof input !== 'string') return input;
  if (!/[\u4e00-\u9fff]/.test(input)) return input;

  let out = input;
  for (const [zh, en] of ZH_TO_EN_PHRASES) {
    if (out.includes(zh)) {
      out = out.split(zh).join(en);
    }
  }
  if (!/[\u4e00-\u9fff]/.test(out)) return out;

  // Dynamic numeric-unit patterns
  out = out
    .replace(/第\s*(\d+)\s*排\s*[-—]\s*(\d+)\s*列/g, 'Row $1 - Col $2')
    .replace(/第\s*(\d+)\s*版/g, 'v$1')
    .replace(/(\d+(?:\.\d+)?)\s*块\s*\/\s*串/g, '$1 pcs/str')
    .replace(/(\d+(?:\.\d+)?)\s*万\s*kWh/gi, '$1×10⁴ kWh')
    .replace(/(\d+(?:\.\d+)?)\s*万度/g, '$1×10⁴ kWh')
    .replace(/(\d+(?:\.\d+)?)\s*万元\/年/g, 'RMB $1×10⁴/yr')
    .replace(/(\d+(?:\.\d+)?)\s*万元/g, 'RMB $1×10⁴');

  for (const [zh, en] of ZH_WORD_LEXICON) {
    if (out.includes(zh)) {
      out = out.split(zh).join(en);
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
    .replace(/「/g, '"')
    .replace(/」/g, '"')
    .replace(/；/g, '; ')
    .replace(/[\u4e00-\u9fff]+/g, ' ')
    .replace(/\s{2,}/g, ' ');

  return out;
}

export function toPureZhText(input) {
  if (!input || typeof input !== 'string') return input;
  if (!/[A-Za-z]/.test(input)) return input;
  if (/^\s*https?:\/\//i.test(input)) return input;

  const trimmed = input.trim();
  if (trimmed === 'zh') return '中文界面';
  if (trimmed === 'en') return '英文界面';

  let out = input;
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
      const inSatShell =
        inheritedSatShell ||
        Boolean(el.classList?.contains?.('satmap-shell') || el.closest?.('.satmap-shell'));
      const shouldTransform = lang === 'en' || inSatShell;
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
        // lang === 'zh' outside .satmap-shell: restore original Chinese strings if previously localized to 'en'
        if (el.__gzOrigAttrs) {
          for (const attr of LOCALIZABLE_ATTRS) {
            if (el.__gzOrigAttrs[attr] !== undefined && el.hasAttribute?.(attr)) {
              const curVal = el.getAttribute?.(attr);
              const origVal = el.__gzOrigAttrs[attr];
              if (curVal !== origVal) {
                el.setAttribute?.(attr, origVal);
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
            child.nodeValue = child.__gzOrigText;
            child.__gzLastOut = child.__gzOrigText;
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
