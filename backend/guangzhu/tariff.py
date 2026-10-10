"""Jiangsu 426 rates applied to in-memory energy; persisted statistics are aggregates."""
import csv
import math
from datetime import datetime, timedelta, timezone
from .config import DATA_DIR

BANDS = ('flat', 'valley', 'peak', 'sharp', 'deep')
HOLIDAYS = (('01-21', '01-27'), ('04-29', '05-03'), ('09-29', '10-06'))


def reprice(project, basis, flat):
    import copy
    result = copy.deepcopy(basis)
    values = factors(result['tariff_class'])
    ratio = project.economics.self_use_ratio
    if ratio is not None and ratio != basis['input_self_ratio']:
        for row in result['bands'].values():
            row['self_use_kwh'] = row['generation_kwh'] * ratio
        result['load_mode'] = '手填比例均摊到各小时'
    total = result['generation_kwh']
    used = math.fsum(row['self_use_kwh'] for row in result['bands'].values())
    revenue = math.fsum(row['self_use_kwh'] * flat * values[key] for key, row in result['bands'].items())
    for cell in result['graph']:
        cell['price_cny_kwh'] = cell['price_factor'] * flat
    result.update(self_use_kwh=used, revenue_cny=revenue, effective_ratio=used / total if total else 0,
                  weighted_price_cny_kwh=revenue / used if used else 0, input_self_ratio=ratio, flat_price=flat)
    return result


def category(project):
    kva = project.requirements.structured.transformer_kva
    if kva is None and project.facts:
        kva = project.facts.transformer_kva
    inferred = 'two_part' if kva is not None and kva >= 315 else 'single_small' if kva is not None and kva < 100 else 'single100'
    return project.economics.tariff_class or inferred, bool(kva is not None and kva >= 315), kva


def factors(kind):
    with (DATA_DIR / 'catalog/tou-jiangsu.csv').open(encoding='utf-8-sig', newline='') as stream:
        return {row['band']: float(row[kind]) for row in csv.DictReader(stream)}


def band(stamp, minute, eligible, rows=None):
    month, hour = stamp.month, stamp.hour + minute / 60
    holiday = stamp.year == 2023 and any(a <= stamp.strftime('%m-%d') <= b for a, b in HOLIDAYS)
    summer_winter = month in (6, 7, 8, 12, 1, 2)
    if rows is None:
        with (DATA_DIR / 'catalog/tou-jiangsu.csv').open(encoding='utf-8-sig', newline='') as stream:
            rows = list(csv.DictReader(stream))
    specials = ['holiday'] if holiday else []
    specials += ['sharp_summer'] if month in (7, 8) else ['sharp_winter'] if month in (12, 1) else []
    if eligible:
        for season in specials:
            for row in rows:
                if row['season'] == season and float(row['start']) <= hour < float(row['end']):
                    return row['band']
    season = 'summer_winter' if summer_winter else 'spring_autumn'
    return next(row['band'] for row in rows if row['season'] == season and float(row['start']) <= hour < float(row['end']))


def integrate(project, energy, ratio, flat):
    from .economics import load_curve
    kind, eligible, kva = category(project)
    prices = factors(kind)
    hourly = energy.get('hourly')
    if hourly is None:
        raise ValueError('分时经济测算需要内存逐时发电，请重新分析')
    times, generation = hourly['utc'], hourly['kwh']
    if len(times) != len(generation) or any(not math.isfinite(v) or v < 0 for v in generation):
        raise ValueError('逐时发电数据不完整')
    if not math.isclose(math.fsum(generation), energy['p50'], rel_tol=1e-6, abs_tol=.01):
        raise ValueError('逐时发电与年度总量不一致')
    supplied = project.economics
    has_load = supplied.monthly_kwh is not None and supplied.shifts is not None
    loads = load_curve(supplied.monthly_kwh, supplied.shifts, times) if has_load else None
    physical = project.requirements.structured.export_allowed is False
    phased = bool(project.requirements.structured.phase1_kw or project.requirements.structured.phase1_budget_cny)
    automatic = has_load and (supplied.self_use_ratio is None or physical or phased)
    self_energy = [min(g, l) for g, l in zip(generation, loads)] if automatic else [g * ratio for g in generation]
    totals = {key: dict(generation_kwh=0.0, self_use_kwh=0.0) for key in BANDS}
    cells = {}
    with (DATA_DIR / 'catalog/tou-jiangsu.csv').open(encoding='utf-8-sig', newline='') as stream:
        schedule = list(csv.DictReader(stream))
    for value, consumed, timestamp in zip(generation, self_energy, times, strict=True):
        stamp = datetime.fromisoformat(timestamp).astimezone(timezone(timedelta(hours=8)))
        cell = cells.setdefault((stamp.month, stamp.hour), [0.0, 0.0, 0])
        for minute in (0, 30):
            key = band(stamp, minute, eligible, schedule)
            totals[key]['generation_kwh'] += value / 2
            totals[key]['self_use_kwh'] += consumed / 2
            cell[1] += prices[key] / 2
        cell[0] += value
        cell[2] += 1
    used = math.fsum(row['self_use_kwh'] for row in totals.values())
    revenue = math.fsum(row['self_use_kwh'] * flat * prices[key] for key, row in totals.items())
    return dict(algorithm='jiangsu426/1', tariff_class=kind, sharp_eligible=eligible, transformer_kva=kva,
                weighted_price_cny_kwh=revenue / used if used else 0, self_use_kwh=used, revenue_cny=revenue,
                effective_ratio=used / energy['p50'] if energy['p50'] else 0, generation_kwh=energy['p50'], bands=totals, schedule=schedule,
                reference_self_use_kwh=math.fsum(min(g, l) for g, l in zip(generation, loads)) if has_load else None,
                load_mode='按用电逐时算' if automatic else '手填比例均摊到各小时' if supplied.self_use_ratio is not None else '示意比例',
                input_self_ratio=supplied.self_use_ratio, flat_price=flat,
                graph=[dict(month=m, hour=h, generation_kwh=g / n, price_cny_kwh=flat * p / n, price_factor=p / n)
                       for (m, h), (g, p, n) in sorted(cells.items())],
                note=f'用电类别：{dict(two_part="两部制", single100="单一制、100千伏安及以上", single_small="单一制、100千伏安以下")[kind]}'
                     '（按变压器容量推断，没填容量时按单一制、100千伏安及以上，可在填条件页改）；'
                     f'尖峰和深谷电价{"计入" if eligible else "不计"}（315千伏安及以上的工业用户才有，须现场确认）。'
                     '时段和上下浮比例按江苏苏发改价格发〔2025〕426号文，按2023年天气和国务院2023年放假安排逐小时算；'
                     '跨半点的时段按半小时分摊（示意）。平段电价按示意值，各时段在它的基础上上下浮动'
                     '（还没取到国网江苏最新的代理购电价格表）。基本电费不算进光伏收益；已签分时零售合同的，不能再按本表叠加。'
                     '图为每个月同一小时的平均值。')
