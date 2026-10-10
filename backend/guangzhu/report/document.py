"""Document structure and publication metadata; archived engineering values stay untouched."""
from hashlib import sha256


HEADINGS = {
    '一页结论': '项目概况与主要结论', '三方案对比': '方案比选', '屋顶与排布': '屋面布置方案',
    '空地与排布': '场地布置方案', '车棚与排布': '车棚布置方案', '电缆和压降': '电缆选型与压降校核',
    '承重核对': '附加荷载校核', '回报与敏感性': '经济评价与敏感性分析', '造价明细': '投资估算明细',
    '电价与收益': '电价与收益测算', '税和贷款': '税费与融资测算', '三种投资方式': '投资模式对比',
    '减碳估算': '环境效益估算', '开工前要核实的事': '实施前核实清单', '22条规则清单': '规则校核汇总',
    '规则清单（含新建安装校核）': '规则校核汇总', '假设与来源': '计算假设与资料来源',
    '独立审核': '独立审核意见', '执行记录与交付': '执行证据与交付记录',
}
CHAPTERS = {'1': '方案总览', '2': '场地与建设方案', '3': '发电与遮挡分析', '4': '电气设计',
            '5': '结构与经济评价', '6': '实施与校核', 'A': '计算资料', 'B': '审核意见', 'C': '执行证据'}
STARTS = {'一页结论': '1', '各朝向发电复核': '3', '发电量与复核': '3', '电气与组串': '4',
          '承重核对': '5', '基础与结构': '5', '开工前要核实的事': '6'}
KINDS = {'layout': '2', 'sources': 'A', 'review': 'B', 'execution': 'C'}


def prepare(pages, context, stamp):
    result, contents, count = [], [], {}
    chapter = None
    for original in pages:
        page = dict(original)
        page['heading'] = HEADINGS.get(page['title'], page['title'])
        page['compact'] = not page['chart'] and len(page['paragraphs']) <= 3 and len(page['rows']) <= 10
        if page['kind'] != 'cover':
            current = KINDS.get(page['kind'], STARTS.get(page['title'], chapter or '1'))
            first = current != chapter
            chapter = current
            count[chapter] = count.get(chapter, 0) + 1
            page.update(number=f'{chapter}.{count[chapter]}', chapter=CHAPTERS[chapter], chapter_start=first,
                        newpage=first or page['newpage'] and page['title'] != '造价明细')
            if first:
                contents.append(dict(number=chapter, title=CHAPTERS[chapter], anchor=f'part-{page["number"]}', sections=[]))
            contents[-1]['sections'].append(dict(number=page['number'], title=page['heading'], chapter=page['chapter']))
        result.append(page)
    identifier = str(context.get('project_id') or context['project']['id'])
    code = 'GZ-' + sha256(identifier.encode()).hexdigest()[:8].upper() + '-V' + str(context['version'])
    rules = context.get('summary', {}).get('rules', {})
    failures = rules.get('hard_failed')
    status = '校核结果未提供' if failures is None else f'{failures}项硬性校核未通过' if failures else '自动校核无硬性失败'
    document = dict(code=code, project_id=identifier, revision=f'V{context["version"]}', date=stamp,
                    stage='初步设计方案', purpose='方案比选与技术沟通', status=status, failed=bool(failures),
                    evidence='归档运行记录' if context.get('sessions') else '离线工具计算', contents=contents)
    return result, document
