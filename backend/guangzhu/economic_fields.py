"""Public economic form and tool fields, shared to prevent dropped park settings."""
LABELS = dict(land_rent_cny_mu_year='年地租（元/亩，示意）', loan_ratio='贷款比例', loan_rate='贷款年利率', loan_years='贷款年限', tariff_class='电价类别',
              posttax_payback='按税后看回本', cleaning_times='每年清洗次数', refurbish='安装前翻新',
              tax_holiday_confirmed='已确认三免三减半资格', mechanism_share='已确认机制电量比例',
              mechanism_price='已确认机制电价', mechanism_years='已确认机制年限', green_sold_share='已随绿电出售比例',
              public_subsidy_confirmed='已确认常州公共机构奖励全部资格', subsidy_year='补贴到账年')
BOOLEANS = ('posttax_payback', 'refurbish', 'tax_holiday_confirmed', 'public_subsidy_confirmed')
RANGES = dict(land_rent_cny_mu_year=(0, 100000), loan_ratio=(0, .99), loan_rate=(0, 1), loan_years=(1, 50), cleaning_times=(0, 365),
              mechanism_share=(0, .9), mechanism_price=(0, 2), mechanism_years=(1, 25), green_sold_share=(0, 1), subsidy_year=(1, 25))


def schemas():
    integer = ('loan_years', 'cleaning_times', 'mechanism_years', 'subsidy_year')
    result = {key: dict(type='integer' if key in integer else 'number', minimum=low, maximum=high)
              for key, (low, high) in RANGES.items()}
    result.update({key: dict(type='boolean') for key in BOOLEANS})
    result['tariff_class'] = dict(type='string', enum=['two_part', 'single100', 'single_small'])
    return result
