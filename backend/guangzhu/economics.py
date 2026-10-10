"""Auditable annual cashflows; prices and factors come only from the catalog."""

import csv
import math
from pathlib import Path
from datetime import datetime, timedelta, timezone
from calendar import monthrange

from scipy.optimize import brentq

from .config import DATA_DIR
from .models import GzError

ASSUMPTIONS_PATH = DATA_DIR / "catalog" / "assumptions.csv"
PARAMETER_KEYS = ("capex_cny_per_w", "om_cny_per_w_year", "price_self_cny_kwh",
                  "price_export_cny_kwh", "self_use_ratio", "discount_rate",
                  "degradation_annual_pct", "lifetime_years", "emission_factor_kgco2_kwh",
                  "design_system_loss_pct", "national_emission_factor_kgco2_kwh")
CSV_COLUMNS = ("key", "中文名", "数值", "单位", "状态", "来源标题", "链接", "发布日期", "访问日期", "备注")


def _mapping(value):
    return value.model_dump() if hasattr(value, "model_dump") else dict(value)


def load_assumptions():
    """Load every CSV column plus numeric value; missing data never uses a preset."""
    try:
        with Path(ASSUMPTIONS_PATH).open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if tuple(reader.fieldnames or ()) != CSV_COLUMNS:
                raise ValueError("假设表列名或顺序不正确")
            records = {}
            for row in reader:
                value, key = float(row["数值"]), row["key"]
                if not key or key in records or not math.isfinite(value) or row["状态"] not in {"已查证", "示意"}:
                    raise ValueError("假设表编号、数值或状态不正确")
                if row["状态"] == "已查证" and not all(row[k] for k in ("链接", "发布日期", "访问日期")):
                    raise ValueError("已查证的假设缺少链接或日期")
                records[key] = dict(row, value=value)
            if not set(PARAMETER_KEYS) <= records.keys():
                raise ValueError("假设表缺少经济计算所需字段")
            return records
    except (OSError, UnicodeError, csv.Error, TypeError, ValueError, KeyError) as error:
        raise GzError("ASSUMPTIONS_INVALID", "经济假设表缺失或不完整", "检查data/catalog/assumptions.csv及每项来源") from error


def resolve_parameters(project):
    """Return (params, sources); a non-null project value overrides each field."""
    defaults, supplied = load_assumptions(), _mapping(_mapping(project)["economics"])
    params, sources = {}, {}
    for key in PARAMETER_KEYS:
        metadata = dict(defaults[key])
        override = supplied.get(key)
        params[key] = float(metadata["value"] if override is None else override)
        if override is None:
            metadata["basis"] = "assumptions.csv"
        else:
            metadata.update(value=params[key], 数值=str(override), 状态="示意", 来源标题="用户项目参数",
                            链接="", 发布日期="", 访问日期="", basis="project.economics",
                            备注="用户覆盖值，可修改；" + (supplied.get("assumptions_note") or ""), default_source=dict(defaults[key]))
        sources[key] = metadata
    return params, sources


def _payback(rows, key):
    if rows[0][key] >= 0:
        return 0.0
    for previous, current in zip(rows, rows[1:]):
        if previous[key] < 0 <= current[key]:
            return previous["year"] - previous[key] / (current[key] - previous[key])
    return None


def _irr(cash):
    if not min(cash) < 0 < max(cash):
        return None
    def npv(rate):
        return math.fsum(amount / (1 + rate) ** year for year, amount in enumerate(cash))
    previous, left = npv(0), 0.0
    if previous == 0:
        return 0.0
    for right in (1.0, 10.0, 100.0, 1000.0, 1e6):
        current = npv(right)
        if current == 0:
            return right * 100
        if previous * current < 0:
            return brentq(npv, left, right) * 100
        previous, left = current, right
    return brentq(npv, -.9999, 0) * 100 if npv(-.9999) * npv(0) < 0 else None


def cashflow_model(dc_kw, p50, params):
    """The shared baseline/sensitivity algorithm; percentage degradation is /100."""
    p = params
    if not all(math.isfinite(float(v)) and v >= 0 for v in (dc_kw, p50, *p.values())):
        raise ValueError("装机、发电量和经济参数须为有限非负数")
    years = int(p["lifetime_years"])
    if years != p["lifetime_years"] or years <= 0 or p["self_use_ratio"] > 1 or p["discount_rate"] >= 1 or p["degradation_annual_pct"] > 100:
        raise ValueError("年限、自用比例、折现率或衰减率范围不正确")
    capex, om = dc_kw * 1000 * p["capex_cny_per_w"], dc_kw * 1000 * p["om_cny_per_w_year"]
    rows = [dict(year=0, generation_kwh=0.0, self_use_kwh=0.0, export_kwh=0.0, income_cny=0.0,
                 om_cny=0.0, net_cny=-capex, cumulative_cny=-capex, discounted_cny=-capex, cumulative_discounted_cny=-capex)]
    energy_pv, om_pv = 0.0, 0.0
    for year in range(1, years + 1):
        generation = p50 * (1 - p["degradation_annual_pct"] / 100) ** (year - 1)
        self_use, export = generation * p["self_use_ratio"], generation * (1 - p["self_use_ratio"])
        income = self_use * p["price_self_cny_kwh"] + export * p["price_export_cny_kwh"]
        net, discount = income - om, (1 + p["discount_rate"]) ** year
        energy_pv, om_pv = energy_pv + generation / discount, om_pv + om / discount
        rows.append(dict(year=year, generation_kwh=generation, self_use_kwh=self_use, export_kwh=export,
                         income_cny=income, om_cny=om, net_cny=net, cumulative_cny=rows[-1]["cumulative_cny"] + net,
                         discounted_cny=net / discount, cumulative_discounted_cny=rows[-1]["cumulative_discounted_cny"] + net / discount))
    return dict(capex_cny=capex, payback_years=_payback(rows, "cumulative_cny"),
                dynamic_payback_years=_payback(rows, "cumulative_discounted_cny"), npv_cny=rows[-1]["cumulative_discounted_cny"],
                irr_pct=_irr([row["net_cny"] for row in rows]), lcoe_cny_kwh=(capex + om_pv) / energy_pv if energy_pv else None,
                profit_cny=rows[-1]["cumulative_cny"], operating_net_cny=math.fsum(row["net_cny"] for row in rows[1:]), cashflows=rows)


def load_curve(monthly_kwh, shifts, timestamps):
    """Illustrative Beijing-time Monday–Saturday shifts, normalized month by month."""
    stamps = [datetime.fromisoformat(value).astimezone(timezone(timedelta(hours=8))) for value in timestamps]
    if shifts == 4:
        from .livestock import fan_curve
        return fan_curve(monthly_kwh, stamps)
    weights = [1.0 if stamp.weekday() < 6 and (shifts == 3 or 8 <= stamp.hour < (17 if shifts == 1 else 24))
               else .2 for stamp in stamps]
    totals = {}
    hours = 24 if shifts == 3 else 9 if shifts == 1 else 16
    for year, month in {(stamp.year, stamp.month) for stamp in stamps}:
        days = monthrange(year, month)[1]
        working = sum(datetime(year, month, day).weekday() < 6 for day in range(1, days + 1))
        totals[year, month] = days * 24 * .2 + working * hours * .8
    return [monthly_kwh * weight / totals[(stamp.year, stamp.month)] for stamp, weight in zip(stamps, weights)]


def hourly_self_use(monthly_kwh, shifts, hourly):
    loads = load_curve(monthly_kwh, shifts, hourly['utc'])
    generation = math.fsum(hourly['kwh'])
    consumed = hourly_consumption(hourly['kwh'], loads)
    return dict(algorithm='按用电逐时算', annual_load_kwh=monthly_kwh * 12, self_use_kwh=consumed,
                surplus_kwh=generation - consumed, ratio=consumed / generation if generation else 0)


def hourly_consumption(generation, loads):
    return math.fsum(min(produced, load) for produced, load in zip(generation, loads, strict=True))


def calculate(project, dc_kw, yield_kwh, *, design=None, electric=None, load=None, sensitivity=True):
    from .economic_analysis import calculate as detailed
    return detailed(project, dc_kw, yield_kwh, design=design, electric=electric, load=load, sensitivity=sensitivity)


def plot(result, tornado_path, cashflow_path):
    """Save PNGs, marking the interpolated static and discounted payback points."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    for path in (tornado_path, cashflow_path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    base, years = result["payback_years"], result["cashflows"][-1]["year"]
    fig, ax = plt.subplots(figsize=(7, 4))
    labels = {"capex_cny_per_w": "CAPEX +/-10%", "price_self_cny_kwh": "Self-use price +/-10%",
              "self_use_ratio": "Self-use share +/-10pp", "generation_kwh": "Generation low/high"}
    center = base if base is not None else years + 1
    def span(key):
        values = [row["payback_years"] if row["payback_years"] is not None else years + 1
                  for row in result["sensitivity"] if row["variable"] == key]
        return max(values) - min(values)
    ordered = sorted(labels, key=span)
    for index, key in enumerate(ordered):
        for scenario in [row for row in result["sensitivity"] if row["variable"] == key]:
            value = scenario["payback_years"]
            drawn = value if value is not None else years + 1
            ax.barh(index, drawn - center, left=center, height=.5, alpha=.65,
                    color="#356f96" if scenario["direction"] == "low" else "#e7a244")
            ax.annotate(f"{value:.2f}" if value is not None else f">{years} (no payback)", (drawn, index), fontsize=8)
    ax.set_yticks(range(len(labels)), [labels[key] for key in ordered])
    ax.axvline(center, color="black", linestyle="--", label="Baseline" if base is not None else "Baseline: no payback")
    ax.set(xlabel="Static payback (years)", title="Payback sensitivity")
    ax.legend()
    fig.tight_layout()
    fig.savefig(tornado_path, dpi=160)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(7, 4))
    for key, payback, label in (("cumulative_cny", "payback_years", "Cumulative"),
                                ("cumulative_discounted_cny", "dynamic_payback_years", "Discounted cumulative")):
        ax.plot([row["year"] for row in result["cashflows"]], [row[key] / 10000 for row in result["cashflows"]], label=label)
        point = result[payback]
        if point is not None:
            ax.scatter([point], [0], zorder=3)
            ax.annotate(f"{label} payback: {point:.2f}y", (point, 0), xytext=(8, 12 if payback == "payback_years" else -24), textcoords="offset points", fontsize=8)
    ax.axhline(0, color="black", linewidth=.7)
    ax.set(xlabel="Year", ylabel="Cashflow (10,000 CNY)", title="Project cumulative cashflow")
    ax.legend()
    fig.tight_layout()
    fig.savefig(cashflow_path, dpi=160)
    plt.close(fig)


def check_requirements_consistency(structured, project, *, max_capacity_kw=None, best_payback_years=None):
    req, missing, contradictions = _mapping(structured), [], []
    budget, payback = req.get("budget_cny_max"), req.get("payback_years_max")
    lower, upper = req.get("capacity_kw_min"), req.get("capacity_kw_max")
    for absent, message in ((budget is None, "建议补充最高预算（元），以判断造价是否可接受。"),
                            (payback is None, "建议补充最长回本年限，以判断收益是否符合要求。"),
                            (lower is None and upper is None, "建议补充装机容量下限或上限（千瓦）。")):
        if absent:
            missing.append(message)
    if lower is not None and upper is not None and lower > upper:
        contradictions.append(f"装机下限{lower:g}千瓦大于上限{upper:g}千瓦。")
    if budget is not None and lower is not None:
        from .costs import catalog
        manual = _mapping(_mapping(project)['economics']).get('capex_cny_per_w')
        prices = catalog()
        price = manual if manual is not None else prices['module']['value'] + prices['installation']['value']
        minimum = lower * 1000 * price
        basis = '手填单位造价' if manual is not None else '仅组件及施工的保守下界，不含其他非负分项（示意）'
        if budget < minimum:
            contradictions.append(f'预算{budget:g}元低于装机下限{lower:g}千瓦至少所需的{minimum:g}元（{basis}{price:g}元/瓦）。')
    if lower is not None and max_capacity_kw is not None and lower > max_capacity_kw:
        contradictions.append(f"装机下限{lower:g}千瓦超过屋顶最多可装的{max_capacity_kw:g}千瓦。")
    if payback is not None and best_payback_years is not None and payback < best_payback_years:
        contradictions.append(f"要求{payback:g}年内回本，快于当前条件下最快的{best_payback_years:g}年。")
    return dict(missing=missing, contradictions=contradictions)
