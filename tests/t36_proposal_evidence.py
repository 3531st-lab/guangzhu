"""Render two real offline contexts to reviewable PDFs; never write to the input archives."""
import argparse
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright
import pypdfium2 as pdfium

from guangzhu.report.archive import load_archive
from guangzhu.report.view import render
from guangzhu.report.pagination import paginate, contents_for_pdf


ROOT = Path(__file__).parents[1]


def main(output):
    output.mkdir(parents=True, exist_ok=True)
    contexts = {'grazing': json.loads((ROOT / 'reports/assets/T35/context.json').read_text(encoding='utf-8')),
                'review': load_archive(ROOT / 'runs/gz-t14-impossible-001')}
    results = {}
    with sync_playwright() as runner:
        browser = runner.chromium.launch(channel='msedge', headless=True)
        for name, context in contexts.items():
            context.update(generated_at=datetime.now(timezone(timedelta(hours=8))).isoformat(), regenerated=True)
            before = deepcopy(context)
            markup = render(context)
            assert context == before
            target = output / name
            target.with_suffix('.html').write_text(markup, encoding='utf-8')
            page = browser.new_page(viewport={'width': 1280, 'height': 900})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.route('**/*', lambda route: route.abort())
            def print_once():
                page.set_content(target.with_suffix('.html').read_text(encoding='utf-8'), wait_until='load')
                page.evaluate('document.fonts.ready')
                page.pdf(path=str(target.with_suffix('.pdf')), print_background=True, prefer_css_page_size=True)
            paginate(target.with_suffix('.html'), target.with_suffix('.pdf'), print_once)
            final_html = target.with_suffix('.html').read_text(encoding='utf-8')
            assert contents_for_pdf(final_html, target.with_suffix('.pdf')) == final_html
            assert page.title() == context['project']['name'] + ' · 光筑方案书'
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page_links = page.locator('.contents-group > a').all()
            for link in page_links:
                anchor = link.get_attribute('href')
                link.click()
                section = page.locator(f'[id="{anchor[1:]}"]')
                assert section.is_visible()
                position = section.evaluate('(el) => el.getBoundingClientRect().top')
                assert -2 <= position < 900
            assert not errors, errors
            page.close()
            document = pdfium.PdfDocument(target.with_suffix('.pdf'))
            texts, thumbnails = [], []
            outside = []
            for index in range(len(document)):
                pdf_page = document[index]
                text_page = pdf_page.get_textpage()
                texts.append(text_page.get_text_range())
                width, height = pdf_page.get_size()
                assert abs(width - 595.28) < 2 and abs(height - 841.89) < 2
                for char in range(text_page.count_chars()):
                    left, bottom, right, top = text_page.get_charbox(char)
                    if right > width + 1 or left < -1 or top > height + 1 or bottom < -1:
                        outside.append([index + 1, char])
                snapshot = pdf_page.render(scale=1.2).to_pil()
                snapshot.save(output / f'{name}-{index + 1:02}.png')
                snapshot.thumbnail((238, 337))
                thumbnails.append(snapshot)
                text_page.close()
                pdf_page.close()
            document.close()
            assert not outside, outside
            assert all(f'第 {i + 1} 页 / 共 {len(texts)} 页' in text for i, text in enumerate(texts))
            sheet = Image.new('RGB', (5 * 254, ((len(thumbnails) + 4) // 5) * 362), '#dce2e8')
            draw = ImageDraw.Draw(sheet)
            for index, snapshot in enumerate(thumbnails):
                x, y = (index % 5) * 254 + 8, (index // 5) * 362 + 18
                sheet.paste(snapshot, (x, y))
                draw.text((x, y - 15), str(index + 1), fill='#202d3b')
            sheet.save(output / f'{name}-contact.png')
            (output / f'{name}-pages.json').write_text(json.dumps(texts, ensure_ascii=False, indent=2), encoding='utf-8')
            results[name] = dict(pages=len(texts), bytes=target.with_suffix('.pdf').stat().st_size,
                                 navigation_links=len(page_links), javascript_errors=errors, out_of_page_characters=outside,
                                 source='reports/assets/T35/context.json' if name == 'grazing' else 'runs/gz-t14-impossible-001')
        browser.close()
    (output / 'pdf-checks.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    main(parser.parse_args().output)
