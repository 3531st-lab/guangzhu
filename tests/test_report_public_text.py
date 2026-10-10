"""Actual browser PDF text, using isolated byte-identical archive copies."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil

import pytest
from pypdf import PdfReader

from guangzhu import api, report
from guangzhu.report.archive import load_archive

from test_report_archive import archive
from guangzhu.report import view as REAL_VIEW

ROOT = Path(__file__).resolve().parents[1]
BROWSERS = [Path(os.environ.get(key, "")) / suffix
            for suffix in ("Microsoft/Edge/Application/msedge.exe", "Google/Chrome/Application/chrome.exe")
            for key in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA")]


@pytest.mark.parametrize("name", ["gz-t11-changzhou-006", "gz-t14-impossible-001"])
def test_real_pdf_public_text_and_untouched_archive(tmp_path, monkeypatch, name):
    if not any(path.is_file() for path in BROWSERS):
        pytest.skip("A real Edge/Chrome print executable is required")
    original = ROOT / "runs" / name
    metadata = json.loads((original / "run.json").read_text(encoding="utf-8-sig"))
    files = {Path("run.json"), Path("verification.json")}
    for field in ("capture", "review_capture"):
        base = original / metadata[field]
        files |= {Path(metadata[field]) / "run.json", Path(metadata[field]) / "ledger.agnes.jsonl"}
        files |= {path.relative_to(original) for path in (base / "project").rglob("*.json")}
    hashes = {str(path): hashlib.sha256((original / path).read_bytes()).hexdigest() for path in files}
    folder = tmp_path / "runs" / name
    for relative in files:
        target = folder / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original / relative, target)
    monkeypatch.setattr(api, "ROOT", tmp_path)
    monkeypatch.setattr(report, "ROOT", tmp_path)
    context = load_archive(folder)
    state = report.generate(folder, regenerated=True, browsers=BROWSERS)
    assert state["status"] == "ready", state
    pdf = folder / "report" / f"report-v{context['version']}.pdf"
    pages = [page.extract_text() or "" for page in PdfReader(pdf).pages]
    text = "\n".join(pages)
    before_review, review_and_execution = text.rsplit("\n独立审核意见\n", 1)
    review, execution = review_and_execution.split("\n执行证据与交付记录\n", 1)
    public = before_review + execution
    assert not re.search(r"requirements\.|roof\.|_m：|allowed-|任务卡|T04|T05|\d{4}-\d{2}-\d{2}T\d{2}:", public)
    compact = re.sub(r"\s+", "", public)
    assert "五链年发电复核范围（不是置信区间）" in compact
    assert "0.55%" in compact and "25年" in compact
    assert "仅允许这次" in execution and "（北京时间）" in execution
    assert re.search(r"审核记录核对（[^）]*）：通过", re.sub(r"\s+", "", review))
    for finding in context["review"]["findings"]:
        severity = {"low": "低（low）", "medium": "中（medium）", "high": "高（high）"}[finding["severity"]]
        assert severity in re.sub(r"\s+", "", review)
    html = (pdf.with_suffix(".html")).read_text(encoding="utf-8")
    html_entry = next(item for item in state['files'] if item['name'].endswith('.html'))
    assert html_entry['sha256'] == hashlib.sha256(pdf.with_suffix('.html').read_bytes()).hexdigest()
    from guangzhu.report.pagination import ENTRY, compact as normalize
    entries = list(ENTRY.finditer(html))
    assert entries
    for entry in entries:
        actual = [index + 1 for index, page in enumerate(pages) if normalize(entry[2] + entry[3]) in normalize(page)]
        assert len(actual) == 1 and entry[4] == str(actual[0])
    from html import unescape
    plain = unescape(re.sub(r"<[^>]+>", "", html))
    for finding in context["review"]["findings"]:
        assert all(finding[key] in plain for key in ("item", "evidence", "suggestion"))
    assert {str(path): hashlib.sha256((original / path).read_bytes()).hexdigest() for path in files} == hashes
    assert not (tmp_path / "projects").exists()


@pytest.mark.parametrize('delayed', [{'gz_compare_options'}, {'gz_compare_options', 'gz_export'}])
def test_synthetic_pending_wait_pdf_has_comparison_table_and_original_once_cover(archive, monkeypatch, delayed):
    if not any(path.is_file() for path in BROWSERS):
        pytest.skip('A real Edge/Chrome print executable is required')
    import sys
    from test_report_archive import pending_archive
    monkeypatch.setitem(sys.modules, 'guangzhu.report.view', REAL_VIEW)
    pending_archive(archive, delayed)
    state = report.generate(archive, browsers=BROWSERS)
    assert state['status'] == 'ready', state
    pdf = archive / 'report/report-v12.pdf'
    pages = [page.extract_text() or '' for page in PdfReader(pdf).pages]
    compact = re.sub(r'\s+', '', '\n'.join(pages))
    cover = re.sub(r'\s+', '', pages[0])
    assert '导出经AGH审批卡批准（仅允许这次）' in cover
    assert '本次未做三方案对比' not in compact
    # T20: sections flow, so the comparison table is found by its heading instead of a fixed page number.
    comparison = compact.rsplit('方案比选', 1)[1].split('屋面布置方案', 1)[0]
    assert all('v'+str(version) in comparison for version in (6,9,12))
