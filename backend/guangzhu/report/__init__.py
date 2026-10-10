"""Generate a self-contained, post-run report from archived evidence."""
from datetime import datetime, timedelta, timezone
import hashlib
import html
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from ..config import ROOT
from .archive import evidence, load_archive

NAMES = {"msedge": "Edge", "chrome": "Chrome"}


def generate(run_dir, *, regenerated=False, browsers=None):
    from .view import render
    folder = Path(run_dir).resolve()
    context = load_archive(folder)
    stamp = datetime.now(timezone(timedelta(hours=8))).isoformat()
    context.update(generated_at=stamp, regenerated=regenerated)
    state = dict(status="error", version=context["version"], generated_at=stamp, regenerated=regenerated, files=[])
    output = evidence.contained(folder, "report")
    output.mkdir(exist_ok=True)
    try:
        contents = "<!-- Generated file: post-run report -->\n" + render(context)
        plain = html.unescape(contents)
        if evidence.sanitize(plain) != plain or re.search(r"account-acct|[A-Z]:[\\/]Users[\\/]|/home/", plain, re.I):
            raise ValueError("方案书包含不应公开的信息")
        target = evidence.contained(output, f"report-v{context['version']}.html")
        target.write_text(contents, encoding="utf-8", newline="\n")
        state["files"].append(dict(name=target.name, sha256=hashlib.sha256(target.read_bytes()).hexdigest()))
        render_pdf(target, state, browsers)
    except (OSError, ValueError, subprocess.SubprocessError):
        state["error"] = "方案书生成失败；已有HTML可用浏览器打印" if state["files"] else "方案书生成失败，请检查归档与公开信息"
    try:
        project = evidence.contained(ROOT / "projects", evidence.identifier(context["project_id"]))
        if project.is_dir() and state["files"]:
            destination = evidence.contained(project, f"reports/v{state['version']}")
            destination.mkdir(parents=True, exist_ok=True)
            for entry in state["files"]:
                shutil.copyfile(evidence.contained(output, entry["name"]), evidence.contained(destination, entry["name"]))
    except (OSError, ValueError):
        state["hint"] = "归档方案书已保存，项目副本未能写入"
    json_read = evidence.contained(folder, "run.json")
    metadata = json.loads(json_read.read_text(encoding="utf-8-sig"))
    metadata["report"] = state
    metadata.setdefault("artifacts", {}).update({"report/" + row["name"]: row["sha256"] for row in state["files"]})
    json_read.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return state


def render_pdf(target, state, browsers=None):
    from .pagination import paginate
    output = target.parent
    if browsers is None:
        browsers = [Path(os.environ.get(key, "")) / suffix
                    for suffix in ("Microsoft/Edge/Application/msedge.exe", "Google/Chrome/Application/chrome.exe")
                    for key in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA")]
    state.update(status="html-only", hint="可用浏览器打印成 PDF")
    failed = []
    for browser in dict.fromkeys(Path(path) for path in browsers if Path(path).is_file()):
        try:  # Codex review R06: a browser that leaves no real PDF is noted and the next one is tried
            with tempfile.TemporaryDirectory(prefix="guangzhu-report-") as temporary:
                pdf = Path(temporary) / "report.pdf"
                command = [str(browser), "--headless=new", "--disable-gpu", "--no-first-run", "--no-pdf-header-footer",
                           "--user-data-dir=" + str(Path(temporary) / "profile"), "--print-to-pdf=" + str(pdf), target.as_uri()]
                def print_once():
                    if pdf.exists():
                        pdf.unlink()
                    subprocess.run(command, check=True, timeout=60, capture_output=True,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                paginate(target, pdf, print_once)
                saved = evidence.contained(output, target.with_suffix(".pdf").name)
                saved.write_bytes(pdf.read_bytes())
        except (OSError, ValueError, subprocess.SubprocessError):
            failed.append(NAMES.get(browser.stem.lower(), browser.stem))
            continue
        state["files"].append(dict(name=saved.name, sha256=hashlib.sha256(saved.read_bytes()).hexdigest()))
        note = f"（{'、'.join(dict.fromkeys(failed))} 没转成 PDF，已改用 {NAMES.get(browser.stem.lower(), browser.stem)}）" if failed else ""
        state.update(status="ready", hint="运行结束后生成" + note)
        break
    if failed and state["status"] != "ready":
        names = list(dict.fromkeys(failed))
        state["error"] = "、".join(names) + (" 都" if len(names) > 1 else " ") + "没能转成 PDF；HTML 方案书已生成，可用浏览器打开后打印成 PDF"
    for entry in state['files']:
        if entry['name'] == target.name:
            entry['sha256'] = hashlib.sha256(target.read_bytes()).hexdigest()
    return state
