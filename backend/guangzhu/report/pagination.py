"""Resolve contents against the actual printed pages, without guessing page numbers."""
from html import unescape
import re

import pypdfium2 as pdfium


ENTRY = re.compile(r'(<span class="toc-page" data-section="([^"]+)" data-heading="([^"]+)">)(.*?)(</span>)')


def compact(text):
    return re.sub(r'\s+', '', unescape(text))


def contents_for_pdf(contents, pdf):
    if not ENTRY.search(contents):
        return contents
    try:
        with pdfium.PdfDocument(pdf) as document:
            pages = []
            for page in document:
                text = page.get_textpage()
                try:
                    pages.append(compact(text.get_text_range()))
                finally:
                    text.close()
                    page.close()
    except pdfium.PdfiumError as error:
        raise ValueError('无法读取目录页码') from error

    def replace(match):
        marker = compact(match[2] + match[3])
        found = [index + 1 for index, page in enumerate(pages) if marker in page]
        if len(found) != 1:
            raise ValueError('无法唯一确认章节所在页：' + match[2])
        return match[1] + str(found[0]) + match[5]
    return ENTRY.sub(replace, contents)


def paginate(target, pdf, print_once):
    original = target.read_text(encoding='utf-8')
    contents = original
    try:
        for _ in range(3):
            print_once()
            if not pdf.is_file() or not pdf.read_bytes().startswith(b'%PDF-'):
                raise ValueError('浏览器未产生有效PDF')
            updated = contents_for_pdf(contents, pdf)
            if updated == contents:
                return
            contents = updated
            target.write_text(contents, encoding='utf-8', newline='\n')
        raise ValueError('目录页码未稳定，请使用HTML打印')
    except Exception:
        target.write_text(original, encoding='utf-8', newline='\n')
        raise
