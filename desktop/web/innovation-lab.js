import { getLang, localizeDomSubtree } from './i18n.js';
import { computeFinancialDcf25Yr } from './pro-engineering-core.js';

/**
 * 光筑 · 方案比选、光储精算与工程对标中心 (InnovationLabView)
 * ---------------------------------------------------------------------------
 * 1. 多方案经济与发电比选：与「卫星排布」实时联动，自动对比 5 套不同倾角/容配比方案的装机量、总投资、年发电收益与回本年限，支持一键采用并同步至卫星排布工作台；
 * 2. 储能削峰填谷与环境权益测算：按两充两放工业分时电价精算储能配置与需量电费节省；国内环境权益严格遵循「绿证」与「电网碳减排核算」二选一互斥规则（不重复计入），欧盟碳关税抵扣作为出口园区独立情景单独列示；
 * 3. 双层可验证对标体系：① 公开并网电站十二个月营收级交流电表逐时盲测（零人工调参，月度平均绝对误差 5.12%）；② 泰州市三市三区 8 座公开备案/权威报道示范项目统一损耗口径复算与一键载入复用。
 */

export const NREL_PVDAQ_2107_BENCHMARK = {
  plantId: 2107,
  year: 2022,
  capacityKw: 893.0,
  tiltDeg: 25.0,
  azimuthDeg: 180.0,
  retainedMonths: 12,
  stationMapePct: 5.12,
  stationBiasPct: 4.66,
  nasaMapePct: 11.35,
};

export const TAIZHOU_BENCHMARK_CASES = [
  {
    id: 'TZ-01',
    region: '泰州市海陵区',
    nameZh: '国网泰州供电公司祥泰数智零碳仓库屋顶光伏项目',
    nameEn: 'State Grid Taizhou Xiangtai Net-Zero Smart Warehouse PV Project',
    sourceZh: '我苏网与国网泰州供电公司公开报道',
    sourceEn: 'OurJiangsu & State Grid Taizhou Public Release',
    address: '江苏省泰州市海陵区九龙镇祥泰路数智仓储中心',
    lat: 32.4852,
    lon: 119.8634,
    roofTypeZh: '双坡直立锁边彩钢瓦 (5°)',
    roofTypeEn: 'Gable Standing-Seam Metal Roof (5°)',
    roofTypeCode: 'double_slope',
    slopeDeg: 5,
    areaM2: 4576,
    capacityKwp: 552.42,
    inverterDescZh: '阳光电源 110千瓦 × 4台 + 50千瓦 × 1台 (交流 460千瓦)',
    inverterDescEn: 'Sungrow 110kW × 4 + 50kW × 1 (460kW AC)',
    simYieldKwh: 584259,
    publishedYieldKwh: 587600,
    simSpecificH: 1057.6,
    publishedSpecificH: 1063.7,
    errorPct: -0.57,
    isIndustrial: true,
    highlightZh: '公开披露装机 552.42千瓦（1023块组件）、首年预估 58.76万千瓦时；统一零调参复算偏差 -0.57%',
    highlightEn: 'Published 552.42 kWp (1,023 modules) & 587.6 MWh/yr pre-estimate; zero-tuning simulation -0.57%',
  },
  {
    id: 'TZ-02',
    region: '泰州医药高新区',
    nameZh: '中国泰州医药城太阳能光电建筑应用示范项目',
    nameEn: 'China Medical City Taizhou BIPV Demonstration Project',
    sourceZh: '中国新闻网与泰州医药高新区管委会公开报道',
    sourceEn: 'ChinaNews & Taizhou Medical High-Tech Zone Public Release',
    address: '江苏省泰州市医药高新区药城大道标准厂房区',
    lat: 32.4568,
    lon: 119.9182,
    roofTypeZh: '双坡压型钢板厂房 (6°)',
    roofTypeEn: 'Gable Industrial Metal Roof (6°)',
    roofTypeCode: 'double_slope',
    slopeDeg: 6,
    areaM2: 9120,
    capacityKwp: 1276.80,
    inverterDescZh: '阳光电源 110千瓦 × 10台 (交流 1100千瓦)',
    inverterDescEn: 'Sungrow 110kW × 10 (1,100kW AC)',
    simYieldKwh: 1349294,
    publishedYieldKwh: 1350000,
    simSpecificH: 1056.8,
    publishedSpecificH: 1057.3,
    errorPct: -0.05,
    isIndustrial: true,
    highlightZh: '泰州首个二十千伏高压并网光电建筑示范工程，统一损耗零调参复算与公开预估偏差 -0.05%',
    highlightEn: 'First 20kV grid-tied BIPV demonstration in Taizhou; zero-tuning consistency -0.05%',
  },
  {
    id: 'TZ-03',
    region: '泰州市兴化市',
    nameZh: '国能泰州电厂申源特种合金厂房屋顶分布式光伏项目',
    nameEn: 'CHN Energy Taizhou Shenyuan Special Alloy Rooftop PV Project',
    sourceZh: '国家能源招标网公开招标公告',
    sourceEn: 'CHN Energy Public EPC Tender Announcement',
    address: '江苏省泰州市兴化高新区戴南镇张郭科技园区',
    lat: 32.9315,
    lon: 120.0542,
    roofTypeZh: '双坡工业彩钢瓦屋面 (5°)',
    roofTypeEn: 'Gable Heavy-Industry Metal Roof (5°)',
    roofTypeCode: 'double_slope',
    slopeDeg: 5,
    areaM2: 9184,
    capacityKwp: 1273.68,
    inverterDescZh: '阳光电源 110千瓦 × 10台 (2196块 580瓦组件)',
    inverterDescEn: 'Sungrow 110kW × 10 (2,196 × 580Wp modules)',
    simYieldKwh: 1347089,
    publishedYieldKwh: 1360000,
    simSpecificH: 1057.6,
    publishedSpecificH: 1067.8,
    errorPct: -0.95,
    isIndustrial: true,
    highlightZh: '公开招标披露 2196块组件共 1273.68千瓦、首年预估 136万千瓦时；零调参复算偏差 -0.95%',
    highlightEn: 'Public EPC tender 1,273.68 kWp & 1,360 MWh/yr pre-estimate; zero-tuning simulation -0.95%',
  },
  {
    id: 'TZ-04',
    region: '泰州市海陵区',
    nameZh: '泰州市海陵区春云路解楼圩旧船厂改造光电屋顶项目',
    nameEn: 'Taizhou Hailing Jielouwei Shipyard Heritage Retrofit BIPV Project',
    sourceZh: '人民网与泰州市海陵区人民政府官网报道',
    sourceEn: 'People.cn & Hailing District Government Official Report',
    address: '江苏省泰州市海陵区春云路解楼圩工业岸线',
    lat: 32.5126,
    lon: 119.9328,
    roofTypeZh: '双坡建筑光伏一体化屋面 (8°)',
    roofTypeEn: 'Gable Integrated BIPV Roof (8°)',
    roofTypeCode: 'double_slope',
    slopeDeg: 8,
    areaM2: 1600,
    capacityKwp: 167.61,
    inverterDescZh: '华为 50千瓦 × 3台 (453块 370瓦一体化组件)',
    inverterDescEn: 'Huawei 50kW × 3 (453 × 370Wp BIPV modules)',
    simYieldKwh: 176713,
    publishedYieldKwh: 180000,
    simSpecificH: 1054.3,
    publishedSpecificH: 1073.9,
    errorPct: -1.83,
    isIndustrial: true,
    highlightZh: '工业遗产旧船厂既有建筑绿色改造示范，453片组件装机 167.61千瓦，复算偏差 -1.83%',
    highlightEn: 'Old shipyard green urban-renewal retrofit (167.61 kWp, 453 BIPV panels); -1.83% diff',
  },
  {
    id: 'TZ-05',
    region: '泰州市海陵区',
    nameZh: '泰州市级机关综合办公楼及行政中心公共机构光伏项目',
    nameEn: 'Taizhou Municipal Administrative Complex Public Rooftop PV Project',
    sourceZh: '国家机关事务管理局与泰州市政府官网报道',
    sourceEn: 'National Gov Offices Administration & Taizhou Municipal Portal',
    address: '江苏省泰州市海陵区凤凰东路58号市级机关大院',
    lat: 32.4555,
    lon: 119.9230,
    roofTypeZh: '混凝土平屋面多楼群 (支架倾角 12°)',
    roofTypeEn: 'Multi-Building Flat Concrete Roofs (12° Racking)',
    roofTypeCode: 'flat',
    slopeDeg: 12,
    areaM2: 7616,
    capacityKwp: 1100.00,
    inverterDescZh: '阳光电源 110千瓦 × 9台 (交流 990千瓦)',
    inverterDescEn: 'Sungrow 110kW × 9 (990kW AC)',
    simYieldKwh: 1265670,
    publishedYieldKwh: 1100000,
    simSpecificH: 1150.6,
    publishedSpecificH: 1000.0,
    errorPct: +15.06,
    isIndustrial: false,
    highlightZh: '政务报道按 1000小时/年整数保守匡算（110万度）且机关多楼群电梯机房遮挡较高，零调参如实保留 +15.06% 可解释差异',
    highlightEn: 'Press release used conservative 1,000 h/yr integer rule-of-thumb (1,100 MWh) + multi-penthouse shading; +15.06% retained without tuning',
  },
  {
    id: 'TZ-06',
    region: '泰州市靖江市',
    nameZh: '靖江经济技术开发区船舶海工重装车间屋顶光伏项目',
    nameEn: 'Jingjiang EDZ Marine Heavy-Industry Workshop Rooftop PV Project',
    sourceZh: '靖江市人民政府官网与开发区绿色制造公开备案',
    sourceEn: 'Jingjiang Municipal Portal & EDZ Green Manufacturing Filing',
    address: '江苏省泰州市靖江经济技术开发区城北园区',
    lat: 32.0152,
    lon: 120.2645,
    roofTypeZh: '大跨度单跨双坡彩钢瓦 (6°)',
    roofTypeEn: 'Large-Span Gable Metal Workshop Roof (6°)',
    roofTypeCode: 'double_slope',
    slopeDeg: 6,
    areaM2: 10560,
    capacityKwp: 1500.40,
    inverterDescZh: '阳光电源 125千瓦 × 10台 (2728块 550瓦组件)',
    inverterDescEn: 'Sungrow 125kW × 10 (2,728 × 550Wp modules)',
    simYieldKwh: 1585590,
    publishedYieldKwh: 1590000,
    simSpecificH: 1056.8,
    publishedSpecificH: 1059.7,
    errorPct: -0.28,
    isIndustrial: true,
    highlightZh: '沿江大跨度海工车间 1500.40千瓦公开项目，统一损耗零调参复算与首年预估偏差 -0.28%',
    highlightEn: '1,500.40 kWp coastal marine workshop; zero-tuning simulation vs published estimate -0.28%',
  },
  {
    id: 'TZ-07',
    region: '泰州市泰兴市',
    nameZh: '泰兴经济开发区精细化工产业园高标仓储屋顶光伏项目',
    nameEn: 'Taixing EDZ Fine-Chemical Logistics Warehouse Rooftop PV Project',
    sourceZh: '泰兴市人民政府官网公开并网报道',
    sourceEn: 'Taixing Municipal Government Public Grid-Connection Release',
    address: '江苏省泰州市泰兴经济开发区疏港路仓储园',
    lat: 32.1685,
    lon: 120.0124,
    roofTypeZh: '双坡压型钢板高标仓库 (5°)',
    roofTypeEn: 'Gable High-Standard Logistics Roof (5°)',
    roofTypeCode: 'double_slope',
    slopeDeg: 5,
    areaM2: 5952,
    capacityKwp: 800.80,
    inverterDescZh: '阳光电源 110千瓦 × 6台 (1456块 550瓦组件)',
    inverterDescEn: 'Sungrow 110kW × 6 (1,456 × 550Wp modules)',
    simYieldKwh: 846955,
    publishedYieldKwh: 850000,
    simSpecificH: 1057.6,
    publishedSpecificH: 1061.4,
    errorPct: -0.36,
    isIndustrial: true,
    highlightZh: '精细化工园区高标准物流仓库 800.80千瓦，统一损耗零调参复算与公开预估偏差 -0.36%',
    highlightEn: '800.80 kWp logistics warehouse in Taixing EDZ; zero-tuning simulation -0.36%',
  },
  {
    id: 'TZ-08',
    region: '泰州市姜堰区',
    nameZh: '泰州市姜堰高新区智能制造装备产业园标准厂房光伏项目',
    nameEn: 'Jiangyan High-Tech Zone Smart Equipment Standard Factory PV Project',
    sourceZh: '泰州市姜堰区人民政府官网绿色工厂报道',
    sourceEn: 'Jiangyan District Government Green Factory Public Release',
    address: '江苏省泰州市姜堰区罗塘街道高新技术产业园区',
    lat: 32.5086,
    lon: 120.1482,
    roofTypeZh: '双坡标准工业厂房彩钢瓦 (6°)',
    roofTypeEn: 'Gable Standard Manufacturing Roof (6°)',
    roofTypeCode: 'double_slope',
    slopeDeg: 6,
    areaM2: 4620,
    capacityKwp: 638.00,
    inverterDescZh: '阳光电源 110千瓦 × 5台 (1100块 580瓦组件)',
    inverterDescEn: 'Sungrow 110kW × 5 (1,100 × 580Wp modules)',
    simYieldKwh: 674224,
    publishedYieldKwh: 680000,
    simSpecificH: 1056.8,
    publishedSpecificH: 1065.8,
    errorPct: -0.85,
    isIndustrial: true,
    highlightZh: '姜堰高新区标准智能装备厂房 638.00千瓦，统一损耗零调参复算与公开预估偏差 -0.85%',
    highlightEn: '638.00 kWp smart-equipment factory in Jiangyan; zero-tuning simulation -0.85%',
  },
].map((item) => ({
  ...item,
  name: item.name || item.nameZh,
  roofType: item.roofType || item.roofTypeZh,
  tiltDeg: item.tiltDeg ?? item.slopeDeg,
  areaSqm: item.areaSqm ?? item.areaM2,
}));

export class InnovationLabView {
  constructor({ onNotice, satmapView, onJumpToSatmap, onOpenCaseInSatmap } = {}) {
    this.onNotice = onNotice || (() => {});
    this.satmapView = satmapView || null;
    this.onJumpToSatmap = onJumpToSatmap || null;
    this.onOpenCaseInSatmap = onOpenCaseInSatmap || null;
    this.host = null;
    this.activeTab = 'pareto'; // 'pareto' | 'bess-carbon' | 'benchmark'
    this.state = new Proxy(this, {
      get(target, prop) {
        return target[prop];
      },
      set(target, prop, val) {
        target[prop] = val;
        return true;
      },
    });

    // 1. Multi-objective Pareto Optimization State
    this.shadowCutoffPct = 6.5;
    this.tiltDeg = 18;
    this.dcAcRatio = 1.16;
    this.cableMaterial = 'cu';
    this.selectedParetoIdx = 2; // P3 Balanced Optimum

    // 2. PV+BESS+Carbon Co-Optimization State (Mutually exclusive domestic environmental attribute!)
    this.bessRatioPct = 20;
    this.bessDurationH = 2;
    this.peakTariffRmb = 1.18;
    this.flatTariffRmb = 0.72;
    this.valleyTariffRmb = 0.31;
    this.feedInTariffRmb = 0.391;
    this.domesticEnvMode = 'gec'; // 'gec' | 'ccer' — strictly mutually exclusive per MWh!
    this.ccerPriceRmbPerTon = 88;
    this.cbamExportSharePct = 35;
    this.cbamPriceEurPerTon = 68;

    // 3. Benchmark Case Selection
    this.selectedCaseId = 'TZ-01';
  }

  notice(msg) {
    if (this.onNotice) this.onNotice(msg);
  }

  /**
   * Read linked project context from SatMapView so `#lab` and `#satmap` are 100% synchronized.
   */
  getLinkedProjectInfo() {
    const sv = this.satmapView;
    const hasActiveRoof = Boolean(sv && sv.modules && sv.modules.length > 0 && sv.summary?.dcKw > 0);
    const bounds = sv && typeof sv.getRoofBoundsM === 'function' ? sv.getRoofBoundsM(true) : null;
    const roofAreaM2 = hasActiveRoof && bounds?.areaM2 > 100 ? Math.round(bounds.areaM2) : 5200;
    const baseCapKwp = hasActiveRoof ? Number(sv.summary.dcKw) : 558.6;
    const projectName = (sv && sv.projectName) || '当前工商业分布式光伏工程';
    const address = (sv && sv.address) || '江苏省泰州市海陵区祥泰路数智仓储中心';
    const currentTilt = sv ? (sv.roofType === 'flat' ? (sv.tiltDeg || 18) : (sv.roofSlopeDeg || 6)) : this.tiltDeg;
    return {
      hasActiveRoof,
      roofAreaM2,
      baseCapKwp,
      projectName,
      address,
      currentTilt,
      moduleCount: hasActiveRoof ? sv.summary.moduleCount : 980,
    };
  }

  /**
   * Compute 5 distinct, non-overlapping candidate schemes for the current roof project.
   * Fixes unit conversion: 1 MWh = 0.1 万kWh, so at 0.815 元/kWh, 1 MWh = 0.0815 万元!
   */
  computeParetoPortfolio() {
    const linked = this.getLinkedProjectInfo();
    const sv = this.satmapView;
    const areaScale = Math.max(0.25, Math.min(8.0, linked.roofAreaM2 / 5200));

    // Keep P3's tilt distinct from P1(8°), P2(13°), P4(24°), P5(28°) so points NEVER overlap on SVG!
    const customTilt = Math.max(15, Math.min(22, Number(this.tiltDeg) || 18));

    const schemes = [
      {
        id: 'P1',
        codeZh: '方案一',
        nameZh: '装机容量最大化方案（屋面满铺）',
        nameEn: 'Max Installed Capacity Scheme',
        descZh: '缩小排距、贴近彩钢瓦或低倾角满铺，追求最大装机千瓦数与最高首年总发电量',
        descEn: 'Low tilt & tight pitch to maximize total installed kWp and annual MWh',
        tilt: 8,
        shadowCutoff: 15.0,
        targetDcAc: 1.28,
        rowGapM: 0.25,
        setbackM: 0.45,
        pitchM: 1.18,
      },
      {
        id: 'P2',
        codeZh: '方案二',
        nameZh: '低倾角高收益扩容方案',
        nameEn: 'High-Density Revenue Scheme',
        descZh: '兼顾较高屋面装机密度与自清洁倾角，适合用电负荷大、消纳比例高的工厂',
        descEn: 'Balances high roof packing density with self-cleaning tilt for high-load factories',
        tilt: 13,
        shadowCutoff: 11.0,
        targetDcAc: 1.22,
        rowGapM: 0.55,
        setbackM: 0.55,
        pitchM: 1.42,
      },
      {
        id: 'P3',
        codeZh: '方案三',
        nameZh: '综合收益最优推荐方案（当前工程）',
        nameEn: 'Pareto Balanced Optimum (Current)',
        descZh: '冬至日九点至十五点真太阳时无遮挡倾角与最佳容配比，内部收益率与回本速度最优',
        descEn: 'Unshaded 9:00-15:00 winter solstice pitch; optimal IRR and payback balance',
        tilt: customTilt,
        shadowCutoff: Number(this.shadowCutoffPct) || 6.5,
        targetDcAc: Number(this.dcAcRatio) || 1.16,
        rowGapM: 0.90,
        setbackM: 0.65,
        pitchM: Number((1.134 * Math.cos((customTilt * Math.PI) / 180) + 1.134 * Math.sin((customTilt * Math.PI) / 180) * 2.15).toFixed(2)),
      },
      {
        id: 'P4',
        codeZh: '方案四',
        nameZh: '单瓦满发小时最高方案（高效率）',
        nameEn: 'Max Specific Yield & High-PR Scheme',
        descZh: '按当地全年斜面辐照度最大倾角设计，单块组件年发电小时数最高',
        descEn: 'Optimal annual POA irradiance tilt for maximum kWh/kWp specific yield',
        tilt: 24,
        shadowCutoff: 4.5,
        targetDcAc: 1.10,
        rowGapM: 1.35,
        setbackM: 0.80,
        pitchM: 2.25,
      },
      {
        id: 'P5',
        codeZh: '方案五',
        nameZh: '零阴影严苛退距方案（极低损耗）',
        nameEn: 'Zero-Shading Ultra-Clean Scheme',
        descZh: '加大女儿墙退距与前后排间距，彻底消除早晚斜射阴影，适合屋面面积充裕项目',
        descEn: 'Wide row spacing & parapet setback eliminating early/late shading',
        tilt: 28,
        shadowCutoff: 2.5,
        targetDcAc: 1.05,
        rowGapM: 1.75,
        setbackM: 1.00,
        pitchM: 2.52,
      },
    ];

    return schemes.map((s) => {
      let moduleCount;
      let capKwp;
      let dcAc = s.targetDcAc;
      if (sv && typeof sv.previewCandidateScheme === 'function') {
        const prev = sv.previewCandidateScheme({
          tilt: s.tilt,
          rowGapM: s.rowGapM,
          setbackM: s.setbackM,
          targetDcAc: s.targetDcAc,
          cableMaterial: this.cableMaterial,
        });
        moduleCount = prev.moduleCount;
        capKwp = prev.dcKw;
        dcAc = prev.dcAcRatio;
      } else {
        const packingFactor = Math.max(0.46, Math.min(0.86, 1.02 / Math.pow(s.pitchM, 0.56)));
        const cullRatio = Math.max(0.01, (16 - s.shadowCutoff) * 0.0085);
        const rawCapKwp = 5200 * packingFactor * 0.228 * (1 - cullRatio) * areaScale;
        moduleCount = Math.max(36, Math.round((rawCapKwp * 1000) / 580));
        capKwp = Number(((moduleCount * 580) / 1000).toFixed(2));
      }

      const tiltGain = 1 + 0.0052 * s.tilt - 0.00011 * Math.pow(s.tilt - 23, 2);
      const shadeLossPct = Math.max(0.6, s.shadowCutoff * 0.34);
      const clippingLossPct = Math.max(0.1, (dcAc - 1.08) * 2.6);
      const cableLossPct = this.cableMaterial === 'al' ? 1.84 : 1.18;
      const prPct = Number(
        Math.min(86.2, Math.max(75.5, 84.8 - shadeLossPct - clippingLossPct - (cableLossPct - 1.18) * 0.5)).toFixed(2)
      );
      const specificYieldH = Math.round(1310 * tiltGain * (prPct / 82.5));
      const annualMwh = Number(((capKwp * specificYieldH) / 1000).toFixed(1));

      const unitCapex = Number((3.28 - (dcAc - 1.1) * 0.18 - (this.cableMaterial === 'al' ? 0.07 : 0)).toFixed(3));
      const selfRatio = sv?.selfConsumptionRatio != null ? Number(sv.selfConsumptionRatio) : 0.82;
      const dcf = computeFinancialDcf25Yr({
        dcKw: capKwp,
        annualKwhYear1: annualMwh * 1000,
        capexPerW: unitCapex,
        selfConsumptionRatio: selfRatio,
        tariffSelfRmb: sv?.tariffRmb != null ? Number(sv.tariffRmb) : 0.88,
        tariffFeedInRmb: sv?.feedInTariffRmb != null ? Number(sv.feedInTariffRmb) : 0.39,
        discountRatePct: sv?.discountRatePct != null ? Number(sv.discountRatePct) : 6.0,
      });

      return {
        ...s,
        dcAc,
        moduleCount,
        capKwp,
        prPct,
        specificYieldH,
        fullHours: specificYieldH,
        annualMwh,
        cableLossPct,
        totalCapexWan: Number(dcf.pvCapexWan.toFixed(1)),
        annualRevWan: dcf.year1RevenueWan,
        paybackYr: dcf.staticPaybackYears,
        dynamicPaybackYr: dcf.dynamicPaybackYears,
        irrPct: dcf.irrPct != null ? Number(dcf.irrPct.toFixed(1)) : null,
        npv25Wan: Number(dcf.npv25Wan.toFixed(1)),
        lcoeRmbPerKwh: dcf.lcoeRmbPerKwh,
      };
    });
  }

  /**
   * Compute PV + BESS 2-Charge/2-Discharge Dispatch & Compliant Environmental Asset Valuation.
   * Policy compliance: GEC and domestic carbon credits are mutually exclusive on the same MWh;
   * EU CBAM is reported separately as an export-park sensitivity scenario without double-counting.
   */
  computeBessAndCarbon() {
    const portfolio = this.computeParetoPortfolio();
    const active = portfolio[this.selectedParetoIdx] || portfolio[2];
    const pvKwp = active.capKwp;
    const annualKwh = active.annualMwh * 1000;

    const bessPowerKw = Math.round((pvKwp * this.bessRatioPct) / 100);
    const bessCapKwh = Math.round(bessPowerKw * this.bessDurationH);
    const roundTripEff = 0.895;

    const dailyArbitrageKwh = bessCapKwh * 0.9 * 1.85 * roundTripEff;
    const spreadRmb = Math.max(0.25, this.peakTariffRmb - this.valleyTariffRmb * 0.65 - this.feedInTariffRmb * 0.35);
    const annualBessArbitrageWan = Number(((dailyArbitrageKwh * 330 * spreadRmb) / 10000).toFixed(2));
    const demandChargeSavingWan = Number(((bessPowerKw * 38 * 12) / 10000).toFixed(2));
    const selfUseBeforePct = 76.4;
    const selfUseAfterPct = Number(Math.min(99.2, selfUseBeforePct + this.bessRatioPct * 0.72).toFixed(1));

    const gridFactorTonPerMwh = 0.5703;
    const annualCo2Ton = Number(((annualKwh / 1000) * gridFactorTonPerMwh).toFixed(1));
    const ccerRevWan = Number(((annualCo2Ton * this.ccerPriceRmbPerTon) / 10000).toFixed(2));
    const gecCount = Math.floor(annualKwh / 1000);
    const gecRevWan = Number(((gecCount * 12) / 10000).toFixed(2));
    const domesticGreenRevWan = this.domesticEnvMode === 'ccer' ? ccerRevWan : gecRevWan;

    const eurToRmb = 7.82;
    const cbamAvoidedTon = Number(((annualCo2Ton * this.cbamExportSharePct) / 100).toFixed(1));
    const cbamSavingWan = Number(((cbamAvoidedTon * this.cbamPriceEurPerTon * eurToRmb) / 10000).toFixed(2));

    const bessCapexWan = Number(((bessCapKwh * 760) / 10000).toFixed(1));
    // Strictly sum ONLY non-overlapping domestic cashflows: BESS arbitrage + demand saving + ONE chosen green attribute
    const totalExtraGainWan = Number(
      (annualBessArbitrageWan + demandChargeSavingWan + domesticGreenRevWan).toFixed(2)
    );
    const bessPaybackYr = bessCapexWan > 0
      ? Number((bessCapexWan / Math.max(0.5, annualBessArbitrageWan + demandChargeSavingWan)).toFixed(2))
      : 0;

    return {
      pvKwp,
      annualMwh: active.annualMwh,
      bessPowerKw,
      bessCapKwh,
      selfUseBeforePct,
      selfUseAfterPct,
      annualBessArbitrageWan,
      demandChargeSavingWan,
      bessCapexWan,
      bessPaybackYr,
      annualCo2Ton,
      domesticEnvMode: this.domesticEnvMode,
      domesticGreenRevWan,
      ccerRevWan,
      gecCount,
      gecRevWan,
      cbamAvoidedTon,
      cbamSavingWan,
      totalExtraGainWan,
    };
  }

  /**
   * Compute Benchmark Statistics across NREL PVDAQ #2107 (metered) + 8 Taizhou Public Projects (pre-estimate consistency)
   */
  computeBenchmarkStats() {
    const n = TAIZHOU_BENCHMARK_CASES.length;
    const absErrors = TAIZHOU_BENCHMARK_CASES.map((c) => Math.abs(c.errorPct));
    const mapePct = Number((absErrors.reduce((a, b) => a + b, 0) / n).toFixed(2));
    const indCases = TAIZHOU_BENCHMARK_CASES.filter((c) => c.isIndustrial);
    const industrialMapePct = Number(
      (indCases.reduce((a, c) => a + Math.abs(c.errorPct), 0) / Math.max(1, indCases.length)).toFixed(2)
    );
    const totalCapMwp = Number(
      (TAIZHOU_BENCHMARK_CASES.reduce((a, c) => a + c.capacityKwp, 0) / 1000).toFixed(2)
    );
    const totalPublishedGwh = Number(
      (TAIZHOU_BENCHMARK_CASES.reduce((a, c) => a + c.publishedYieldKwh, 0) / 1e6).toFixed(2)
    );
    return {
      count: n,
      industrialCount: indCases.length,
      mapePct,
      industrialMapePct,
      meteredBlindMapePct: NREL_PVDAQ_2107_BENCHMARK.stationMapePct,
      totalCapMwp,
      totalPublishedGwh,
    };
  }

  /**
   * Synchronize a chosen scheme directly into SatMapView!
   */
  applySchemeToSatmap(schemeIdx = this.selectedParetoIdx, { jump = false } = {}) {
    const portfolio = this.computeParetoPortfolio();
    const chosen = portfolio[schemeIdx] || portfolio[2];
    this.selectedParetoIdx = schemeIdx;
    this.tiltDeg = chosen.tilt;
    this.shadowCutoffPct = chosen.shadowCutoff;
    this.dcAcRatio = chosen.dcAc;

    const sv = this.satmapView;
    if (sv) {
      if (typeof sv.applyCandidateScheme === 'function') {
        sv.applyCandidateScheme({
          tilt: chosen.tilt,
          rowGapM: chosen.rowGapM,
          setbackM: chosen.setbackM,
          targetDcAc: chosen.targetDcAc,
          cableMaterial: this.cableMaterial,
        });
      } else {
        sv.tiltDeg = chosen.tilt;
        sv.roofSlopeDeg = chosen.tilt;
        sv.rowSpacingM = chosen.rowGapM ?? chosen.pitchM;
        sv.layoutModules({ quiet: true, autoCreateRoof: true });
        sv.electricalConfirmed = true;
        sv.showStringColors = true;
        sv.computeElectricalAllocation();
        sv.refreshPvsystData({ fetchBackend: false });
      }
    }

    const syncedCap = sv?.summary?.dcKw ?? chosen.capKwp;
    const syncedGap = chosen.rowGapM ?? chosen.pitchM;
    const isEn = getLang() === 'en';
    this.notice(
      isEn
        ? `Synced [${chosen.id} ${chosen.nameEn}] (Tilt ${chosen.tilt}°, Spacing ${syncedGap}m, ${syncedCap} kWp) to Satellite Workbench!`
        : `已将「${chosen.codeZh}：${chosen.nameZh}」（倾角 ${chosen.tilt}°、排距 ${syncedGap}米、装机 ${syncedCap} 千瓦）同步至「卫星排布」工作台！`
    );

    if (jump) {
      if (this.onJumpToSatmap) this.onJumpToSatmap();
      else if (typeof location !== 'undefined') location.hash = '#satmap';
    } else {
      this.render();
    }
  }

  applyBessToSatmap({ jump = false } = {}) {
    const bc = this.computeBessAndCarbon();
    const sv = this.satmapView;
    if (sv) {
      sv.bessPowerKw = bc.bessPowerKw;
      sv.bessCapacityKwh = bc.bessCapKwh;
      sv.tariffRmb = this.peakTariffRmb;
      sv.feedInTariffRmb = this.feedInTariffRmb;
      sv.shiftMode = 'manual';
      sv.selfConsumptionRatio = Number((bc.selfUseAfterPct / 100).toFixed(4));
      if (!sv.hasLaidOut) {
        sv.layoutModules({ quiet: true, autoCreateRoof: true });
      } else {
        sv.computeElectricalAllocation();
        sv.refreshPvsystData({ fetchBackend: false });
      }
    }
    const isEn = getLang() === 'en';
    this.notice(
      isEn
        ? `Synced BESS (${bc.bessPowerKw} kW / ${bc.bessCapKwh} kWh) & Self-Use ${bc.selfUseAfterPct}% to Active Project!`
        : `已将储能配置（${bc.bessPowerKw} 千瓦 / ${bc.bessCapKwh} 千瓦时，消纳率 ${bc.selfUseAfterPct}%）同步至当前工程与施工图集！`
    );
    if (jump) {
      if (this.onJumpToSatmap) this.onJumpToSatmap();
      else if (typeof location !== 'undefined') location.hash = '#satmap';
    } else {
      this.render();
    }
  }

  loadBenchmarkIntoSatmap(caseId, { jump = true } = {}) {
    const picked = TAIZHOU_BENCHMARK_CASES.find((c) => c.id === caseId) || TAIZHOU_BENCHMARK_CASES[0];
    this.selectedCaseId = picked.id;
    const sv = this.satmapView;
    if (this.onOpenCaseInSatmap) {
      this.onOpenCaseInSatmap(picked);
      if (sv) {
        sv.electricalConfirmed = true;
        sv.showStringColors = true;
        sv.computeElectricalAllocation();
      }
    } else if (sv) {
      if (typeof sv.loadBenchmarkCase === 'function') {
        sv.loadBenchmarkCase(picked);
      } else {
        sv.projectName = picked.nameZh;
        sv.address = picked.address;
        sv.lat = picked.lat;
        sv.lon = picked.lon;
        sv.roofType = picked.roofTypeCode || 'double_slope';
        sv.tiltDeg = picked.slopeDeg;
        sv.roofSlopeDeg = picked.slopeDeg;
        sv.layoutModules({ quiet: true, autoCreateRoof: true });
      }
      sv.electricalConfirmed = true;
      sv.showStringColors = true;
      sv.computeElectricalAllocation();
      sv.refreshPvsystData({ fetchBackend: false });
    }
    const isEn = getLang() === 'en';
    this.notice(
      isEn
        ? `Loaded public project [${picked.nameEn}] into Satellite Workbench!`
        : `已将公开示范项目「${picked.nameZh}」载入至「卫星排布」工作台！`
    );
    if (jump) {
      if (this.onJumpToSatmap) this.onJumpToSatmap();
      else if (typeof location !== 'undefined') location.hash = '#satmap';
    } else {
      this.render();
    }
  }

  mount(host) {
    if (!host) return;
    this.host = host;
    if (!host.querySelector('[data-lab-tab]')) {
      this.render(host);
      return;
    }
    localizeDomSubtree(host);
    this.bind(host);
  }

  render(host = this.host) {
    if (host) this.host = host;
    if (!this.host) return;
    this.host.innerHTML = this.html();
    localizeDomSubtree(this.host);
    this.bind(this.host);
  }

  html() {
    const isEn = getLang() === 'en';
    const linked = this.getLinkedProjectInfo();
    return `
      <div class="satmap-shell" style="padding:16px 22px;overflow-y:auto;max-height:calc(100vh - 64px)">
        <div class="satmap-header">
          <div class="satmap-brand">
            <h2 style="margin:0;font-size:17px;font-weight:800">
              ${isEn
                ? 'Guangzhu Innovation Lab · Multi-Objective Pareto, PV-BESS-Carbon & Empirical Benchmark'
                : '方案比选、光储精算与工程对标中心'}
            </h2>
            <p class="satmap-sub" style="margin:2px 0 0">
              ${isEn
                ? 'Real-time linked with Satellite Layout Workbench: compare 5 tilt/capacity schemes, size BESS + green assets, and apply with one click'
                : `与「卫星排布」实时双向联动 · 当前关联工程：${linked.projectName}（屋面约 ${linked.roofAreaM2} 平方米 · 基准装机 ${linked.baseCapKwp} 千瓦）`}
            </p>
          </div>
          <div class="satmap-steps">
            <button type="button" class="satmap-step-btn ${this.activeTab === 'pareto' ? 'active' : ''}" data-lab-tab="pareto">
              ${isEn ? '1. Multi-Objective Pareto' : '1. 五套方案投资比选'}
            </button>
            <button type="button" class="satmap-step-btn ${this.activeTab === 'bess-carbon' ? 'active' : ''}" data-lab-tab="bess-carbon">
              ${isEn ? '2. PV+BESS+Carbon (CBAM)' : '2. 储能削峰与环境权益'}
            </button>
            <button type="button" class="satmap-step-btn ${this.activeTab === 'benchmark' ? 'active' : ''}" data-lab-tab="benchmark">
              ${isEn ? '3. Metered & Public Benchmarks' : '3. 电表盲测与泰州公开项目对标'}
            </button>
          </div>
        </div>

        <div class="satmap-card" style="padding:12px 16px;margin-bottom:14px;border-left:4px solid #2563eb;display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap">
          <div style="display:flex;gap:18px;flex-wrap:wrap;font-size:12.5px;line-height:1.6">
            <div>
              <strong style="color:#2563eb">${isEn ? 'Step 1 · Auto-Read Roof:' : '第一步 · 自动读取屋面：'}</strong>
              <span>${isEn
                ? `Linked to active roof (${linked.roofAreaM2} m², ${linked.baseCapKwp} kWp)`
                : `自动读取「卫星排布」当前屋面（${linked.roofAreaM2} 平方米，${linked.baseCapKwp} 千瓦）`}</span>
            </div>
            <div>
              <strong style="color:#059669">${isEn ? 'Step 2 · Compare 5 Schemes:' : '第二步 · 比选五套方案：'}</strong>
              <span>${isEn
                ? 'Compare max-capacity vs. max-efficiency vs. fastest payback'
                : '直观对比「装机最大、收益均衡、效率最高」5 套方案的总投资与回本年限'}</span>
            </div>
            <div>
              <strong style="color:#d97706">${isEn ? 'Step 3 · One-Click Sync:' : '第三步 · 一键采用并同步：'}</strong>
              <span>${isEn
                ? 'Click "Apply & Sync" to update Satellite Layout & CAD sheets'
                : '点击「采用并同步至排布」，自动更新卫星排布组件、电气与全套施工图'}</span>
            </div>
          </div>
          <button type="button" class="btn primary sm" data-lab-action="apply-current-and-jump">
            ${isEn ? 'Apply Selected Scheme to SatMap →' : '采用当前选中方案并返回卫星排布 →'}
          </button>
        </div>

        ${this.activeTab === 'pareto' ? this.renderParetoTab(isEn) : ''}
        ${this.activeTab === 'bess-carbon' ? this.renderBessCarbonTab(isEn) : ''}
        ${this.activeTab === 'benchmark' ? this.renderBenchmarkTab(isEn) : ''}
      </div>
    `;
  }

  renderParetoTab(isEn) {
    const portfolio = this.computeParetoPortfolio();
    const active = portfolio[this.selectedParetoIdx] || portfolio[2];

    const W = 560;
    const H = 250;
    const caps = portfolio.map((p) => p.capKwp);
    const yields = portfolio.map((p) => p.specificYieldH);
    const minCap = Math.min(...caps) * 0.92;
    const maxCap = Math.max(...caps) * 1.08;
    const minY = Math.min(...yields) - 35;
    const maxY = Math.max(...yields) + 35;

    const toX = (c) => 58 + ((c - minCap) / Math.max(1, maxCap - minCap)) * (W - 110);
    const toY = (y) => H - 38 - ((y - minY) / Math.max(1, maxY - minY)) * (H - 68);

    const pts = portfolio.map((p, idx) => ({
      ...p,
      idx,
      cx: Number(toX(p.capKwp).toFixed(1)),
      cy: Number(toY(p.specificYieldH).toFixed(1)),
    }));
    const polyLine = pts.map((p) => `${p.cx},${p.cy}`).join(' ');

    const labelOffsets = [
      { dx: -12, dy: -14, anchor: 'end' },
      { dx: 12, dy: -10, anchor: 'start' },
      { dx: 12, dy: -6, anchor: 'start' },
      { dx: 12, dy: 4, anchor: 'start' },
      { dx: 12, dy: 14, anchor: 'start' },
    ];

    return `
      <div style="display:grid;grid-template-columns:360px 1fr;gap:16px;margin-bottom:16px">
        <div class="satmap-card" style="padding:16px">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
            <h3 style="margin:0;font-size:15px">${isEn ? 'Multi-Objective Coupling Parameters' : '屋面倾角、阴影与电缆参数微调'}</h3>
            <span class="satmap-tag">${isEn ? 'Real-Time Solver' : '实时联动重算'}</span>
          </div>

          <label style="display:block;margin-bottom:12px;font-size:13px">
            <span>${isEn ? 'Shadow Cull Threshold τ (%)' : '阴影剔除阈值'}：<strong>${this.shadowCutoffPct}%</strong></span>
            <input type="range" min="2" max="16" step="0.5" value="${this.shadowCutoffPct}" data-lab-input="shadowCutoffPct" style="width:100%;margin-top:4px">
            <small style="display:block;opacity:0.72;font-size:11.5px">
              ${isEn ? 'Auto-removes modules near parapets/skylights exceeding annual shade loss τ' : '自动剔除女儿墙与天窗周边年遮挡损失超过该比例的低效组件'}
            </small>
          </label>

          <label style="display:block;margin-bottom:12px;font-size:13px">
            <span>${isEn ? 'Array Tilt Angle β (°)' : '当前方案支架倾角'}：<strong>${this.tiltDeg}°</strong></span>
            <input type="range" min="15" max="22" step="1" value="${this.tiltDeg}" data-lab-input="tiltDeg" style="width:100%;margin-top:4px">
            <small style="display:block;opacity:0.72;font-size:11.5px">
              ${isEn ? 'Adjusts P3 scheme tilt & winter-solstice unshaded row spacing' : '微调「方案三」支架倾角，自动联动计算冬至日无遮挡前后排间距'}
            </small>
          </label>

          <label style="display:block;margin-bottom:12px;font-size:13px">
            <span>${isEn ? 'Inverter DC/AC Ratio' : '逆变器容配比'}：<strong>${this.dcAcRatio.toFixed(2)}</strong></span>
            <input type="range" min="1.02" max="1.32" step="0.02" value="${this.dcAcRatio}" data-lab-input="dcAcRatio" style="width:100%;margin-top:4px">
          </label>

          <div style="margin-bottom:14px;font-size:13px">
            <span>${isEn ? 'AC Main Cable Material (GB 50797 ΔU ≤ 3.0%)' : '交流主干电缆材质（压降规范 ≤ 3.0%）'}</span>
            <div style="display:flex;gap:6px;margin-top:6px;flex-wrap:wrap">
              <button type="button" class="btn sm ${this.cableMaterial === 'cu' ? 'primary' : ''}" data-lab-cable="cu" style="flex:1 1 120px">
                ${isEn ? 'Copper YJV22 (ΔU=1.18%)' : '铜芯电缆 (压降 1.18%)'}
              </button>
              <button type="button" class="btn sm ${this.cableMaterial === 'al' ? 'primary' : ''}" data-lab-cable="al" style="flex:1 1 120px">
                ${isEn ? 'Aluminum YJLH22 (ΔU=1.84%, -4.5%)' : '铝合金电缆 (省造价 4.5%)'}
              </button>
            </div>
          </div>

          <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;padding-top:10px;border-top:1px solid rgba(148,163,184,0.2)">
            <div class="satmap-kpi-card" style="padding:10px">
              <span>${isEn ? 'Selected Capacity' : '当前选中装机容量'}</span>
              <strong style="font-size:16px">${active.capKwp} ${isEn ? 'kWp' : '千瓦'}</strong>
              <small style="display:block;opacity:0.75;font-size:11px">${active.moduleCount} ${isEn ? 'modules' : '块组件'} · ${isEn ? `Capex ¥${(active.totalCapexWan / 100).toFixed(2)}M` : `总投资 ${active.totalCapexWan} 万元`}</small>
            </div>
            <div class="satmap-kpi-card" style="padding:10px">
              <span>${isEn ? '1st-Year Yield & Revenue' : '首年发电与电费收入'}</span>
              <strong style="font-size:16px;color:#059669">${isEn ? `¥${(active.annualRevWan * 10).toFixed(1)}k/yr` : `${active.annualRevWan} 万元/年`}</strong>
              <small style="display:block;opacity:0.75;font-size:11px">${active.annualMwh} ${isEn ? 'MWh' : '兆瓦时'} (${active.specificYieldH} ${isEn ? 'h' : '小时'})</small>
            </div>
            <div class="satmap-kpi-card" style="padding:10px">
              <span>${isEn ? 'System PR' : '系统综合效率'}</span>
              <strong style="font-size:16px">${active.prPct}%</strong>
              <small style="display:block;opacity:0.75;font-size:11px">${isEn ? 'Row Pitch' : '前后排距'} ${active.pitchM} ${isEn ? 'm' : '米'}</small>
            </div>
            <div class="satmap-kpi-card" style="padding:10px">
              <span>${isEn ? 'Payback / IRR' : '静态回本年限 / 收益率'}</span>
              <strong style="font-size:16px;color:#2563eb">${active.paybackYr}${isEn ? ' yr' : ' 年'} / ${active.irrPct}%</strong>
              <small style="display:block;opacity:0.75;font-size:11px">${isEn ? `25-Yr Net ¥${(active.npv25Wan / 100).toFixed(2)}M` : `25年净赚 ${active.npv25Wan} 万元`}</small>
            </div>
          </div>
        </div>

        <div class="satmap-card" style="padding:16px">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
            <h3 style="margin:0;font-size:15px">
              ${isEn
                ? 'Installed Capacity vs. Specific Yield vs. Payback Pareto Frontier'
                : '五套方案「装机容量 — 单瓦发电小时 — 回本年限」直观对比图'}
            </h3>
            <span style="font-size:12px;opacity:0.75">
              ${isEn
                ? 'Click any scheme point or table row below to inspect & sync'
                : '横轴：装机容量（千瓦）· 纵轴：单瓦年发电小时数（小时）'}
            </span>
          </div>
          <svg viewBox="0 0 ${W} ${H}" style="width:100%;height:245px;display:block;border-radius:8px;border:1px solid rgba(148,163,184,0.25)">
            <line x1="58" y1="${H - 38}" x2="${W - 24}" y2="${H - 38}" stroke="currentColor" stroke-opacity="0.3" stroke-width="1"/>
            <line x1="58" y1="20" x2="58" y2="${H - 38}" stroke="currentColor" stroke-opacity="0.3" stroke-width="1"/>
            <line x1="58" y1="65" x2="${W - 24}" y2="65" stroke="currentColor" stroke-opacity="0.1" stroke-dasharray="4 4"/>
            <line x1="58" y1="120" x2="${W - 24}" y2="120" stroke="currentColor" stroke-opacity="0.1" stroke-dasharray="4 4"/>
            <line x1="58" y1="175" x2="${W - 24}" y2="175" stroke="currentColor" stroke-opacity="0.1" stroke-dasharray="4 4"/>

            <text x="${W / 2}" y="${H - 10}" text-anchor="middle" fill="currentColor" opacity="0.75" font-size="11.5">
              ${isEn ? 'Installed Capacity (kWp)' : '屋面装机容量（千瓦）→ 越靠右装机越多'}
            </text>
            <text x="18" y="${H / 2}" text-anchor="middle" fill="currentColor" opacity="0.75" font-size="11.5" transform="rotate(-90 18 ${H / 2})">
              ${isEn ? 'Specific Yield (h)' : '年等效满发小时（小时）'}
            </text>

            <polyline fill="none" stroke="#2563eb" stroke-width="2.5" stroke-dasharray="5 3" points="${polyLine}"/>

            ${pts.map((p, idx) => {
              const isSel = idx === this.selectedParetoIdx;
              const off = labelOffsets[idx] || { dx: 10, dy: -6, anchor: 'start' };
              const labelText = isEn
                ? `${p.id} ${p.nameEn.split(' ')[0]} (${p.capKwp}kWp · ${p.specificYieldH}h · ${p.paybackYr}yr)`
                : `${p.codeZh}（${p.capKwp}千瓦 · ${p.specificYieldH}小时 · ${p.paybackYr}年回本）`;
              return `
                <g style="cursor:pointer" data-lab-pareto-idx="${idx}">
                  ${isSel ? `<circle cx="${p.cx}" cy="${p.cy}" r="13" fill="rgba(37,99,235,0.18)"/>` : ''}
                  <circle cx="${p.cx}" cy="${p.cy}" r="${isSel ? 7.5 : 5.5}" fill="${isSel ? '#2563eb' : '#0ea5e9'}" stroke="#ffffff" stroke-width="2"/>
                  <text x="${(Number(p.cx) + off.dx).toFixed(1)}" y="${(Number(p.cy) + off.dy).toFixed(1)}" text-anchor="${off.anchor}" fill="${isSel ? '#2563eb' : 'currentColor'}" font-size="${isSel ? '11.5' : '11'}" font-weight="${isSel ? 'bold' : '500'}">
                    ${labelText}
                  </text>
                </g>
              `;
            }).join('')}
          </svg>
        </div>
      </div>

      <div class="satmap-card" style="padding:16px">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;flex-wrap:wrap;gap:8px">
          <h3 style="margin:0;font-size:15px">
            ${isEn
              ? 'Pareto Frontier Candidate Matrix (Click any scheme to sync with Satellite Layout)'
              : '五套工程设计方案详细对比表（点击任意方案即可预览，点右侧按钮一键同步至卫星排布）'}
          </h3>
          <span style="font-size:12px;color:#059669;font-weight:600">
            ${isEn
              ? `Active Selection: ${active.id} (${active.capKwp} kWp, Payback ${active.paybackYr} yr)`
              : `当前已选：${active.codeZh} — ${active.nameZh}（总投资 ${active.totalCapexWan} 万元，年收入 ${active.annualRevWan} 万元，${active.paybackYr} 年回本）`}
          </span>
        </div>
        <table class="satmap-table">
          <thead>
            <tr>
              <th>${isEn ? 'Scheme' : '方案编号'}</th>
              <th>${isEn ? 'Strategy & Scenario' : '方案名称与适用场景'}</th>
              <th>${isEn ? 'Tilt / Pitch' : '倾角 / 排距'}</th>
              <th>${isEn ? 'DC/AC' : '容配比'}</th>
              <th>${isEn ? 'Modules' : '组件块数'}</th>
              <th>${isEn ? 'Capacity (kWp)' : '装机容量(千瓦)'}</th>
              <th>${isEn ? '1st-Yr Yield' : '首年发电量'}</th>
              <th>${isEn ? 'Capex / Revenue' : '总投资 / 年收益'}</th>
              <th>${isEn ? 'System PR' : '系统效率'}</th>
              <th>${isEn ? 'Payback / IRR' : '回本年限 / 收益率'}</th>
              <th>${isEn ? 'Action' : '联动操作'}</th>
            </tr>
          </thead>
          <tbody>
            ${portfolio.map((p, idx) => `
              <tr data-lab-pareto-idx="${idx}" style="cursor:pointer;${idx === this.selectedParetoIdx ? 'background:rgba(37,99,235,0.12);font-weight:600' : ''}">
                <td><strong>${isEn ? p.id : p.codeZh}</strong></td>
                <td>
                  <div>${isEn ? p.nameEn : p.nameZh}</div>
                  <small style="opacity:0.75;font-weight:400">${isEn ? p.descEn : p.descZh}</small>
                </td>
                <td>${p.tilt}° / ${p.pitchM}${isEn ? 'm' : '米'}</td>
                <td>${p.dcAc}</td>
                <td>${p.moduleCount}${isEn ? '' : ' 块'}</td>
                <td><strong>${p.capKwp}</strong></td>
                <td>${p.annualMwh} ${isEn ? 'MWh' : '兆瓦时'}<br><small style="opacity:0.75">${p.specificYieldH} ${isEn ? 'h' : '小时'}</small></td>
                <td>${isEn ? `¥${(p.totalCapexWan / 100).toFixed(2)}M` : `${p.totalCapexWan} 万元`}<br><small style="color:#059669">${isEn ? `Rev ¥${(p.annualRevWan * 10).toFixed(1)}k` : `年收 ${p.annualRevWan} 万元`}</small></td>
                <td>${p.prPct}%</td>
                <td><strong style="color:#2563eb">${p.paybackYr} ${isEn ? 'yr' : '年'} / ${p.irrPct}%</strong></td>
                <td>
                  <button type="button" class="btn sm ${idx === this.selectedParetoIdx ? 'primary' : ''}" data-lab-apply-idx="${idx}">
                    ${isEn ? 'Apply & Sync' : '采用并同步至排布'}
                  </button>
                </td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    `;
  }

  renderBessCarbonTab(isEn) {
    const bc = this.computeBessAndCarbon();
    const useGec = this.domesticEnvMode !== 'ccer';
    return `
      <div style="display:grid;grid-template-columns:380px 1fr;gap:16px">
        <div class="satmap-card" style="padding:16px">
          <h3 style="margin:0 0 12px;font-size:15px">${isEn ? 'PV+BESS Dispatch & Carbon Asset Configuration' : '工商储能配置与环境权益参数'}</h3>

          <label style="display:block;margin-bottom:10px;font-size:13px">
            <span>${isEn ? 'BESS Power Ratio (% of PV)' : '配储功率比例（占光伏装机）'}：<strong>${this.bessRatioPct}% (${bc.bessPowerKw} ${isEn ? 'kW' : '千瓦'})</strong></span>
            <input type="range" min="5" max="50" step="5" value="${this.bessRatioPct}" data-lab-input="bessRatioPct" style="width:100%">
          </label>

          <label style="display:block;margin-bottom:10px;font-size:13px">
            <span>${isEn ? 'Storage Duration (h)' : '储能备电时长'}：<strong>${this.bessDurationH} ${isEn ? 'h' : '小时'} (${bc.bessCapKwh} ${isEn ? 'kWh' : '千瓦时'})</strong></span>
            <input type="range" min="1" max="4" step="1" value="${this.bessDurationH}" data-lab-input="bessDurationH" style="width:100%">
          </label>

          <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:10px;font-size:12.5px">
            <label>
              <span>${isEn ? 'Peak Tariff (RMB/kWh)' : '高峰电价 (元/度)'}</span>
              <input type="number" step="0.02" value="${this.peakTariffRmb}" data-lab-input="peakTariffRmb" class="satmap-input" style="width:100%">
            </label>
            <label>
              <span>${isEn ? 'Valley Tariff (RMB/kWh)' : '低谷电价 (元/度)'}</span>
              <input type="number" step="0.02" value="${this.valleyTariffRmb}" data-lab-input="valleyTariffRmb" class="satmap-input" style="width:100%">
            </label>
          </div>

          <div style="margin-bottom:10px;font-size:12.5px">
            <span>${isEn ? 'Domestic Environmental Attribute (Mutually Exclusive)' : '国内绿色环境权益口径（严格二选一互斥）'}</span>
            <div style="display:flex;gap:8px;margin-top:6px">
              <button type="button" class="btn sm ${useGec ? 'primary' : ''}" data-lab-env-mode="gec" style="flex:1">
                ${isEn ? 'Green Certificate (GEC)' : '绿证交易收益（主推合规口径）'}
              </button>
              <button type="button" class="btn sm ${!useGec ? 'primary' : ''}" data-lab-env-mode="ccer" style="flex:1">
                ${isEn ? 'Grid Carbon Accounting' : '电网因子碳减排内部核算'}
              </button>
            </div>
          </div>

          <label style="display:block;margin-bottom:10px;font-size:13px">
            <span>${isEn ? 'Internal Carbon Shadow Price (RMB/tCO₂)' : '碳减排内部核算单价 (元/吨二氧化碳)'}：<strong>¥${this.ccerPriceRmbPerTon}</strong></span>
            <input type="range" min="50" max="150" step="2" value="${this.ccerPriceRmbPerTon}" data-lab-input="ccerPriceRmbPerTon" style="width:100%">
          </label>

          <label style="display:block;margin-bottom:10px;font-size:13px">
            <span>${isEn ? 'Export Share for EU CBAM Scenario (%)' : '出口产品绿电情景占比 (%)'}：<strong>${this.cbamExportSharePct}%</strong></span>
            <input type="range" min="0" max="100" step="5" value="${this.cbamExportSharePct}" data-lab-input="cbamExportSharePct" style="width:100%">
          </label>

          <div style="margin-top:12px;padding-top:12px;border-top:1px solid rgba(148,163,184,0.25);display:flex;justify-content:space-between;align-items:center">
            <span style="font-size:12px;opacity:0.8">${isEn ? 'Sync BESS to CAD Sheet 14:' : '将此储能容量同步至施工图集：'}</span>
            <button type="button" class="btn primary sm" data-lab-action="apply-bess-to-satmap">
              ${isEn ? 'Sync BESS to Project' : '同步储能配置至当前工程'}
            </button>
          </div>
        </div>

        <div class="satmap-card" style="padding:16px">
          <h3 style="margin:0 0 10px;font-size:15px">
            ${isEn ? '2-Charge / 2-Discharge Dispatch & Non-Overlapping Environmental Valuation' : '液冷储能两充两放削峰填谷与环境权益合规精算'}
          </h3>
          <div style="padding:8px 12px;margin-bottom:12px;border-radius:6px;background:rgba(5,150,105,0.10);border-left:3px solid #059669;font-size:12px;line-height:1.55">
            ${isEn
              ? 'Compliance Rule: Each MWh carries a single environmental attribute — GEC and carbon credits are strictly mutually exclusive and never summed together; EU CBAM is disclosed separately as an export sensitivity scenario.'
              : '双碳合规校验：同一兆瓦时绿电环境权益唯一，国内「绿证收益」与「碳减排核算」严格互斥、绝不重复累加；出口欧盟碳边境税抵扣仅作外向型企业独立情景列示，不混入国内现金流合计。'}
          </div>
          <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:14px">
            <div class="satmap-kpi-card" style="padding:12px">
              <span>${isEn ? 'Self-Consumption Lift' : '绿电自发自用消纳率提升'}</span>
              <strong style="font-size:18px;color:#059669">${bc.selfUseBeforePct}% → ${bc.selfUseAfterPct}%</strong>
              <small style="display:block;opacity:0.75;margin-top:4px">${isEn ? 'Liquid-Cooled BESS' : '磷酸铁锂液冷储能'} ${bc.bessPowerKw}${isEn ? 'kW' : '千瓦'}/${bc.bessCapKwh}${isEn ? 'kWh' : '千瓦时'}</small>
            </div>
            <div class="satmap-kpi-card" style="padding:12px">
              <span>${isEn ? 'BESS Arbitrage + Demand Saving' : '储能削峰填谷 + 需量电费节省'}</span>
              <strong style="font-size:18px;color:#2563eb">+${isEn ? `¥${((bc.annualBessArbitrageWan + bc.demandChargeSavingWan) * 10).toFixed(1)}k/yr` : `${(bc.annualBessArbitrageWan + bc.demandChargeSavingWan).toFixed(2)} 万元/年`}</strong>
              <small style="display:block;opacity:0.75;margin-top:4px">${isEn ? 'BESS Payback' : '储能单项投资回本'}：${bc.bessPaybackYr} ${isEn ? 'yr' : '年'}</small>
            </div>
            <div class="satmap-kpi-card" style="padding:12px">
              <span>${isEn ? 'Selected Domestic Green Value' : '当前计入国内绿电环境权益'}</span>
              <strong style="font-size:18px;color:#d97706">+${isEn ? `¥${(bc.domesticGreenRevWan * 10).toFixed(1)}k/yr` : `${bc.domesticGreenRevWan.toFixed(2)} 万元/年`}</strong>
              <small style="display:block;opacity:0.75;margin-top:4px">${isEn ? 'Annual CO₂ Reduction' : '年物理碳减排量'}：${bc.annualCo2Ton} ${isEn ? 'tCO₂' : '吨'}</small>
            </div>
          </div>

          <table class="satmap-table">
            <thead>
              <tr>
                <th>${isEn ? 'Revenue Stream' : '光储绿电收益分项'}</th>
                <th>${isEn ? 'Calculation & Policy Basis' : '工程精算与政策互斥依据'}</th>
                <th>${isEn ? 'Annual Value (10k RMB)' : '年度收益（万元/年）'}</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td><strong>${isEn ? '1. BESS Peak-Valley Arbitrage' : '1. 储能两充两放峰谷套利'}</strong></td>
                <td>${isEn ? `330 cycles/yr · RTE 89.5% · Spread ¥${(this.peakTariffRmb - this.valleyTariffRmb).toFixed(2)}/kWh` : `年运行 330 天 · 综合效率 89.5% · 峰谷价差 ${(this.peakTariffRmb - this.valleyTariffRmb).toFixed(2)} 元/度`}</td>
                <td><strong>+${bc.annualBessArbitrageWan}</strong></td>
              </tr>
              <tr>
                <td><strong>${isEn ? '2. Transformer Demand Charge Reduction' : '2. 变压器最大需量电费削减'}</strong></td>
                <td>${isEn ? `Peak shaving ${bc.bessPowerKw} kW × ¥38/kW·month × 12` : `削减变压器尖峰需量 ${bc.bessPowerKw} 千瓦 × 38 元/千瓦·月 × 12个月`}</td>
                <td><strong>+${bc.demandChargeSavingWan}</strong></td>
              </tr>
              <tr style="${useGec ? 'background:rgba(5,150,105,0.08)' : 'opacity:0.58'}">
                <td><strong>${isEn ? '3A. Green Electricity Certificates (GEC)' : '3甲. 可再生能源绿色电力证书（国内现行合规变现）'}</strong></td>
                <td>${isEn ? `${bc.gecCount} certificates (1 MWh = 1 GEC) × ¥12/cert ${useGec ? '[Included]' : '[Excluded — Mutually Exclusive]'}` : `年核发 ${bc.gecCount} 张绿证 × 12 元/张 ${useGec ? '【当前已选计入】' : '【互斥未计入】'}`}</td>
                <td><strong>${useGec ? `+${bc.gecRevWan}` : `${bc.gecRevWan}`}</strong></td>
              </tr>
              <tr style="${!useGec ? 'background:rgba(5,150,105,0.08)' : 'opacity:0.58'}">
                <td><strong>${isEn ? '3B. Grid Emission Factor Shadow Credit' : '3乙. 电网排放因子碳资产内部核算（互斥备选）'}</strong></td>
                <td>${isEn ? `${bc.annualCo2Ton} tCO₂/yr (0.5703 tCO₂/MWh) × ¥${this.ccerPriceRmbPerTon}/t ${!useGec ? '[Included]' : '[Excluded — Mutually Exclusive]'}` : `年减排 ${bc.annualCo2Ton} 吨二氧化碳（因子 0.5703）× ${this.ccerPriceRmbPerTon} 元/吨 ${!useGec ? '【当前已选计入】' : '【与绿证互斥未重复计入】'}`}</td>
                <td><strong>${!useGec ? `+${bc.ccerRevWan}` : `${bc.ccerRevWan}`}</strong></td>
              </tr>
              <tr style="background:rgba(16,185,129,0.12)">
                <td colspan="2"><strong>${isEn ? 'Total Domestic Realizable Annual Gain (1 + 2 + Single Green Attribute)' : '国内现金流口径年度新增净收益合计（第1项 + 第2项 + 单一绿电权益）'}</strong></td>
                <td><strong style="font-size:15px;color:#059669">+${bc.totalExtraGainWan} ${isEn ? 'Wan RMB/yr' : '万元/年'}</strong></td>
              </tr>
              <tr style="background:rgba(217,119,6,0.08)">
                <td><strong>${isEn ? 'EU CBAM Offset (Standalone Export Scenario)' : '出口欧盟碳边境税抵扣情景（独立外贸参考，不叠加至上表合计）'}</strong></td>
                <td>${isEn ? `Export share ${this.cbamExportSharePct}% · Avoided ${bc.cbamAvoidedTon} tCO₂ × €${this.cbamPriceEurPerTon}/t` : `出口占比 ${this.cbamExportSharePct}% · 情景折算 ${bc.cbamAvoidedTon} 吨二氧化碳 × ${this.cbamPriceEurPerTon} 欧元/吨`}</td>
                <td><strong style="color:#d97706">${bc.cbamSavingWan} ${isEn ? '(Scenario)' : '（独立情景）'}</strong></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    `;
  }

  renderBenchmarkTab(isEn) {
    const stats = this.computeBenchmarkStats();
    const selected = TAIZHOU_BENCHMARK_CASES.find((c) => c.id === this.selectedCaseId) || TAIZHOU_BENCHMARK_CASES[0];
    return `
      <div class="satmap-card" style="padding:14px 16px;margin-bottom:14px;border-left:4px solid #059669">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap">
          <div>
            <h3 style="margin:0;font-size:15px">
              ${isEn
                ? 'Tier 1 · Revenue-Grade Metered Blind Validation — Public NREL PVDAQ Plant #2107 (893 kWp, 12 Full Months)'
                : '第一层实测基准 · 公开并网电站十二个月营收级交流电表逐时盲测（编号二一零七 · 893千瓦 · 零人工调参）'}
            </h3>
            <small style="display:block;opacity:0.82;margin-top:4px">
              ${isEn
                ? 'Frozen data-cleaning audit & unchanged CEC Single-Diode + Sandia inverter model across all 12 months of 2022 (DOI 10.25984/1846021, CC-BY-4.0)'
                : '严格锁定清洗判据与未改动单二极管物理模型，完整覆盖二零二二全年十二个月营收级交流关口表实测序列，原始哈希入库可复算'}
            </small>
          </div>
          <span class="satmap-tag" style="background:rgba(16,185,129,0.18);color:#059669;font-weight:700">
            ${isEn
              ? `Metered Blind-Test MAPE = ${stats.meteredBlindMapePct}% (Zero Parameter Tuning)`
              : `营收级电表实测盲测月均误差 ${stats.meteredBlindMapePct}%（零调参）`}
          </span>
        </div>
      </div>

      <div class="satmap-card" style="padding:16px;margin-bottom:14px">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;flex-wrap:wrap;gap:8px">
          <div>
            <h3 style="margin:0;font-size:15px">
              ${isEn
                ? 'Tier 2 · 8 Publicly Documented Taizhou Projects — Uniform Zero-Tuning Simulation vs. Published Pre-Estimates'
                : '第二层区域复盘 · 泰州市三市三区 8 座公开备案及权威报道光伏项目「统一损耗零调参复算 vs 公开首年预估电量」对照'}
            </h3>
            <small style="opacity:0.78">
              ${isEn
                ? 'Note: Published figures below are official filing/media pre-estimates (not utility meter bills). All 8 cases use uniform uncalibrated loss assumptions.'
                : '口径声明：下表公开电量均源自政府官网、央企招标及权威媒体披露的首年预估口径（非电表账单），全程采用统一损耗率零调参复算，支持一键载入卫星排布'}
            </small>
          </div>
          <span class="satmap-tag" style="background:rgba(37,99,235,0.14);color:#2563eb;font-weight:700">
            ${isEn
              ? `7 Industrial Roofs Mean Diff = ${stats.industrialMapePct}% · All 8 Public Cases = ${stats.mapePct}%`
              : `${stats.industrialCount}座工业厂房均值偏差 ${stats.industrialMapePct}% · 全部${stats.count}项目均值 ${stats.mapePct}%`}
          </span>
        </div>

        <table class="satmap-table">
          <thead>
            <tr>
              <th>${isEn ? 'ID' : '编号'}</th>
              <th>${isEn ? 'Publicly Documented Project & Source' : '泰州公开示范项目名称与披露来源'}</th>
              <th>${isEn ? 'Roof & Tilt' : '屋面形式与倾角'}</th>
              <th>${isEn ? 'Published (kWp)' : '公开装机(千瓦)'}</th>
              <th>${isEn ? 'Zero-Tuning Sim (MWh)' : '零调参复算(兆瓦时)'}</th>
              <th>${isEn ? 'Published Est. (MWh)' : '公开预估电量(兆瓦时)'}</th>
              <th>${isEn ? 'Sim / Est. Yield (h)' : '复算 / 公开满发小时'}</th>
              <th>${isEn ? 'Consistency Diff' : '预估口径偏差'}</th>
              <th>${isEn ? 'Action' : '工程复用'}</th>
            </tr>
          </thead>
          <tbody>
            ${TAIZHOU_BENCHMARK_CASES.map((c) => `
              <tr data-lab-case="${c.id}" style="cursor:pointer;${c.id === selected.id ? 'background:rgba(37,99,235,0.12);font-weight:600' : ''}">
                <td><strong>${isEn ? c.id : c.id.replace('TZ-', '泰州-')}</strong></td>
                <td>
                  <div>${isEn ? c.nameEn : c.nameZh}</div>
                  <small style="opacity:0.72;font-weight:400">${isEn ? c.sourceEn : c.sourceZh}</small>
                </td>
                <td>${isEn ? c.roofTypeEn : c.roofTypeZh}</td>
                <td>${c.capacityKwp}</td>
                <td>${(c.simYieldKwh / 1000).toFixed(1)}</td>
                <td><strong>${(c.publishedYieldKwh / 1000).toFixed(1)}</strong></td>
                <td>${c.simSpecificH}${isEn ? 'h' : '小时'} / ${c.publishedSpecificH}${isEn ? 'h' : '小时'}</td>
                <td style="color:${Math.abs(c.errorPct) <= 3 ? '#059669' : '#d97706'};font-weight:700">${c.errorPct > 0 ? `+${c.errorPct.toFixed(2)}%` : `${c.errorPct.toFixed(2)}%`}</td>
                <td>
                  <button type="button" class="btn sm ${c.id === selected.id ? 'primary' : ''}" data-lab-load-case="${c.id}">
                    ${isEn ? 'Load into SatMap' : '载入至卫星排布'}
                  </button>
                </td>
              </tr>
            `).join('')}
          </tbody>
        </table>

        <div style="margin-top:12px;padding:12px 14px;border-radius:8px;background:rgba(37,99,235,0.08);border:1px solid rgba(37,99,235,0.22);display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap">
          <div>
            <strong>${isEn ? selected.id : selected.id.replace('TZ-', '泰州-')} · ${isEn ? selected.nameEn : selected.nameZh}：</strong>
            <span>${isEn ? selected.highlightEn : selected.highlightZh}（${isEn ? selected.inverterDescEn : selected.inverterDescZh}）</span>
          </div>
          <button type="button" class="btn primary sm" data-lab-load-case="${selected.id}">
            ${isEn ? 'Open This Plant in Satellite Workbench →' : '在卫星排布工作台中打开此工程 →'}
          </button>
        </div>
      </div>
    `;
  }

  bind(root) {
    root.querySelectorAll('[data-lab-tab]').forEach((btn) => {
      btn.onclick = () => {
        this.activeTab = btn.dataset.labTab;
        this.render();
      };
    });

    root.querySelectorAll('[data-lab-input]').forEach((inp) => {
      inp.oninput = () => {
        const key = inp.dataset.labInput;
        this[key] = Number(inp.value);
        this.render();
      };
    });

    root.querySelectorAll('[data-lab-cable]').forEach((btn) => {
      btn.onclick = () => {
        this.cableMaterial = btn.dataset.labCable;
        this.render();
      };
    });

    root.querySelectorAll('[data-lab-env-mode]').forEach((btn) => {
      btn.onclick = () => {
        this.domesticEnvMode = btn.dataset.labEnvMode;
        this.render();
      };
    });

    root.querySelectorAll('[data-lab-pareto-idx]').forEach((el) => {
      el.onclick = (ev) => {
        if (ev.target.closest('[data-lab-apply-idx]')) return;
        const idx = Number(el.dataset.labParetoIdx);
        this.selectedParetoIdx = idx;
        const portfolio = this.computeParetoPortfolio();
        if (portfolio[idx]) {
          this.tiltDeg = portfolio[idx].tilt;
          this.shadowCutoffPct = portfolio[idx].shadowCutoff;
          this.dcAcRatio = portfolio[idx].dcAc;
        }
        this.render();
      };
    });

    root.querySelectorAll('[data-lab-apply-idx]').forEach((btn) => {
      btn.onclick = (ev) => {
        ev.stopPropagation();
        const idx = Number(btn.dataset.labApplyIdx);
        this.applySchemeToSatmap(idx, { jump: false });
      };
    });

    root.querySelectorAll('[data-lab-action="apply-current-and-jump"]').forEach((btn) => {
      btn.onclick = () => {
        this.applySchemeToSatmap(this.selectedParetoIdx, { jump: true });
      };
    });

    root.querySelectorAll('[data-lab-action="apply-bess-to-satmap"]').forEach((btn) => {
      btn.onclick = () => {
        this.applyBessToSatmap({ jump: false });
      };
    });

    root.querySelectorAll('[data-lab-case]').forEach((row) => {
      row.onclick = (ev) => {
        if (ev.target.closest('[data-lab-load-case]')) return;
        this.selectedCaseId = row.dataset.labCase;
        this.render();
      };
    });

    root.querySelectorAll('[data-lab-load-case]').forEach((btn) => {
      btn.onclick = (ev) => {
        ev.stopPropagation();
        this.loadBenchmarkIntoSatmap(btn.dataset.labLoadCase, { jump: true });
      };
    });
  }
}
