"""Make the four synthetic regional templates explicit and internally consistent.

This edits only the named bundled examples, never user roofs or design projects.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES = {
    'taizhou-cmc-pharma': ('泰州产业演示·医药洁净厂房（合成）', 150000., 3,
        '组合坡屋面与设备避让', '主跨双坡与低跨附楼；保留天窗、净化空调、酸雾塔和水罐，检查通道与限高。'),
    'taizhou-shipbuilding-workshop': ('泰州产业演示·船舶海工车间（合成）', 100000., 2,
        '彩钢瓦顺坡与设备选型', '避开屋脊通风气楼、采光带与除尘塔；比较铜铝线缆并检查夹具荷载。'),
    'taizhou-watertown-pavilion': ('泰州产业演示·文旅坡屋面（合成）', 20000., 1,
        '坡屋面、天窗与周边树木', '顺坡平铺；比较不同退距后的容量与遮挡，展示未核实承载力提示。'),
    'taizhou-lixiahe-coldchain': ('泰州产业演示·农业冷链仓（合成）', 100000., 3,
        '分段女儿墙与连续用电', '保留女儿墙吊装缺口、冷机与管桥；切换允许上网条件，核对逐月自用与限发。'),
}


def main():
    catalogue = []
    for identifier, (name, monthly, shifts, focus, instruction) in CASES.items():
        directory = ROOT / 'data/demo/projects' / identifier
        path = directory / 'project.json'
        record = json.loads(path.read_text(encoding='utf-8'))
        record['name'] = name
        record['requirements']['text'] = f'合成产业场景，不是实测或客户工程。{instruction} 按下列结构化要求计算；不能满足时保留失败原因，不得伪报通过。'
        economy = record['economics']
        economy.update(monthly_kwh=monthly, shifts=shifts, self_use_ratio=None)
        economy['assumptions_note'] = (
            f'本例全部屋面尺寸、障碍物、承载力、用电及经济条件为合成演示输入，不代表对应企业或实测工程。'
            f'月用电量假设{monthly:g}kWh、{shifts}班，自用比例由模拟逐时发电与示意负荷曲线计算，不预设高自用率。'
            f'自用平段电价假设{economy["price_self_cny_kwh"]:g}元/kWh，计算期{economy["lifetime_years"]}年，折现率{economy["discount_rate"]:g}。'
            '造价按实际工程量及当前目录的示意报价汇总；未填参数取data/catalog/assumptions.csv，并保留各自来源及限制。'
            '余电价格、峰谷电价、荷载能力和并网条件均待真实项目核实；不承诺回本。'
            '天气使用泰州区域坐标32.46N/119.92E的已标注来源数据，坐标用于区域气象，不是该建筑测绘坐标。'
            '所有输出为模型计算，不能替代现场测量和专业复核。')
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        details = dict(id=identifier, name=name, synthetic=True, focus=focus, demonstration=instruction,
                       geometry_source='由示意尺寸构建，非航测/测绘/客户CAD',
                       weather_basis='区域坐标32.46N/119.92E；快照来源见data/demo/weather元数据',
                       monthly_load_kwh=monthly, shifts=shifts,
                       unresolved=['屋面承载力', '实际用电曲线', '接网容量和价格', '设备与施工报价', '客户授权及落地成效'],
                       expected='可重新计算并检查结果；失败和未核实项必须保留，规则通过不等于工程批准')
        (directory / 'case.json').write_text(json.dumps(details, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        catalogue.append(details)
    (ROOT / 'data/demo/cases.json').write_text(json.dumps(dict(schema='guangzhu.demo-cases/1', cases=catalogue), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(updated=[row['id'] for row in catalogue], synthetic=True), ensure_ascii=False))


if __name__ == '__main__':
    main()
