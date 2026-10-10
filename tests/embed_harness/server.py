"""T10 localhost test page; serves no AGH credentials or model requests."""

import argparse
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
ORIGIN = "http://127.0.0.1:8765"
PRESETS = {
    "changzhou-demo": ("常州：6 年回本", "6 年内回本，留 1 米检修通道，别挡天窗", ["--payback", "6", "--walkway", "1", "--keep", "sky-1"]),
    "l-shape": ("L 形：30 万预算", "总预算最多 30 万元，要留 1 米检修通道，别挡天窗", ["--budget", "30", "--walkway", "1", "--keep", "sky"]),
    "rotated": ("旋转：15–20 度倾角", "组件倾角必须在 15–20 度之间，要留 1 米检修通道，别挡天窗", ["--tilt", "15", "20", "--walkway", "1", "--keep", "sky-1"]),
    "impossible": ("做不到：5 万 / 300 kW", "预算 5 万元，装机不少于 300 千瓦", ["--budget", "5", "--capacity-min", "300"]),
}


def make_brief(payload):
    sample = payload.get("sample", "changzhou-demo")
    _, text, flags = PRESETS[sample]
    template = "l-shape" if sample == "impossible" else sample
    identifier = payload["id"]
    if not re.fullmatch(r"t10-[A-Za-z0-9_-]{1,59}", identifier):
        raise ValueError("测试项目编号必须以 t10- 开头，且不超过 63 字符")
    args = [sys.executable, "-m", "guangzhu.brief", "--template", template, "--id", identifier, "--text", text, *flags,
            "--reviewer-model", payload.get("reviewer_model", "agnes-3.0-flash")]
    if payload.get("review_mode") is not None:
        args.extend(["--review-mode", payload["review_mode"]])
    result = subprocess.run(args, cwd=ROOT, env={**os.environ, "PYTHONPATH": str(ROOT / "backend")},
                            capture_output=True, text=True, encoding="utf-8", check=True)
    return {"brief": result.stdout.rstrip("\r\n"), "project_id": identifier, "command": ["python", *args[1:]]}


def sanitized(value):
    text = json.dumps(value, ensure_ascii=False)
    text = re.sub(r"(?i)[A-Z]:\\+(?:Users|Documents and Settings)\\+[^\\\"\s]+", "%USERPROFILE%", text)
    text = re.sub(r"(?i)(?:sk-|api[_-]?key[=: ]+)[A-Za-z0-9_-]{8,}", "[REDACTED]", text)
    value = json.loads(text)
    def clean(item):
        if isinstance(item, dict):
            return {key: ("[REDACTED]" if re.search(r"(?i)^(?:api.?key|token|password|authorization|credential|secret)$", key) else clean(val)) for key, val in item.items()}
        if isinstance(item, list):
            return [clean(val) for val in item]
        return item
    return clean(value)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(HERE), **kwargs)

    def log_message(self, format, *args):
        pass

    def reply(self, value, status=200):
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/api/presets":
            return self.reply([{ "id": key, "label": value[0]} for key, value in PRESETS.items()])
        if path == "/desktop/web/steps.js":
            body = (ROOT / "desktop/web/steps.js").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/javascript; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            return self.wfile.write(body)
        if path not in ("/", "/index.html", "/app.js", "/style.css", "/session-runs.js"):
            return self.reply({"error": "not found"}, 404)
        return super().do_GET()

    def do_POST(self):
        if self.headers.get("Origin") != ORIGIN or self.headers.get("Host") != "127.0.0.1:8765":
            return self.reply({"error": "origin rejected"}, 403)
        try:
            size = int(self.headers.get("Content-Length", 0))
            if not 0 < size < 16_000_000:
                raise ValueError("invalid payload size")
            payload = json.loads(self.rfile.read(size))
            if self.path == "/api/brief":
                return self.reply(make_brief(payload))
            if self.path in ("/api/log", "/api/save"):
                name = payload["name"]
                if not re.fullmatch(r"t10-[A-Za-z0-9_-]{1,100}", name):
                    raise ValueError("invalid log name")
                data = sanitized(payload["data"])
                directory = self.server.log_dir
                directory.mkdir(parents=True, exist_ok=True)
                suffix = ".messages.jsonl" if self.path == "/api/log" else ".snapshot.json"
                destination = directory / (name + suffix)
                if self.path == "/api/log":
                    with destination.open("a", encoding="utf-8") as stream:
                        stream.write(json.dumps(data, ensure_ascii=False) + "\n")
                else:
                    destination.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                return self.reply({"saved": destination.name})
            return self.reply({"error": "not found"}, 404)
        except (ValueError, KeyError, TypeError, subprocess.CalledProcessError):
            return self.reply({"error": "请求不正确或任务书生成失败；检查样例、项目编号与审核模型"}, 400)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log-dir", type=Path, default=ROOT / "reports/assets/T10-spike/messages")
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", 8765), Handler)
    server.log_dir = args.log_dir.resolve()
    print(f"T10 embed harness: {ORIGIN}\nLogs: {server.log_dir}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
