"""Deterministic park proposal from the same verified rows used by the map."""
import hashlib
import html
import uuid

from markupsafe import Markup

from . import park, park_store as store
from .report import render_pdf
from .report.archive import evidence
from .report.view import fmt, render_pages


def generate(saved, entries, root, browsers=None):
    with store.transaction(root):
        saved = store.load(saved.id, root)
        data = park.named(saved, entries, root)
        pages = []
        def add(title, paragraphs=(), rows=(), headers=(), chart=None):
            pages.append(dict(title=title, paragraphs=paragraphs, rows=rows, headers=headers,
                              chart=chart, kind='park', newpage=True))
        add(saved.name + ' · 园区方案书', ['光筑 · 按核验导出汇总，不调用 AI。',
            f"厂房 {len(data['buildings'])} 栋，已核验 {data['all']['count']} 栋；缺少设计的厂房不计入合计。",
            '本方案为初步设计，结构、消防、并网和报价须现场复核。'])
        add('园区总图', ['北向上，x朝东、y朝北；蓝色为园区一期，棕色为二期。',
            '组件按整栋分期显示；单屋顶内部的分期仍保留在单栋记录，不能重复相加。'], chart=Markup(park.map_svg(data)))
        rows = []
        for building in data['buildings']:
            result = building['result'] or {}
            rows.append((building['name'], fmt(result.get('dc_kw'), 'kW'), fmt(result.get('annual_kwh'), 'kWh'),
                         fmt(result.get('capex_cny'), '元'), fmt(result.get('payback_years'), '年'),
                         str(result.get('park_phase', '—')), '四步通过' if result else '未纳入'))
        add('每栋一行与分期', ['按回本从快到慢排序，预算与兼容AC容量均容得下的整栋进入一期。'], rows,
            ['厂房', '装机', '年发电', '造价', '回本', '园区期次', '核对'])
        metrics = [('装机', 'dc_kw', 'kW'), ('年发电', 'annual_kwh', 'kWh'), ('造价', 'capex_cny', '元'),
                   ('整体回本', 'payback_years', '年'), ('年减碳', 'co2_t', 't')]
        rows = [(label, fmt(data['all'][key], unit), fmt(data['phase1'][key], unit)) for label, key, unit in metrics]
        rows += [('逆变器台数', fmt(data['inverter_count'], '台'), '按实际设备清单'),
                 ('实际额定AC', fmt(data['rated_ac_kw'], 'kW'), '不重复累加屋顶内分期视图')]
        for key, label in [('posttax', '税后整体回本'), ('equity', '贷款权益税后回本')]:
            if key in data['all']:
                rows.append((label, fmt(data['all'][key]['payback_years'], '年'),
                             fmt(data['phase1'].get(key, {}).get('payback_years'), '年')))
            elif key + '_note' in data['all']:
                rows.append((label, data['all'][key + '_note'], '不适用'))
        add('合计与变压器对照', ['整体回本由逐年净现金流相加后过零插值，不平均每栋回本。'], rows, ['项目', '全园区已设计', '园区一期'])
        rows = [(r['label'], fmt(r['limit'], 'kW'), '无法核定' if r['excess'] is None else
                 Markup('有风险，超 {}').format(fmt(r['excess'], 'kW')) if r['excess'] > 1e-9 else '未超出') for r in data['risks']]
        add('容量风险与主要假设', ['额定AC由归档电气文件每台直流容量及未舍入容配比还原；缺失或零值不补当前目录。',
            '分栋贪心保留T22的摘要容量/容配比兼容AC；容量风险另按实际设备还原值。变压器×0.8为示意。',
            '现金流是每栋完整方案的同基准年导出值；不再把一期/两期合计/二期增量相加，不另分摊园区负荷。',
            'OSM真实屋顶从冻结原始经纬度还原；无地理锚点的自画屋顶放空处供人工移动。',
            '武进示意选real-07、09、10、11，因位置相邻且形状相近；不证明同一公司。10m屋面与1m女儿墙为示意。'],
            rows, ['约束', '上限', '结论'])
        add('设计记录与楼间遮挡', [], [(b['name'], (b['result'] or {}).get('run_id', '未设计'),
            (b['result'] or {}).get('shading_note', '暂无核验设计')) for b in data['buildings']], ['厂房', '设计记录编号', '遮挡依据'])
        token = uuid.uuid4().hex[:12]
        context = dict(project=dict(name=saved.name), project_id='园区 ' + saved.id, version=token)
        document = render_pages(pages, context)
        if evidence.sanitize(html.unescape(document)) != html.unescape(document):
            raise ValueError('方案书包含不可公开的信息')
        directory = store.folder(saved.id, root) / 'reports' / token
        directory.mkdir(parents=True)
        target = directory / 'park.html'
        target.write_text(document, encoding='utf-8', newline='\n')
        state = render_pdf(target, dict(files=[]), browsers)
        if state['status'] != 'ready':
            raise ValueError('未能生成PDF，保留HTML以便排查；请检查本地浏览器')
        files = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (target, target.with_suffix('.pdf'))}
        store.write(directory / 'manifest.json', dict(park=saved.model_dump(), data=data, files=files))
        store.write(directory.parent / 'latest.json', dict(report=token))
        return dict(report=token, files=files)


def verified_pdf(identifier, root):
    base = store.folder(identifier, root) / 'reports'
    token = store.read(base / 'latest.json')['report']
    directory = evidence.contained(base, token)
    manifest = store.read(directory / 'manifest.json')
    path = evidence.contained(directory, 'park.pdf')
    if hashlib.sha256(path.read_bytes()).hexdigest() != manifest['files']['park.pdf'] or not path.read_bytes().startswith(b'%PDF-'):
        raise ValueError('园区方案书哈希或格式校验失败')
    return path
