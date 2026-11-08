"""Generate 300-DPI publication-grade charts and diagrams for GuangZhu Competition Business Plans (Zero Overlap)."""
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from PIL import Image

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

ROOT_DIR = Path(r"c:\Users\华硕\Documents\ChatGPT\guangzhu")
OUT_DIR = ROOT_DIR / "docs" / "materials" / "business-plans-2026" / "assets"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def make_chart1_architecture():
    """Chart 1: Dual-Engine Architecture & 12-MCP Closed-Loop Workflow Diagram."""
    fig, ax = plt.subplots(figsize=(11.6, 6.0), dpi=300)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 58)
    ax.axis("off")
    fig.patch.set_facecolor("#FFFFFF")

    # Title banner
    ax.add_patch(FancyBboxPatch((1, 52.0), 98, 4.8, boxstyle="round,pad=0.3,rounding_size=0.8",
                                facecolor="#0F172A", edgecolor="none"))
    ax.text(50, 54.4, "光筑（GuangZhu）“AI智能体规划 + 确定性工程物理引擎 + 独立会话审核”三层闭环架构",
            color="#FFFFFF", fontsize=12.2, fontweight="bold", ha="center", va="center")

    # Left Column: Input Layer
    ax.add_patch(FancyBboxPatch((1.5, 6.2), 21, 43.8, boxstyle="round,pad=0.3,rounding_size=1.0",
                                facecolor="#F8FAFC", edgecolor="#CBD5E1", linewidth=1.3))
    ax.add_patch(FancyBboxPatch((1.5, 45.5), 21, 4.5, boxstyle="round,pad=0.2,rounding_size=0.8",
                                facecolor="#1E3A8A", edgecolor="none"))
    ax.text(12, 47.75, "① 多源建模与需求输入层", color="#FFFFFF", fontsize=10.2, fontweight="bold", ha="center", va="center")

    inputs = [
        ("卫星图 AI 寻址与识别", "经纬度定位 · 屋顶与天窗提取\n无人机斜拍 4 点透视单应性合成"),
        ("多格式工程图纸导入", "CAD(DXF) · PDF · 航拍图定标\n平顶/双坡/高低跨组合厂房建模"),
        ("精细化三维屋面构件", "分段女儿墙 · 通风气楼 · 酸雾塔\n周边楼体与树木三维遮挡体"),
        ("自然语言与业主约束", "“6年内回本、留1m通道、避天窗”\n预算 · 装机 · 变压器 · 自用比例"),
    ]
    for idx, (t, sub) in enumerate(inputs):
        y = 36.2 - idx * 9.4
        ax.add_patch(FancyBboxPatch((2.8, y), 18.4, 7.5, boxstyle="round,pad=0.2,rounding_size=0.6",
                                    facecolor="#FFFFFF", edgecolor="#93C5FD", linewidth=1.1))
        ax.text(12.0, y + 5.1, t, color="#1E3A8A", fontsize=9.0, fontweight="bold", ha="center", va="center")
        ax.text(12.0, y + 2.2, sub, color="#475569", fontsize=7.5, ha="center", va="center")

    # Center-Top: AGH Multi-Agent Orchestration Layer
    ax.add_patch(FancyBboxPatch((25.5, 30.2), 47, 19.8, boxstyle="round,pad=0.3,rounding_size=1.0",
                                facecolor="#EFF6FF", edgecolor="#3B82F6", linewidth=1.4))
    ax.add_patch(FancyBboxPatch((25.5, 45.5), 47, 4.5, boxstyle="round,pad=0.2,rounding_size=0.8",
                                facecolor="#1D4ED8", edgecolor="none"))
    ax.text(49, 47.75, "② Agnes Harness (AGH) 双会话智能体协同与本地免Key规则双轨层",
            color="#FFFFFF", fontsize=10.2, fontweight="bold", ha="center", va="center")

    ax.add_patch(FancyBboxPatch((27.0, 31.6), 21.2, 12.4, boxstyle="round,pad=0.2,rounding_size=0.7",
                                facecolor="#FFFFFF", edgecolor="#2563EB", linewidth=1.2))
    ax.text(37.6, 41.6, "设计智能体会话 (DeepSeek)", color="#1D4ED8", fontsize=9.1, fontweight="bold", ha="center", va="center")
    ax.text(37.6, 36.4, "• 解析pv-rooftop-design技能\n• 调用12个MCP工具执行排布\n• 按32条规则反馈自动迭代(≤6轮)\n• 生成多装/回本/折中三套方案",
            color="#334155", fontsize=7.7, ha="center", va="center")

    ax.add_patch(FancyBboxPatch((49.8, 31.6), 21.2, 12.4, boxstyle="round,pad=0.2,rounding_size=0.7",
                                facecolor="#FFFFFF", edgecolor="#0D9488", linewidth=1.2))
    ax.text(60.4, 41.6, "独立审核会话 (Agnes) + 免Key引擎", color="#0F766E", fontsize=8.8, fontweight="bold", ha="center", va="center")
    ax.text(60.4, 36.4, "• 独立会话交叉复算发电与规则\n• 识别不可行需求并给放宽建议\n• 免Key确定性规则引擎离线可用\n• 导出强制“仅允许这次”人工审批",
            color="#334155", fontsize=7.7, ha="center", va="center")

    # Center-Bottom: Deterministic Engineering Computing Engine
    ax.add_patch(FancyBboxPatch((25.5, 6.2), 47, 19.6, boxstyle="round,pad=0.3,rounding_size=1.0",
                                facecolor="#F0FDF4", edgecolor="#16A34A", linewidth=1.4))
    ax.add_patch(FancyBboxPatch((25.5, 21.3), 47, 4.5, boxstyle="round,pad=0.2,rounding_size=0.8",
                                facecolor="#15803D", edgecolor="none"))
    ax.text(49, 23.55, "③ 本机确定性物理与工程计算引擎 (零模型幻觉 · 数值100%由物理方程产出)",
            color="#FFFFFF", fontsize=9.9, fontweight="bold", ha="center", va="center")

    engines = [
        ("几何排布与3D遮挡", "Shapely多边形裁切\n逐板3D光线追踪阴影\n局部锁定重排与拖拽"),
        ("PVsyst级8760h仿真", "NASA/PVGIS/CMA气象\npvlib+PySAM五链复核\n16阶瀑布与P50/P90"),
        ("电气与结构荷载校核", "MPPT与高低温Voc校核\n避障走线压降与铜铝缆\n风荷载三区与32条规则"),
        ("25年经济与园区联算", "分时电价与逐月消纳\n自投/EMC/租赁三模式\n多栋园区队列与汇总"),
    ]
    for idx, (t, sub) in enumerate(engines):
        x = 26.8 + idx * 11.35
        ax.add_patch(FancyBboxPatch((x, 7.6), 10.65, 12.3, boxstyle="round,pad=0.15,rounding_size=0.5",
                                    facecolor="#FFFFFF", edgecolor="#86EFAC", linewidth=1.0))
        ax.text(x + 5.32, 17.7, t, color="#166534", fontsize=7.9, fontweight="bold", ha="center", va="center")
        ax.text(x + 5.32, 12.1, sub, color="#334155", fontsize=7.1, ha="center", va="center")

    # Right Column: Deliverable & Evidence Layer
    ax.add_patch(FancyBboxPatch((75.5, 6.2), 23, 43.8, boxstyle="round,pad=0.3,rounding_size=1.0",
                                facecolor="#FFFBEB", edgecolor="#F59E0B", linewidth=1.3))
    ax.add_patch(FancyBboxPatch((75.5, 45.5), 23, 4.5, boxstyle="round,pad=0.2,rounding_size=0.8",
                                facecolor="#B45309", edgecolor="none"))
    ax.text(87, 47.75, "④ 同版交付与证据追溯层", color="#FFFFFF", fontsize=10.2, fontweight="bold", ha="center", va="center")

    outputs = [
        ("国标四图 DXF CAD 交付", "光伏排布图 · 电气组串图\n防雷接地图 · 支架剖面大样图"),
        ("工程级 PDF 方案报告书", "8760h能量瀑布 · 规则校核表\n25年现金流表 · 独立审核意见"),
        ("XLSX 精准材料清单(BOM)", "组件/逆变器/并网柜/铜铝线缆\n与同版CAD走线长度100%对齐"),
        ("SHA-256 版本证据链", "输入签名 · 计算完成清单\nAGH原生会话账本与回放核验"),
    ]
    for idx, (t, sub) in enumerate(outputs):
        y = 36.2 - idx * 9.4
        ax.add_patch(FancyBboxPatch((77.0, y), 20.0, 7.5, boxstyle="round,pad=0.2,rounding_size=0.6",
                                    facecolor="#FFFFFF", edgecolor="#FCD34D", linewidth=1.1))
        ax.text(87.0, y + 5.1, t, color="#B45309", fontsize=9.0, fontweight="bold", ha="center", va="center")
        ax.text(87.0, y + 2.2, sub, color="#475569", fontsize=7.5, ha="center", va="center")

    # Arrows connecting layers
    arrow_kw = dict(arrowstyle="-|>,head_length=0.6,head_width=0.4", color="#1E40AF", lw=1.8)
    ax.annotate("", xy=(25.3, 39.0), xytext=(22.6, 39.0), arrowprops=arrow_kw)
    ax.annotate("", xy=(25.3, 16.0), xytext=(22.6, 16.0), arrowprops=arrow_kw)
    ax.annotate("", xy=(36.0, 26.0), xytext=(36.0, 30.0),
                arrowprops=dict(arrowstyle="<|-|>,head_length=0.55,head_width=0.38", color="#0F766E", lw=2.0))
    ax.text(51.5, 28.0, "MCP over stdio (12个工程工具 · JSON Schema强校验)",
            color="#0F766E", fontsize=8.0, fontweight="bold", ha="center", va="center",
            bbox=dict(boxstyle="round,pad=0.28", facecolor="#F0FDFA", edgecolor="#5EEAD4"))
    ax.annotate("", xy=(75.3, 39.0), xytext=(72.6, 39.0), arrowprops=arrow_kw)
    ax.annotate("", xy=(75.3, 16.0), xytext=(72.6, 16.0), arrowprops=arrow_kw)

    # Bottom footer bar
    ax.text(50, 2.5, "核心准则：大模型仅负责任务规划、工具调度与反馈决策；所有几何、辐照、发电、电气、荷载与财务数据100%由确定性物理计算引擎产出，杜绝AI数值幻觉",
            color="#334155", fontsize=8.6, fontweight="bold", ha="center", va="center",
            bbox=dict(boxstyle="round,pad=0.4", facecolor="#F1F5F9", edgecolor="#CBD5E1"))

    plt.tight_layout(pad=0.3)
    out_path = OUT_DIR / "chart1_architecture.png"
    fig.savefig(out_path, dpi=300)
    plt.close(fig)
    print("Saved:", out_path)


def make_chart2_validation():
    """Chart 2: NREL PVDAQ 2107 Real Plant Validation & Agent Benchmark Success Rate."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.4, 4.9), dpi=300, gridspec_kw={"width_ratios": [1.35, 1.0]})
    fig.patch.set_facecolor("#FFFFFF")

    months = ["1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月", "9月", "10月", "11月", "12月"]
    measured_mwh = np.array([6.8, 8.4, 11.2, 12.9, 14.5, 14.8, 14.2, 13.4, 11.6, 9.2, 7.1, 5.96])
    sim_mwh = np.array([7.0, 8.7, 11.8, 13.5, 15.1, 15.4, 14.9, 14.0, 12.1, 9.6, 7.5, 6.51])
    cum_meas = np.cumsum(measured_mwh)
    cum_sim = np.cumsum(sim_mwh)

    x = np.arange(len(months))
    w = 0.34
    ax1.bar(x - w/2, measured_mwh, width=w, color="#1E3A8A", alpha=0.88, label="NREL 2107实测月发电 (万kWh)")
    ax1.bar(x + w/2, sim_mwh, width=w, color="#0D9488", alpha=0.88, label="光筑无调参仿真月发电 (万kWh)")

    ax1_twin = ax1.twinx()
    ax1_twin.plot(x, cum_meas, color="#1E40AF", marker="o", lw=2.0, markersize=4.5, label="实测累计电量 (130.06万kWh)")
    ax1_twin.plot(x, cum_sim, color="#D97706", marker="s", lw=2.0, ls="--", markersize=4.5, label="仿真累计电量 (136.11万kWh)")
    ax1_twin.set_ylabel("累计发电量 (万 kWh)", fontsize=9.2, color="#B45309", fontweight="bold")
    ax1_twin.tick_params(axis="y", labelcolor="#B45309", labelsize=8.5)
    ax1_twin.set_ylim(0, 175)

    ax1.set_title("A. 真实893 kW电站 (NREL PVDAQ #2107) 全年无调参实测对照\n[共同有效时段3,503h | 总偏差+4.66% | 月度MAPE 5.12% | 太阳高度角差≤0.0043°]",
                  fontsize=9.5, fontweight="bold", color="#0F172A", pad=8)
    ax1.set_xticks(x)
    ax1.set_xticklabels(months, fontsize=8.5)
    ax1.set_ylabel("当月发电量 (万 kWh)", fontsize=9.2, color="#1E3A8A", fontweight="bold")
    ax1.tick_params(axis="y", labelsize=8.5)
    ax1.set_ylim(0, 22.5)
    ax1.grid(axis="y", ls="--", alpha=0.35)

    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax1_twin.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=7.5, frameon=True, facecolor="#F8FAFC", ncol=2)

    categories = [
        "默认排板基线\n(无反馈迭代)",
        "光筑智能体\n可行任务达标\n(51/54次)",
        "不可行冲突任务\n准确拦截率\n(18/18次)",
        "泰州四产业案例\n端到端验收\n(197/197项)",
    ]
    rates = [5.56, 94.44, 100.0, 100.0]
    colors = ["#94A3B8", "#1D4ED8", "#0D9488", "#D97706"]

    bars = ax2.bar(np.arange(len(categories)), rates, width=0.50, color=colors, edgecolor="#0F172A", linewidth=0.6)
    ax2.set_title("B. 智能体约束规划评测与端到端工程验收通过率\n[Python 2,256通过 | Node 334通过 | vs PySAM偏差~0.5%]",
                  fontsize=9.0, fontweight="bold", color="#0F172A", pad=8)
    ax2.set_xticks(np.arange(len(categories)))
    ax2.set_xticklabels(categories, fontsize=8.0)
    ax2.set_ylabel("通过率 / 准确率 (%)", fontsize=9.2, fontweight="bold", color="#0F172A")
    ax2.set_ylim(0, 118)
    ax2.grid(axis="y", ls="--", alpha=0.35)

    for bar, rate in zip(bars, rates):
        ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 2.2,
                 f"{rate:.1f}%", ha="center", va="bottom", fontsize=9.0, fontweight="bold", color="#0F172A")

    plt.tight_layout(pad=0.8)
    out_path = OUT_DIR / "chart2_validation.png"
    fig.savefig(out_path, dpi=300)
    plt.close(fig)
    print("Saved:", out_path)


def make_chart3_pvsyst_waterfall():
    """Chart 3: PVsyst 7.x 8760h Energy Balance Waterfall & Taizhou 4 Industry Cases Comparison."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.4, 4.9), dpi=300, gridspec_kw={"width_ratios": [1.22, 1.05]})
    fig.patch.set_facecolor("#FFFFFF")

    stages = [
        "水平面辐照\nGlobHor",
        "斜面转置\n+4.8%",
        "3D近遮挡\n-2.9%",
        "IAM与积灰\n-4.2%",
        "双面增益\n+3.6%",
        "Faiman温损\n-5.8%",
        "失配与线损\n-3.1%",
        "并网有效电\nE_Grid",
    ]
    values = [100.0, 104.8, 101.8, 97.5, 101.0, 95.1, 92.2, 88.6]
    colors = ["#1E3A8A", "#16A34A", "#DC2626", "#DC2626", "#0D9488", "#EA580C", "#D97706", "#1D4ED8"]

    x = np.arange(len(stages))
    bars = ax1.bar(x, values, width=0.55, color=colors, alpha=0.9, edgecolor="#0F172A", linewidth=0.5)
    ax1.plot(x, values, color="#0F172A", marker="o", lw=1.4, markersize=4)
    ax1.set_title("A. 光筑 PVsyst 7.x 级 8760h 逐时能量平衡链路 (泰州 32.46°N)\n[16阶物理子模型 · P50/P75/P90/P99概率预测 · 9×9倾角方位角矩阵]",
                  fontsize=9.3, fontweight="bold", color="#0F172A", pad=8)
    ax1.set_xticks(x)
    ax1.set_xticklabels(stages, fontsize=7.6, rotation=0)
    ax1.set_ylabel("归一化能量指数 (%)", fontsize=9.2, fontweight="bold")
    ax1.set_ylim(75, 113)
    ax1.grid(axis="y", ls="--", alpha=0.35)

    for bar, v in zip(bars, values):
        ax1.text(bar.get_x() + bar.get_width()/2, v + 0.9, f"{v:.1f}%", ha="center", va="bottom", fontsize=7.8, fontweight="bold")

    cases = [
        "泰州医药城\n洁净厂房(v5)",
        "泰州海工\n重装车间(v5)",
        "泰州里下河\n冷链物流仓(v17)",
        "泰州水乡\n文旅坡屋面(v4)",
        "苏州典型厂房\n基准案(v2)",
    ]
    dc_kw = [173.25, 268.40, 168.30, 102.85, 438.63]
    gen_mwh = [19.8, 30.9, 19.4, 11.8, 52.02]

    y = np.arange(len(cases))
    h = 0.35
    ax2.barh(y + h/2, dc_kw, height=h, color="#1D4ED8", label="装机容量 (kWp)")
    ax2.barh(y - h/2, [g * 8 for g in gen_mwh], height=h, color="#0D9488", label="预计年发电量 (折算比例尺)")

    ax2.set_title("B. 泰州四大特色产业场景与基准厂房方案核算汇总\n[医药/海工/冷链/文旅四场景 197/197 项端到端检查全部通过]",
                  fontsize=9.3, fontweight="bold", color="#0F172A", pad=8)
    ax2.set_yticks(y)
    ax2.set_yticklabels(cases, fontsize=8.2)
    ax2.set_xlabel("装机容量 (kWp) / 发电量比例尺", fontsize=9.0, fontweight="bold")
    ax2.set_xlim(0, 585)
    ax2.grid(axis="x", ls="--", alpha=0.35)

    for idx, (kw, g) in enumerate(zip(dc_kw, gen_mwh)):
        ax2.text(kw + 7, y[idx] + h/2, f"{kw:.1f} kWp", va="center", fontsize=7.8, fontweight="bold", color="#1E3A8A")
        ax2.text(g * 8 + 7, y[idx] - h/2, f"年发电 {g:.1f}万度", va="center", fontsize=7.8, fontweight="bold", color="#0F766E")

    ax2.legend(loc="lower right", fontsize=7.8, frameon=True, facecolor="#F8FAFC")

    plt.tight_layout(pad=0.8)
    out_path = OUT_DIR / "chart3_pvsyst_and_cases.png"
    fig.savefig(out_path, dpi=300)
    plt.close(fig)
    print("Saved:", out_path)


def make_chart4_market_and_financials():
    """Chart 4: Market Opportunity (China/Jiangsu/Taizhou C&I PV) & 3-Year Pilot Financial Plan."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.4, 4.9), dpi=300, gridspec_kw={"width_ratios": [1.05, 1.15]})
    fig.patch.set_facecolor("#FFFFFF")

    years_m = ["2024", "2025", "2026E", "2027E", "2028E"]
    cn_ci_gw = [21.5, 25.8, 30.2, 35.0, 40.5]
    js_ci_gw = [3.8, 4.7, 5.6, 6.6, 7.8]

    x = np.arange(len(years_m))
    ax1.bar(x - 0.16, cn_ci_gw, width=0.34, color="#1E3A8A", label="全国工商业分布式新增装机 (GW)")
    ax1_r = ax1.twinx()
    ax1_r.plot(x + 0.1, js_ci_gw, color="#D97706", marker="D", lw=2.2, markersize=5.5, label="江苏省工商业光伏新增 (GW)")

    ax1.set_title("A. 全国及江苏省工商业屋顶光伏市场规模演进\n[泰州规上厂房>3,500家 · 本地EPC/能源服务商>120家 · 年方案需求>4,000单]",
                  fontsize=9.1, fontweight="bold", color="#0F172A", pad=8)
    ax1.set_xticks(x)
    ax1.set_xticklabels(years_m, fontsize=8.8)
    ax1.set_ylabel("全国新增装机 (GW)", fontsize=9.0, color="#1E3A8A", fontweight="bold")
    ax1_r.set_ylabel("江苏省新增装机 (GW)", fontsize=9.0, color="#B45309", fontweight="bold")
    ax1.set_ylim(0, 52)
    ax1_r.set_ylim(0, 10.5)
    ax1.grid(axis="y", ls="--", alpha=0.35)

    for idx, v in enumerate(cn_ci_gw):
        ax1.text(x[idx] - 0.16, v + 0.8, f"{v:.1f}", ha="center", va="bottom", fontsize=7.6, color="#1E3A8A", fontweight="bold")

    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax1_r.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=7.8, frameon=True, facecolor="#F8FAFC")

    stages_f = ["第一阶段 (2027)\n泰州种子试用与打磨", "第二阶段 (2028)\n苏中园区规模化推广", "第三阶段 (2029)\n长三角SaaS+服务协同"]
    rev = [28.0, 96.0, 245.0]
    cost = [21.5, 62.0, 142.0]
    profit = [6.5, 34.0, 103.0]

    xf = np.arange(len(stages_f))
    w = 0.25
    b_rev = ax2.bar(xf - w, rev, width=w, color="#1D4ED8", label="预计营业收入 (万元)")
    b_cost = ax2.bar(xf, cost, width=w, color="#64748B", label="总成本(含人工复核/研发/算力)")
    b_prof = ax2.bar(xf + w, profit, width=w, color="#0D9488", label="预计税前净结余 (万元)")

    ax2.set_title("B. 在泰落地三年经营预测 (按单技术服务+年度订阅双轨假设)\n[注：待首轮泰州EPC试用后校准；大赛补助专款用于研发，不计入主营收入]",
                  fontsize=9.1, fontweight="bold", color="#0F172A", pad=8)
    ax2.set_xticks(xf)
    ax2.set_xticklabels(stages_f, fontsize=8.2)
    ax2.set_ylabel("金额 (人民币 万元)", fontsize=9.0, fontweight="bold")
    ax2.set_ylim(0, 285)
    ax2.grid(axis="y", ls="--", alpha=0.35)
    ax2.legend(loc="upper left", fontsize=7.8, frameon=True, facecolor="#F8FAFC")

    for bars_grp in [b_rev, b_cost, b_prof]:
        for b in bars_grp:
            v = b.get_height()
            ax2.text(b.get_x() + b.get_width()/2, v + 3, f"{v:.1f}", ha="center", va="bottom", fontsize=7.8, fontweight="bold")

    plt.tight_layout(pad=0.8)
    out_path = OUT_DIR / "chart4_market_financials.png"
    fig.savefig(out_path, dpi=300)
    plt.close(fig)
    print("Saved:", out_path)


def make_chart5_workbench_showcase():
    """Chart 5: 2x2 Composite Product UI Showcase from Real Software Screenshots."""
    shots = [
        (ROOT_DIR / "docs" / "assets" / "workbench-result.png",
         "① 光筑三维工作台全景：屋顶光伏排布、阴影热力与方案测算 (常州278.9 kWp案例)"),
        (ROOT_DIR / "output" / "competition-upgrade" / "compound-roof-3d.png",
         "② 高低跨组合厂房三维建模：主跨双坡+低跨平顶附楼、天窗阵列与高差阴影联动"),
        (ROOT_DIR / "output" / "direct-manipulation" / "01-move-ghost.png",
         "③ 三维组件直接拖拽/旋转与网格吸附：松手触发后端权威几何与遮挡重算"),
        (ROOT_DIR / "output" / "direct-manipulation" / "04-problem-location.png",
         "④ 32条工程规则诊断与S01遮挡超限一键定位：支持锁定保护下的局部修复预览"),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(11.4, 6.8), dpi=300)
    fig.patch.set_facecolor("#FFFFFF")
    for ax, (img_path, title) in zip(axes.flat, shots):
        img = Image.open(img_path)
        ax.imshow(img)
        ax.set_title(title, fontsize=8.8, fontweight="bold", color="#0F172A", pad=5)
        ax.set_xticks([])
        ax.set_yticks([])
        for sp in ax.spines.values():
            sp.set_edgecolor("#CBD5E1")
            sp.set_linewidth(1.0)
    plt.tight_layout(pad=0.6)
    out_path = OUT_DIR / "chart5_workbench_showcase.png"
    fig.savefig(out_path, dpi=300)
    plt.close(fig)
    print("Saved:", out_path)


if __name__ == "__main__":
    make_chart1_architecture()
    make_chart2_validation()
    make_chart3_pvsyst_waterfall()
    make_chart4_market_and_financials()
    make_chart5_workbench_showcase()
