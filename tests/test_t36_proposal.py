"""Publication changes must preserve archived engineering and audit evidence."""
from copy import deepcopy
from html import unescape
import json
from pathlib import Path
import re

from guangzhu.report.archive import load_archive
from guangzhu.report.view import render


ROOT = Path(__file__).parents[1]


def test_real_archived_review_and_new_livestock_context_keep_values_and_valid_navigation():
    livestock = json.loads((ROOT / 'reports/assets/T35/context.json').read_text(encoding='utf-8'))
    for context in [load_archive(ROOT / 'runs/gz-t14-impossible-001'), livestock]:
        before = deepcopy(context)
        document = render(context)
        plain = unescape(re.sub(r'<[^>]+>', '', document))
        assert context == before
        assert all(label in plain for label in ['文件编号', '初步设计方案', '目录', '内部收益率（IRR）', '待专业复核'])
        targets = re.findall(r'href="#(part-[^"]+)"', document)
        anchors = re.findall(r'<section id="([^"]+)"', document)
        assert len(targets) >= 9 and len(anchors) == len(set(anchors))
        assert set(targets) <= set(anchors)
        assert '图 2.1-1' in plain and '表 1.1-1' in plain
        for row in (context.get('review') or {}).get('findings', []):
            assert all(row[key] in plain for key in ['item', 'evidence', 'suggestion'])
        if not context['sessions']:
            assert '未提供 AI 会话' in plain and '光筑 Agent 生成' not in plain
            raw = context['structure']['livestock']['ground_light']['sun_pct']
            assert f'title="原值 {raw}"' in document
            assert str(raw) not in plain


def test_unknown_and_failed_rules_are_never_shown_as_passed():
    context = load_archive(ROOT / 'runs/gz-t14-impossible-001')
    for value, label in [(None, '校核结果未提供'), (2, '2项硬性校核未通过')]:
        context['summary']['rules']['hard_failed'] = value
        cover = render(context).split('</section>', 1)[0]
        assert label in cover and '自动校核无硬性失败' not in cover
