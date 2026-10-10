"""Report provenance and printing boundaries; no native services or model calls."""
import hashlib
import json
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest

from guangzhu import api, report
from guangzhu.report import generate
from guangzhu.report.archive import load_archive

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "runs/gz-t14-changzhou-005"


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def archive(tmp_path, monkeypatch):
    folder = tmp_path / "runs" / RUN.name
    metadata = read(RUN / "run.json")
    files = {Path("run.json"), Path("verification.json")}
    for name in ("capture", "review_capture"):
        base = RUN / metadata[name]
        files |= {Path(metadata[name]) / "run.json", Path(metadata[name]) / "ledger.agnes.jsonl"}
        files |= {path.relative_to(RUN) for path in (base / "project").rglob("*.json")}
    for relative in files:
        target = folder / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(RUN / relative, target)
    monkeypatch.setattr(api, "ROOT", tmp_path)
    monkeypatch.setattr(report, "ROOT", tmp_path)
    monkeypatch.setitem(sys.modules, "guangzhu.report.view", SimpleNamespace(render=lambda context: "<!doctype html><p>光筑</p>"))
    return folder


def test_real_context_selects_export_and_preserves_review(archive):
    context = load_archive(archive)
    assert context["version"] == 12
    assert context["design"]["version"] == 12
    assert context["compare"]["base_version"] == 3
    assert [row["version"] for row in context["compare"]["options"]] == [6, 9, 12]
    assert context["crosscheck"]["version"] == 12
    assert context["approval"]["verdict"] == "allowed-once"
    assert context["review"]["reviewer_model"] == "agnes-3.0-flash"
    assert context["structure"] is None and context["catalog"] is None
    assert len(context["sessions"]) == 2
    assert all("account-" not in model for row in context["sessions"] for model in row["model_ids"])
    review_base = archive / read(archive / "run.json")["review_capture"] / "project/reviews"
    original = next(read(path) for path in review_base.glob("v12-*.json"))
    assert context["review"]["findings"] == original["findings"]


def test_real_relaxation_uses_trusted_original_consent():
    context = load_archive(ROOT / "runs/gz-t14-impossible-001")
    change = context["relaxations"][0]
    assert change["before"]["structured"]["capacity_kw_min"] == 300
    assert "capacity_kw_min" not in change["after"]["structured"]
    assert change["consent"]
    assert any("建议" in row["text"] for row in change["consent"])
    assert all(change["before"]["seq"] < row["seq"] < change["after"]["seq"] for row in change["consent"])


def test_legacy_design_without_gz_prefix_reads_only_its_own_archive():
    context = load_archive(ROOT / "runs/t10-impossible-007")
    assert context["version"] == 6
    assert context["design"]["version"] == 6
    assert context["project"]["id"] == context["project_id"]


@pytest.mark.parametrize("relative", ["project/designs/v12.json", "project/analysis/v12/shading.json"])
def test_artifact_tampering_fails_closed(archive, relative):
    capture = archive / read(archive / "run.json")["capture"]
    with (capture / relative).open("ab") as stream:
        stream.write(b" ")
    with pytest.raises(ValueError, match="SHA"):
        load_archive(archive)


def test_missing_optional_is_explicit_and_never_reads_projects(archive):
    capture = archive / read(archive / "run.json")["capture"]
    path = capture / "project/analysis/v12/electrical.json"
    path.unlink()
    context = load_archive(archive)
    assert context["electrical"] is None
    assert path.relative_to(archive).as_posix() in context["missing"]


def test_capture_containment_and_review_certificate(archive):
    path = archive / "run.json"
    metadata = read(path)
    original = dict(metadata)
    metadata["capture"] = "../outside"
    write(path, metadata)
    with pytest.raises(ValueError, match="超出"):
        load_archive(archive)
    write(path, original)
    verification = read(archive / "verification.json")
    verification["review"]["associations"][0]["ledger_sha256"] = "0" * 64
    write(archive / "verification.json", verification)
    with pytest.raises(ValueError, match="关联SHA"):
        load_archive(archive)


def test_no_browser_is_successful_html_and_keeps_original_files(archive):
    before = {p.relative_to(archive): p.read_bytes() for p in archive.rglob("*") if p.is_file() and p != archive / "run.json"}
    state = generate(archive, regenerated=True, browsers=[archive / "missing-edge", archive / "missing-chrome"])
    assert state["status"] == "html-only" and state["regenerated"]
    assert state["hint"] == "可用浏览器打印成 PDF"
    assert [row["name"] for row in state["files"]] == ["report-v12.html"]
    metadata = read(archive / "run.json")
    assert metadata["report"] == state
    assert metadata["artifacts"]["report/report-v12.html"] == hashlib.sha256((archive / "report/report-v12.html").read_bytes()).hexdigest()
    assert all((archive / relative).read_bytes() == content for relative, content in before.items())
    assert not (report.ROOT / "projects").exists()


def test_cli_copies_report_to_existing_project_without_reading_live_data(archive, monkeypatch, capsys):
    project = report.ROOT / "projects" / read(archive / "run.json")["project_id"]
    project.mkdir(parents=True)
    live = project / "project.json"
    live.write_bytes(b"invalid live project data must never be read")
    monkeypatch.setattr(report, "generate", lambda folder, **kwargs: generate(folder, browsers=[], **kwargs))
    monkeypatch.setattr(sys, "argv", ["guangzhu.report", str(archive), "--regenerated"])
    with pytest.raises(SystemExit) as caught:
        runpy.run_module("guangzhu.report", run_name="__main__")
    assert caught.value.code == 0
    state = json.loads(capsys.readouterr().out)
    assert state["status"] == "html-only" and state["regenerated"]
    for row in state["files"]:
        original = archive / "report" / row["name"]
        copy = project / "reports/v12" / row["name"]
        assert copy.read_bytes() == original.read_bytes()
        assert hashlib.sha256(copy.read_bytes()).hexdigest() == row["sha256"]
    assert live.read_bytes() == b"invalid live project data must never be read"


def test_project_copy_cannot_escape_project_and_failure_keeps_archive(archive, monkeypatch):
    project = report.ROOT / "projects" / read(archive / "run.json")["project_id"]
    project.mkdir(parents=True)
    linked = project / "reports/v12"
    outside = report.ROOT / "outside"
    original_resolve = Path.resolve
    monkeypatch.setattr(Path, "resolve", lambda path, *args, **kwargs:
                        outside if path == linked else original_resolve(path, *args, **kwargs))
    before = (archive / "verification.json").read_bytes()
    state = generate(archive, browsers=[])
    assert state["status"] == "html-only" and "副本未能写入" in state["hint"]
    assert not outside.exists()
    assert (archive / "report/report-v12.html").is_file()
    assert read(archive / "run.json")["report"] == state
    assert (archive / "verification.json").read_bytes() == before


def test_print_uses_isolated_profile_and_removes_temporary_directory(archive, monkeypatch):
    browser = archive / "fake-edge.exe"
    browser.write_bytes(b"test-only")
    observed = {}
    def run(command, **kwargs):
        observed.update(command=command, kwargs=kwargs)
        pdf = Path(next(value.split("=", 1)[1] for value in command if value.startswith("--print-to-pdf=")))
        observed["temporary"] = pdf.parent
        pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    monkeypatch.setattr(subprocess, "run", run)
    state = generate(archive, browsers=[browser])
    assert state["status"] == "ready"
    assert observed["kwargs"]["timeout"] == 60
    assert observed["kwargs"]["creationflags"] == getattr(subprocess, "CREATE_NO_WINDOW", 0)
    assert "--no-pdf-header-footer" in observed["command"]
    assert not observed["temporary"].exists()
    assert len(state["files"]) == 2


def test_print_timeout_preserves_html_without_changing_verification(archive, monkeypatch):
    browser = archive / "fake-edge.exe"
    browser.write_bytes(b"test-only")
    before = (archive / "verification.json").read_bytes()
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("test-only", 60)
    monkeypatch.setattr(subprocess, "run", timeout)
    state = generate(archive, browsers=[browser])
    assert state["status"] == "html-only" and state["error"]
    assert (archive / "verification.json").read_bytes() == before



def fake_browsers(archive, monkeypatch, prints):
    """Codex review R06: `prints` maps a browser file name to what it leaves behind: real PDF bytes, other bytes, or an exception."""
    browsers, tried = [archive / name for name in prints], []
    for browser in browsers:
        browser.write_bytes(b"test-only")
    def run(command, **kwargs):
        tried.append(Path(command[0]).name)
        outcome = prints[Path(command[0]).name]
        if isinstance(outcome, Exception):
            raise outcome
        Path(next(value.split("=", 1)[1] for value in command if value.startswith("--print-to-pdf="))).write_bytes(outcome)
    monkeypatch.setattr(subprocess, "run", run)
    return browsers, tried


def test_codex_r06_a_browser_that_exits_without_a_pdf_is_skipped_and_the_next_one_prints(archive, monkeypatch):
    browsers, tried = fake_browsers(archive, monkeypatch, {"msedge.exe": b"", "chrome.exe": b"%PDF-1.4\n%%EOF\n"})
    state = generate(archive, browsers=browsers)
    assert tried == ["msedge.exe", "chrome.exe"]
    assert state["status"] == "ready" and "Edge 没转成 PDF，已改用 Chrome" in state["hint"] and "error" not in state
    assert [row["name"] for row in state["files"]] == ["report-v12.html", "report-v12.pdf"]
    assert (archive / "report/report-v12.pdf").read_bytes().startswith(b"%PDF-") and read(archive / "run.json")["report"] == state
    browsers, tried = fake_browsers(archive, monkeypatch, {"msedge.exe": b"%PDF-1.4\n%%EOF\n", "chrome.exe": b"%PDF-1.4\n%%EOF\n"})
    assert generate(archive, browsers=browsers)["hint"] == "运行结束后生成" and tried == ["msedge.exe"]


def test_codex_r06_when_every_browser_fails_the_html_stays_and_the_reason_names_them(archive, monkeypatch):
    before = (archive / "verification.json").read_bytes()
    browsers, tried = fake_browsers(archive, monkeypatch, {"msedge.exe": b"<html>not a pdf</html>",
                                                           "chrome.exe": subprocess.CalledProcessError(1, "chrome")})
    state = generate(archive, browsers=browsers)
    assert tried == ["msedge.exe", "chrome.exe"] and state["status"] == "html-only"
    assert state["error"].startswith("Edge、Chrome 都没能转成 PDF") and "打印成 PDF" in state["error"]
    assert [row["name"] for row in state["files"]] == ["report-v12.html"] and not (archive / "report/report-v12.pdf").exists()
    assert (archive / "verification.json").read_bytes() == before


def test_sensitive_review_output_refused_before_html_write(archive, monkeypatch):
    monkeypatch.setitem(sys.modules, "guangzhu.report.view", SimpleNamespace(render=lambda context: "<p>account-" + "acct-example</p>"))
    state = generate(archive, browsers=[])
    assert state["status"] == "error" and not state["files"]
    assert not (archive / "report/report-v12.html").exists()


def pending_archive(folder, tools, *, bad_job=False, wait_approval=False):
    """Synthetic transport delays inserted in an isolated archive copy only."""
    meta = read(folder / "run.json")
    for field in ("capture", "review_capture"):
        ledger = folder / meta[field] / "ledger.agnes.jsonl"
        events = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
        calls = {e["data"].get("toolUseId"): e for e in events if e["type"] == "tool/call"}
        rebuilt = []
        for event in events:
            rebuilt.append(event)
            call = calls.get(event["data"].get("toolUseId"))
            if event["type"] != "tool/result" or not call or ('gz_' + call['data']['name'].split('_gz_')[-1] if '_gz_' in call['data']['name'] else call['data']['name']) not in tools:
                continue
            name = call["data"]["name"]
            name = 'gz_' + name.split('_gz_')[-1] if '_gz_' in name else name
            value = json.loads(event["data"]["content"][0]["text"])
            job = 'synthetic-job-' + call["data"]["toolUseId"]
            event["data"]["content"][0]["text"] = json.dumps(dict(ok=True, pending=True, tool=name, job_id=job))
            wait_id = 'synthetic-wait-' + call["data"]["toolUseId"]
            wait = dict(event, id=wait_id+'-call', type="tool/call", origin="model",
                        data=dict(toolUseId=wait_id, name="gz_wait", args=dict(job_id=job)))
            rebuilt.append(wait)
            if wait_approval and name == 'gz_export':
                for e in rebuilt:
                    if e['type'] == 'approval/decided': e['data']['verdict'] = 'rejected'
                rebuilt.extend([dict(event, id=wait_id+'-ask', type='approval/asked', origin='system', trust='trusted',
                    data=dict(toolUseId=wait_id, requestId=wait_id+'-request', kind='tool', tool='gz_wait')),
                    dict(event, id=wait_id+'-decision', type='approval/decided', origin='system', trust='trusted',
                    data=dict(requestId=wait_id+'-request', verdict='allowed-once', via='sync'))])
            rebuilt.append(dict(event, id=wait_id+'-result', data=dict(toolUseId=wait_id, isError=False,
                content=[dict(type="text", text=json.dumps(dict(value, tool=name, job_id=job+'-wrong' if bad_job else job)))])))
        for seq, event in enumerate(rebuilt, 1): event['seq'] = seq
        ledger.write_text(''.join(json.dumps(e, ensure_ascii=False)+'\n' for e in rebuilt), encoding='utf-8', newline='\n')
        if field == 'review_capture':
            verification = read(folder / 'verification.json')
            for association in verification['review']['associations']:
                if association['session'] == read(folder / meta[field] / 'run.json')['session']:
                    association['ledger_sha256'] = hashlib.sha256(ledger.read_bytes()).hexdigest()
            write(folder / 'verification.json', verification)


def test_all_semantic_archive_consumers_resolve_wait_results(archive):
    before = load_archive(archive)
    pending_archive(archive, {'gz_set_requirements', 'gz_compare_options', 'gz_crosscheck_yield', 'gz_record_review', 'gz_export'})
    after = load_archive(archive)
    for key in ('compare', 'crosscheck', 'review'):
        assert before[key] == after[key]
    assert [r['structured'] for r in before['requirements']] == [r['structured'] for r in after['requirements']]
    assert after['approval']['verdict'] == 'allowed-once'


@pytest.mark.parametrize('bad_job,wait_approval', [(True,False), (False,True)])
def test_wrong_job_or_wait_card_cannot_authorize_original_export(archive, bad_job, wait_approval):
    pending_archive(archive, {'gz_export'}, bad_job=bad_job, wait_approval=wait_approval)
    assert load_archive(archive)['approval'] is None


@pytest.mark.parametrize('mutation', ['untrusted_ask','untrusted_decision','session','duplicate','late','wrong_tool'])
def test_export_approval_uses_verifier_trust_and_single_decision_rules(archive, mutation):
    meta=read(archive/'run.json');ledger=archive/meta['capture']/'ledger.agnes.jsonl'
    events=[json.loads(line) for line in ledger.read_text(encoding='utf-8').splitlines()]
    call=next(e for e in events if e['type']=='tool/call' and e['data']['name'].endswith('gz_export'))
    ask=next(e for e in events if e['type']=='approval/asked' and e['data'].get('toolUseId')==call['data']['toolUseId'])
    decision=next(e for e in events if e['type']=='approval/decided' and e['data'].get('requestId')==ask['data']['requestId'])
    if mutation=='untrusted_ask': ask['trust']='untrusted'
    if mutation=='untrusted_decision': decision['origin']='model'
    if mutation=='session': decision['data']['verdict']='allowed-session'
    if mutation=='duplicate': events.append(dict(decision,id='synthetic-duplicate',seq=max(e['seq'] for e in events)+1))
    if mutation=='late': decision['seq']=max(e['seq'] for e in events)+1
    if mutation=='wrong_tool': ask['data']['tool']='gz_wait'
    ledger.write_text(''.join(json.dumps(e)+'\n' for e in events),encoding='utf-8')
    assert load_archive(archive)['approval'] is None
