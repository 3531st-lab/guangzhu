"""T22: the owner's answers before construction become eight plain checks; the two reminder lines are illustrative, not rules."""

AGE_YEARS, TRANSFORMER_SHARE = 10, 0.8  # 示意提醒线
ROOFS = dict(concrete="混凝土平屋顶", metal="彩钢瓦屋面", other="其他屋面")
CORES = {"none": "不是夹芯板屋面", "rockwool": "岩棉芯夹芯板，芯材不燃", "foam": "泡沫芯夹芯板：聚苯、聚氨酯可燃，装之前要问当地消防的要求，可能要换板"}


def _answers(facts):
    return facts.model_dump() if hasattr(facts, "model_dump") else dict(facts or {})


def rows(facts, summary=None, params=None, roof_type="flat", requirements=None, roof=None):
    """Each check is ok, risk or ask (left blank); a risk text starts with a short name, then '：'."""
    f, s, p, out = _answers(facts), summary or {}, params or {}, []
    share = p.get("self_use_ratio")

    def add(item, status, text):
        out.append(dict(item=item, status=status, text=text))
    kind, age, core = f.get("roof_type"), f.get("roof_age_years"), f.get("core")
    add("屋面类型", "ask" if kind is None else "ok" if kind == "concrete" else "risk",
        "开工前确认是不是混凝土平屋顶" if kind is None else "混凝土平屋顶，和本方案的压块支架一致" if kind == "concrete" else
        ROOFS[kind] + "：本方案按混凝土平屋顶压块算，" + ("彩钢瓦要顺坡平铺、用夹具，" if kind == "metal" else "") + "排板、造价和荷载都要重算")
    if roof_type == "metal":
        out[0] = dict(item="屋面类型", status="ask" if kind is None else "ok" if kind == "metal" else "risk",
                      text="开工前确认是不是彩钢瓦屋面" if kind is None else "彩钢瓦屋面，本方案按顺坡平铺、夹具算" if kind == "metal" else
                      f"屋面类型不一致：问答说{ROOFS[kind]}，屋顶资料是彩钢瓦屋面")
    if roof_type == 'pitched':
        out[0] = dict(item='屋面类型', status='ask',
                      text='整栋斜屋面按逐面材料顺坡安装：彩钢瓦用夹具、混凝土用固定导轨锚固、玻璃不装；逐面核实材料与承重。')
    add("屋面年限", "ask" if age is None else "risk" if age >= AGE_YEARS else "ok", "问清屋面用了几年：防水和锈蚀情况决定要不要先翻新" if age is None else
        f"屋面已用 {age:g} 年：光伏要用 25 年（到时屋面 {age + 25:g} 年），" + ("先查防水和锈蚀，要翻新就在装之前做（10 年是示意提醒线）"
                                                                if age >= AGE_YEARS else "中途屋面大修要先拆再装，留出这笔钱"))
    add("夹芯板", "ask" if core is None else "risk" if core == "foam" else "ok", "问清是不是夹芯板、芯材是什么：泡沫芯可燃，影响能不能装" if core is None else CORES[core])
    for item, key, bad, blank, good, risky in (
            ("采光带", "skylights", True, "问清有没有采光带：采光带不能压，要画成禁区", "没有采光带", "有采光带：在屋顶图上画成禁区，组件不能压、施工不能踩"),
            ("厂房产权", "owned", False, "问清厂房是不是自己的：租的要房东同意", "厂房是自己的", "厂房是租的：要房东书面同意，租期最好覆盖 25 年，不然搬走时要拆")):
        value = f.get(key)
        add(item, "ask" if value is None else "risk" if value is bad else "ok", blank if value is None else risky if value is bad else good)
    kva, ratio, kwh = f.get("transformer_kva"), (s.get("electrical") or {}).get("dc_ac_ratio"), (s.get("yield_kwh") or {}).get("p50")
    cap = (requirements or {}).get('transformer_kva')
    share_limit = (requirements or {}).get('transformer_share') or .8
    if cap is not None:
        kva = cap
    ac = s["dc_kw"] / ratio if s.get("dc_kw") and ratio else None
    ac = (s.get('electrical') or {}).get('rated_ac_kw', ac)
    if kva is None or ac is None:
        add("变压器", "ask" if kva is None else "ok", "问厂里电工变压器多大：逆变器合计不能超过变压器能接的量" if kva is None else f"变压器 {kva:g} kVA，方案出来后对照逆变器容量")
    else:
        level = "逆变器超过变压器：" if ac > kva else "逆变器接近变压器容量：" if ac > TRANSFORMER_SHARE * kva else ""
        add("变压器", "risk" if level else "ok", level + f"逆变器合计 {ac:,.0f} kW，是变压器 {kva:,.0f} kVA 的 {ac / kva:.0%}" +
            ("，接不进去，要减装机或给变压器扩容" if ac > kva else "，要问供电公司能接多少（80% 是示意提醒线）" if level else ""))
    if cap is not None and ac is not None:
        out[-1] = dict(item='变压器', status='ok' if ac <= cap * share_limit + 1e-9 else 'risk',
                       text=f'逆变器合计{ac:g}kW；同U06上限{cap:g}×{share_limit:g}={cap * share_limit:g}kW（比例为示意）')
    monthly = f.get("monthly_kwh")
    single = "；单班按周一至周六8–17时生产，其余时段按20%示意负荷；余电上网或被限" if f.get("shifts") == 1 else ""
    if (s.get('economics') or {}).get('self_use_ratio') is not None:
        add("用电量", "ok", "已按月用电量和班次逐时算自用比例；手填比例优先；班次负荷和非生产20%负荷是示意")
        if any((requirements or {}).get(k) is not None for k in ('phase1_kw', 'phase1_budget_cny')) or (requirements or {}).get('export_allowed') is False:
            out[-1]['text'] = '分期/不上网按逐时发电与共用负荷计算，覆盖手填比例；班次负荷和非生产20%负荷是示意'
    elif monthly is None or kwh is None:
        add("用电量", "ask" if monthly is None else "ok", (f"账里的自用比例 {share:.0%} 是估的，填了月用电量才能看合不合理" if share is not None
                     else "填了月用电量才能看自用比例合不合理") if monthly is None else f"工厂一年约用 {monthly * 12 / 1e4:,.1f} 万度，方案出来后对照发电量" + single)
    else:
        high = share is not None and share > monthly * 12 / kwh
        add("用电量", "risk" if high else "ok", ("自用比例偏高：" if high else "") + f"光伏一年约发 {kwh / 1e4:,.1f} 万度，是工厂一年用电（{monthly * 12 / 1e4:,.1f} 万度）的 "
            f"{kwh / monthly / 12:.0%}" + (f"；自用比例最多约 {monthly * 12 / kwh:.0%}，账里按 {share:.0%} 算，回本会变长" if high else "") + single)
    export, price = f.get("export_allowed"), p.get("price_export_cny_kwh")
    add("余电上网", "ask" if export is None else "ok" if export else "risk", "问供电公司能不能余电上网：有的地方只能自用" if export is None else
        "可以余电上网" + (f"；新建项目的上网电价按市场价，账里的 {price:g} 元/度是占位" if price is not None else "") if export else
        "只能自用不上网：要装防逆流，用不完的电被限掉" + ("；余电已按 0 元算" if price == 0 else
        f"；账里有 {1 - share:.0%} 的电按上网算了收入，实际拿不到，回本会变长" if share is not None and share < 1 else ""))
    if ac is not None:
        from .costs import voltage
        add('并网电压', 'ask', voltage(ac) + '（阈值示意）；按逆变器交流合计建议，须当地电网核定，四可能力要落实。')
    if roof_type in ('ground', 'carport'):
        out = out[5:]
        out.insert(0, dict(item='新建安装', status='ask', text='基础与支架或车棚钢结构由厂家设计；地勘、风荷载及接网条件待核实'))
        if roof_type == 'ground':
            land = f.get('land_type')
            forbidden = land in ('cultivated', 'permanent')
            out.insert(1, dict(item='土地性质', status='risk' if forbidden else 'ask',
                text='不能建：新建光伏方阵不得占用任何耕地，含一般耕地和永久基本农田（自然资办发〔2023〕12号）' if forbidden else
                '向当地自然资源及林草主管部门核实用地与手续；基本草原、保护林地和生态红线另受限制，其他土地不自动允许'))
            out.insert(2, dict(item='备案类别', status='ask',
                text='建筑附属同一建设用地红线内地面项目须同时符合国能发新能规〔2025〕7号第二、四、五条等条件；'
                     '独立空地通常按集中式管理。向当地发改、能源部门确认，不能按场地类型自动认定分布式'))
    use = (roof or {}).get('use')
    if use == 'barn':
        add('氨气腐蚀', 'ask', '核实氨气、湿度及冲洗环境；夹具、导轨、螺栓和切边须厂家确认，不以材料试验代替整套认证')
        add('羽毛灰尘', 'ask', '核实羽毛和灰尘积聚；清洗仅缺省时按普通频次两倍，手填0或其他频次优先')
        add('养殖场防火', 'ask', '核实可燃夹芯板、饲料粉尘、通风口及检修消防通道，按当地消防要求设计')
    if use == 'grazing':
        from .livestock import LAND
        add('牧草地复合利用', 'ask', LAND)
    if f.get('shifts') == 4:
        add('风机负荷', 'ask', '养殖场风机按七天运行、分季昼夜系数各月归一；为示意负荷，须实测确认')
    return out


def flags(facts, roof_type="flat", roof=None):
    """Short names for the park cards: answers that need attention, and questions left blank."""
    checks = rows(facts, roof_type=roof_type, roof=roof)
    return dict(risk=[r["text"].split("：")[0] for r in checks if r["status"] == "risk"], ask=[r["item"] for r in checks if r["status"] == "ask"])
