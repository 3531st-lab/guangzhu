"""Illustrative ordinary-taxpayer annual accounts, shared by all investment modes."""
import math

NOTES = [
    '价格含税；按一般纳税人、设备取得13%增值税专用发票估算。自己用掉的电省下的钱不交增值税；没抵完的进项税不退。',
    '设备按20年直线折旧、残值5%（示意）；换逆变器那一年全年计折旧，旧逆变器剩下的账面价值没有单列。',
    '企业所得税25%；按本项目单独核算、盈利才交税，不考虑企业其他业务的盈亏；绿证和补贴算作其他收入。',
    '“三免三减半”税收优惠默认不计：企业自建自用的项目不适用，其他方式须确认资格后才可打开。',
    '自己用掉的电对应的绿证不能卖；拿了机制电价或随绿电卖出的电量不重复算绿证。发电按2023年天气。',
    '第13年逆变器更换为示意，基础运维费不含更换；保险、清洗和设备价格须核实。',
    '余电上网价0.391元/度为示意值，默认没有机制电价；25年内电价不变、自用比例按第一年计，都是测算假设。',
    '没查到普通工商业项目现行可拿的补贴，按0计；常州212号文的一次性奖励只给确认符合条件的公共机构。',
    '屋顶租赁的租金按9%增值税和25%企业所得税估算；合同能源管理下业主省下的电费按25%所得税估算。',
]


def metrics(cash, discount=0):
    from .economics import _payback, _irr
    rows = []
    cumulative, discounted = 0.0, 0.0
    for year, net in enumerate(cash):
        cumulative += net
        value = net / (1 + discount) ** year
        discounted += value
        rows.append(dict(year=year, net_cny=net, cumulative_cny=cumulative,
                         discounted_cny=value, cumulative_discounted_cny=discounted))
    return dict(payback_years=_payback(rows, 'cumulative_cny') if cash[0] < 0 else None,
                dynamic_payback_years=_payback(rows, 'cumulative_discounted_cny') if cash[0] < 0 else None,
                irr_pct=_irr(cash), npv_cny=discounted, profit_cny=cumulative,
                operating_net_cny=math.fsum(cash[1:]), cashflows=rows)


def debt_schedule(capex, ratio, rate, term, years):
    if not 0 <= ratio < 1 or not 0 <= rate <= 1 or not 1 <= term <= years:
        raise ValueError('贷款比例须小于100%，利率0至100%，年限不得超过计算期')
    balance = capex * ratio
    annuity = balance * rate / (1 - (1 + rate) ** -term) if rate else balance / term
    rows = []
    for year in range(1, years + 1):
        opening = balance
        interest = balance * rate
        principal = balance if year == term else min(balance, max(0, annuity - interest)) if year < term else 0
        balance = max(0, balance - principal)
        rows.append(dict(year=year, opening=opening, interest=interest, principal=principal,
                         closing=balance, payment=principal + interest))
    return rows


def ledger(capex, hardware, saving, export, om, *, years=25, degradation=0, discount=.06,
           mode='self', rent=0, land_rent=None, emc_discount=.15, replacement=0, replacement_year=13,
           other=None, sale_adjustment=None, tax_holiday=False, loan_ratio=0, loan_rate=.035, loan_years=20):
    credit = hardware * 13 / 113
    original_basis = capex - credit
    rows = []
    debts = debt_schedule(capex, loan_ratio, loan_rate, loan_years, years) if loan_ratio else None
    for year in range(1, years + 1):
        factor = (1 - degradation / 100) ** (year - 1)
        self_saving, exported = saving * factor, export * factor
        exported += sale_adjustment(year, factor) if sale_adjustment else 0
        q = self_saving if mode == 'self' else 0
        sales = exported + (self_saving * (1 - emc_discount) if mode == 'emc' else self_saving if mode == 'rent' else 0)
        rental = rent if mode == 'rent' else 0
        land = land_rent or 0
        replaced = replacement if year == replacement_year else 0
        new_credit = replaced * 13 / 113
        opening = credit
        output = sales * 13 / 113
        paid = max(0, output - credit - new_credit)
        credit = max(0, credit + new_credit - output)
        depreciation = original_basis * .95 / 20 if year <= 20 else 0
        if replacement_year <= year < replacement_year + 20:
            depreciation += replacement / 1.13 * .95 / 20
        added = other(year, factor) if other else 0
        taxable = q + sales - output + added - om - rental - land - depreciation
        rate = 0 if tax_holiday and year <= 3 else .125 if tax_holiday and year <= 6 else .25
        cit = max(0, taxable) * rate
        pretax = q + sales + added - om - rental - land - replaced
        posttax = pretax - paid - cit
        row = dict(year=year, saving=q, sales=sales, rent=rental, replacement=replaced, credit_open=opening,
                   new_credit=new_credit, output_vat=output, paid_vat=paid, credit_close=credit,
                   depreciation=depreciation, taxable=taxable, cit=cit, pretax=pretax, posttax=posttax, other=added)
        if land_rent is not None:
            row['land_rent_cny'] = land
        if debts:
            debt = debts[year - 1]
            equity_cit = max(0, taxable - debt['interest']) * rate
            row.update(debt, equity_cit=equity_cit, equity_pretax=pretax - debt['payment'],
                       equity_posttax=pretax - paid - equity_cit - debt['payment'])
        rows.append(row)
    pre = metrics([-capex] + [r['pretax'] for r in rows], discount)
    post = metrics([-capex] + [r['posttax'] for r in rows], discount)
    result = dict(pretax=pre, posttax=post, accounts=rows)
    if debts:
        initial = capex * (1 - loan_ratio)
        result['loan'] = dict(initial_equity_cny=initial, ratio=loan_ratio, rate=loan_rate, years=loan_years,
                              pretax=metrics([-initial] + [r['equity_pretax'] for r in rows], discount),
                              posttax=metrics([-initial] + [r['equity_posttax'] for r in rows], discount))
    return result
