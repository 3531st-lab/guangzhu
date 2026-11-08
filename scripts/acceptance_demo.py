"""Run four synthetic cases through the real local API and verify downloaded artifacts.

The default mode changes only filesystem configuration to a new isolated root;
no engineering, weather, export, or API functions are mocked. ``--base-url``
runs the same actions against an already isolated installed application.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time
import traceback
from urllib.parse import urlparse
import uuid


SOURCE = Path(__file__).resolve().parents[1]
CASES = ("taizhou-cmc-pharma", "taizhou-shipbuilding-workshop",
         "taizhou-watertown-pavilion", "taizhou-lixiahe-coldchain")


def digest(value):
    return hashlib.sha256(value).hexdigest()


def json_digest(value):
    return digest(json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8"))


class RemoteClient:
    """Use the application's installed HTTP dependency for remote acceptance."""
    def __init__(self, session, base_url):
        self.session, self.base_url = session, base_url.rstrip("/")

    def request(self, method, path, **kwargs):
        return self.session.request(method, self.base_url + path, timeout=1800, **kwargs)


class Acceptance:
    def __init__(self, client, output, mode, run_root, prefix):
        self.client, self.output, self.prefix = client, output, prefix
        self.log = output.with_suffix(".log")
        self.value = dict(schema="guangzhu.acceptance/1", started_at=datetime.now(timezone.utc).isoformat(),
                          mode=mode, isolated_root=str(run_root) if run_root else None,
                          harness_sha256=digest(Path(__file__).read_bytes()),
                          basis="合成产业场景；真实缓存气象与计算；不代表实测工程或独立工程审核",
                          model_calls=0, physical_functions_mocked=False, cases=[], checks=[], requests=[])
        self.output.parent.mkdir(parents=True, exist_ok=True)
        self.log.write_text("", encoding="utf-8")
        self.save()

    def write(self, line):
        message = f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} {line}"
        print(message, flush=True)
        with self.log.open("a", encoding="utf-8") as stream:
            stream.write(message + "\n")

    def save(self):
        self.output.write_text(json.dumps(self.value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def check(self, case, name, condition, detail=None):
        passed = bool(condition)
        self.value["checks"].append(dict(case=case, name=name, passed=passed, detail=detail))
        self.save()
        self.write(f"{'PASS' if passed else 'FAIL'} {case}: {name}" + (f" ({detail})" if not passed else ""))
        if not passed:
            raise AssertionError(f"{case}: {name}: {detail}")

    def request(self, method, path, *, body=None, expected=200):
        self.write(f"{method} {path}")
        started = time.perf_counter()
        self.value["pending_request"] = dict(method=method, path=path, started_at=datetime.now(timezone.utc).isoformat())
        self.save()
        response = self.client.request(method, path, **({"json": body} if body is not None else {}))
        self.value.pop("pending_request", None)
        self.value["requests"].append(dict(method=method, path=path, status=response.status_code,
                                           elapsed_seconds=round(time.perf_counter() - started, 3)))
        self.save()
        if response.status_code != expected:
            raise AssertionError(f"{method} {path}: expected {expected}, received {response.status_code}: {response.text[:2500]}")
        return response

    def result(self, pid, version=None):
        suffix = f"?version={version}" if version is not None else ""
        return self.request("GET", f"/api/projects/{pid}/result{suffix}").json()

    def command(self, pid, version, **payload):
        result = self.request("POST", f"/api/projects/{pid}/copilot", body=dict(version=version, **payload)).json()
        self.check(pid, "command created a version", result.get("ok") and result["version"] > version, result)
        return result["version"]

    def verify_analysis(self, pid, result):
        version, summary = result["version"], result["summary"]
        self.check(pid, "result/design/analysis bind to requested version",
                   result["design"]["version"] == summary["version"] == version)
        self.check(pid, "analysis inputs and completion match",
                   result["evidence"]["analysis"].get("completion_status") == "matched", result["evidence"]["analysis"])
        self.check(pid, "annual computed generation is positive", summary["yield_kwh"]["p50"] > 0)
        economy = result["economics"]
        months = economy["analysis_metadata"]["yield_kwh"]["monthly_kwh"]
        self.check(pid, "twelve computed months sum to annual generation",
                   len(months) == 12 and abs(sum(row["ac_kwh"] for row in months) - summary["yield_kwh"]["p50"]) < 1,
                   dict(months=len(months), total=sum(row["ac_kwh"] for row in months), annual=summary["yield_kwh"]["p50"]))
        self.check(pid, "no fabricated independent review", not result["reviews"])
        electric = result["scene"]["electrical"]
        self.check(pid, "electrical calculation uses same version", electric["version"] == version)
        self.check(pid, "every array module is represented in electrical capacity",
                   abs(electric["dc_kw"] - summary["dc_kw"]) < .001 and len(result["design"]["modules"]) == summary["modules"])

    def run_case(self, template):
        entry = dict(template=template, started_at=datetime.now(timezone.utc).isoformat(), status="running")
        self.value["cases"].append(entry)
        self.save()
        begin = time.perf_counter()
        try:
            requested = f"{self.prefix}-{template.removeprefix('taizhou-')}"
            auto = self.request("POST", "/api/projects/auto-run", body=dict(
                template_id=template, project_id=requested, compare=False, export=False)).json()
            pid, version = auto["project_id"], auto["final_version"]
            entry.update(project_id=pid, initial_version=version, trace=auto)
            self.check(pid, "new unique project identity", pid == requested)
            self.check(pid, "rule workflow is explicitly identified", auto["workflow_kind"] == "rules")
            self.check(pid, "automatic run does not export or claim review",
                       auto["exported"] is False and auto["export_status"] == "not_requested"
                       and auto["independent_review"]["status"] == "not_performed")
            initial = self.result(pid, version)
            self.verify_analysis(pid, initial)
            self.check(pid, "case is identified as synthetic", "合成" in initial["project"]["name"])
            self.check(pid, "saved default selection matches auto result", self.result(pid)["version"] == version)
            self.check(pid, "automatic run has no hard rule failures", auto["hard_failed"] == 0, initial["rules"])
            original_design = json_digest(initial["design"])
            before_versions = initial["versions"]
            rejected = self.request("POST", "/api/projects/auto-run", expected=422,
                                    body=dict(project_id=pid, template_id="unknown-acceptance-template", overwrite_existing=True))
            unchanged = self.result(pid, version)
            self.check(pid, "invalid repeated request preserves prior project and design",
                       json_digest(unchanged["design"]) == original_design and unchanged["versions"] == before_versions,
                       rejected.json())
            self.request("POST", f"/api/projects/{pid}/copilot", expected=422,
                         body=dict(version=version, text="这不是可执行的设计指令"))
            self.check(pid, "unrecognized command creates no version", self.result(pid, version)["versions"] == before_versions)
            self.request("GET", f"/api/projects/{pid}/download/dxf?version={version}", expected=409)
            self.check(pid, "download cannot create an export", not self.result(pid, version)["files"])

            # Each case exercises a different meaningful edit, using the same
            # public command route as the desktop interface.
            if template == "taizhou-cmc-pharma":
                version = self.command(pid, version, action="change_equipment", inverter_id="solis-s5-gc60k")
                edited = self.result(pid, version)
                self.check(pid, "brand/model edit reaches electrical calculation",
                           edited["scene"]["electrical"]["inverter_id"] == "solis-s5-gc60k")
                self.check(pid, "extended inverter inputs remain explicitly unverified",
                           "unverified" in json.dumps(edited["scene"]["electrical"], ensure_ascii=False))
            elif template == "taizhou-shipbuilding-workshop":
                copper = initial["scene"]["electrical"]["cables"]["ac"]
                self.check(pid, "initial copper cable material is explicit", copper and all(row["material"] == "copper" for row in copper))
                version = self.command(pid, version, action="change_equipment", ac_cable_family="YJLH22")
                aluminum = self.result(pid, version)["scene"]["electrical"]["cables"]["ac"]
                self.check(pid, "aluminum cable selection uses aluminum catalogue data",
                           aluminum and all(row["material"] == "aluminum" and row["cable_id"].upper().startswith("YJLH22-") for row in aluminum), aluminum)
                entry["cable_comparison"] = dict(copper=copper, aluminum=aluminum)
            elif template == "taizhou-watertown-pavilion":
                target = round(initial["summary"]["dc_kw"] * .9, 3)
                version = self.command(pid, version, text=f"把容量调整到 {target} kW")
                edited = self.result(pid, version)
                self.check(pid, "capacity request reduces actual saved modules",
                           0 < edited["summary"]["dc_kw"] <= target and edited["summary"]["modules"] < initial["summary"]["modules"],
                           dict(target=target, actual=edited["summary"]["dc_kw"]))
            else:
                compared = self.request("POST", f"/api/projects/{pid}/copilot",
                                        body=dict(version=version, action="compare")).json()
                version = compared["version"]
                comparison = self.result(pid, version)
                self.check(pid, "comparison creates real versioned candidates",
                           comparison.get("compare") and len(comparison["compare"]["options"]) >= 3,
                           comparison.get("compare"))
                self.check(pid, "comparison selects its recommended version explicitly",
                           self.result(pid)["version"] == version)
                version = self.command(pid, version, text="把倾角改成12度")
                self.check(pid, "tilt request changes saved geometry parameters",
                           self.result(pid, version)["design"]["params"]["tilt_deg"] == 12)

            # A normal equipment recompute saves a new version and executes the
            # real analysis again. Rule repair retains all intermediate versions.
            version = self.command(pid, version, action="change_equipment")
            recomputed = self.result(pid, version)
            if recomputed["rules"]["hard_failed"]:
                repaired = self.request("POST", f"/api/projects/{pid}/copilot",
                                        body=dict(version=version, action="auto_fix")).json()
                version = repaired["version"]
            final = self.result(pid, version)
            self.verify_analysis(pid, final)
            self.check(pid, "edited candidate passes implemented hard rules", final["rules"]["hard_failed"] == 0, final["rules"])
            self.check(pid, "original design is append-only", json_digest(self.result(pid, entry["initial_version"])["design"]) == original_design)
            self.check(pid, "latest local selection survives reload", self.result(pid)["version"] == version)
            entry.update(final_version=version, summary=final["summary"], rules=final["rules"],
                         analysis_evidence=final["evidence"]["analysis"])
            report = self.request("GET", f"/api/projects/{pid}/report-html?version={version}")
            self.check(pid, "candidate report states no independent review",
                       "候选方案" in report.text and "尚未独立审核" in report.text)
            self.check(pid, "report identifies requested version", f"v{version}" in report.text)
            old_report = self.request("GET", f"/api/projects/{pid}/report-html?version={entry['initial_version']}")
            self.check(pid, "older report retains requested design version", f"v{entry['initial_version']}" in old_report.text)
            artifact_dir = self.output.parent / (self.output.stem + "-artifacts") / pid
            artifact_dir.mkdir(parents=True, exist_ok=True)
            (artifact_dir / f"candidate-v{version}.html").write_text(report.text, encoding="utf-8")
            preview = self.request("POST", f"/api/projects/{pid}/exports/preview", body=dict(version=version)).json()
            self.check(pid, "export preview is ready and bound to this version",
                       preview["ready"] and preview["version"] == version and preview.get("approval_id"), preview)
            self.check(pid, "preview does not generate files", not self.result(pid, version)["files"])
            approval = dict(version=version, approval_id=preview["approval_id"], confirmed=True)
            self.request("POST", f"/api/projects/{pid}/exports/approve", body=approval | dict(confirmed=False), expected=400)
            exported = self.request("POST", f"/api/projects/{pid}/exports/approve", body=approval).json()
            self.check(pid, "export approval is explicitly local and single-use",
                       exported["approval"]["kind"] == "local-user" and exported["approval"]["status"] == "approved-once"
                       and exported["version"] == version)
            self.request("POST", f"/api/projects/{pid}/exports/approve", body=approval, expected=409)
            self.check(pid, "single-use approval cannot be replayed", True)
            self.verify_downloads(pid, version, final, exported, artifact_dir)
            report = self.request("GET", f"/api/projects/{pid}/report-html?version={version}")
            self.check(pid, "report shows local approval without claiming independent review",
                       "本地用户已批准一次初步方案文件导出" in report.text and "尚未独立审核" in report.text)
            (artifact_dir / f"approved-v{version}.html").write_text(report.text, encoding="utf-8")
            reopened = self.result(pid)
            self.check(pid, "reopened project retains selected version and geometry",
                       reopened["version"] == version and json_digest(reopened["design"]) == json_digest(final["design"]))
            rows = self.request("GET", "/api/projects/local-list").json()["projects"]
            self.check(pid, "saved project list includes final export", any(row["project_id"] == pid and row["exported"] for row in rows))
            entry.update(status="passed", artifacts=str(artifact_dir), manifest_sha256=exported["manifest_sha256"])
        except Exception as error:
            entry.update(status="failed", error=str(error), traceback=traceback.format_exc())
            self.write(f"CASE FAILED {template}: {error}")
            self.save()
        finally:
            entry["elapsed_seconds"] = round(time.perf_counter() - begin, 3)
            self.save()

    def verify_downloads(self, pid, version, result, exported, directory):
        import ezdxf
        from openpyxl import load_workbook
        for kind, prefix in (("dxf", "layout"), ("xlsx", "bom")):
            response = self.request("GET", f"/api/projects/{pid}/download/{kind}?version={version}")
            name = f"{prefix}-v{version}.{kind}"
            self.check(pid, f"{kind} download matches export manifest", digest(response.content) == exported["files"][name])
            (directory / name).write_bytes(response.content)
        drawing = ezdxf.readfile(directory / f"layout-v{version}.dxf")
        modules = list(drawing.modelspace().query('LWPOLYLINE[layer=="PV"]'))
        self.check(pid, "DXF contains exact saved module count", len(modules) == result["summary"]["modules"])
        self.check(pid, "DXF preserves version label", any(f"v{version}" in item.dxf.text for item in drawing.modelspace().query("TEXT")))
        book = load_workbook(directory / f"bom-v{version}.xlsx", data_only=True)
        materials = list(book["材料清单"].values)
        module = next(row for row in materials if row[0] == "组件")
        self.check(pid, "XLSX module quantity matches saved design", module[4] == result["summary"]["modules"])
        cable_rows = [row for row in materials[1:] if row[0] in ("直流电缆", "交流电缆")]
        electric = result["scene"]["electrical"]
        cables = electric["cables"]["summary"]
        self.check(pid, "XLSX has one row per cable catalogue entry", len(cable_rows) == len(cables))
        for cable in cables:
            row = next(row for row in cable_rows if row[11] == cable["cable_id"])
            self.check(pid, "XLSX cable identity/material/unit price matches computation " + cable["cable_id"],
                       row[2] == cable["cable_model"] and cable["material"] in row[7]
                       and abs(row[8] - cable["unit_price_cny_m"]) < .00001)
        book.close()


def isolated_client(stack, output, run_root):
    """Set data paths before importing the application; preserve all real code."""
    root = run_root or Path(tempfile.mkdtemp(prefix="acceptance-source-", dir=output.parent))
    root = root.resolve()
    if (root / "projects").exists():
        raise ValueError("An existing projects directory cannot be used as a source acceptance root")
    root.mkdir(parents=True, exist_ok=True)
    for relative in ("data/demo", "data/catalog", "backend", ".agh"):
        shutil.copytree(SOURCE / relative, root / relative)
    (root / "desktop/web").mkdir(parents=True)
    (root / "projects").mkdir()
    sys.path[:0] = [str(SOURCE / "backend"), str(SOURCE / "scripts")]
    from guangzhu import config
    config.ROOT, config.DATA_DIR, config.PROJECTS_DIR, config.RUNS_DIR = root, root / "data", root / "projects", root / "runs"
    from guangzhu import api
    from fastapi.testclient import TestClient
    client = stack.enter_context(TestClient(api.app, base_url=config.API_ORIGIN,
                                            headers={"origin": config.API_ORIGIN}, raise_server_exceptions=True))
    return client, root


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", help="Loopback URL of an already isolated installed application")
    parser.add_argument("--run-root", type=Path, help="New empty source data root; never point at a real project directory")
    parser.add_argument("--output", type=Path, default=SOURCE / "output/reliability-repair-20261104/acceptance-source.json")
    parser.add_argument("--cases", nargs="+", choices=CASES, default=list(CASES))
    parser.add_argument("--prefix", default="accept-" + uuid.uuid4().hex[:8])
    args = parser.parse_args()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with ExitStack() as stack:
        if args.base_url:
            parsed = urlparse(args.base_url)
            if parsed.scheme != "http" or parsed.hostname != "127.0.0.1":
                parser.error("--base-url must be an explicit http://127.0.0.1:<port> isolated application")
            import requests
            session = stack.enter_context(requests.Session())
            session.headers.update({"origin": args.base_url.rstrip("/")})
            client = RemoteClient(session, args.base_url)
            root = None
        else:
            client, root = isolated_client(stack, output, args.run_root)
        acceptance = Acceptance(client, output, "installed-http" if args.base_url else "source-testclient", root, args.prefix)
        for case in args.cases:
            acceptance.run_case(case)
        acceptance.value["finished_at"] = datetime.now(timezone.utc).isoformat()
        acceptance.value["passed"] = all(row["status"] == "passed" for row in acceptance.value["cases"])
        acceptance.value["check_count"] = len(acceptance.value["checks"])
        acceptance.value["passed_checks"] = sum(row["passed"] for row in acceptance.value["checks"])
        acceptance.save()
        acceptance.write(f"Finished: passed={acceptance.value['passed']}; checks={acceptance.value['passed_checks']}/{acceptance.value['check_count']}; evidence={output}")
        return 0 if acceptance.value["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
