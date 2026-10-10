"""安装自检；不联网，也不读取任何凭据。"""

import importlib
from importlib.metadata import version
import platform
import json
import shutil
import subprocess
import sys
import uuid

from .config import DATA_DIR, PROJECTS_DIR, RUNS_DIR

DEPENDENCIES = {
    "pvlib": "pvlib", "nrel-pysam": "PySAM", "pandas": "pandas",
    "numpy": "numpy", "scipy": "scipy", "shapely": "shapely",
    "requests": "requests", "pydantic": "pydantic", "fastapi": "fastapi",
    "uvicorn": "uvicorn", "mcp": "mcp", "ezdxf": "ezdxf",
    "openpyxl": "openpyxl", "matplotlib": "matplotlib", "jinja2": "jinja2",
    "pytest": "pytest",
}


def offline_analysis():
    """Run a real temporary Changzhou design, including native PySAM, then remove it."""
    from . import analysis, layout, project as storage, templates
    identifier = "selfcheck-" + uuid.uuid4().hex
    temporary = storage._path(identifier)
    if temporary.exists():
        return {"passed": False, "failures": ["临时项目编号已存在"]}
    try:
        project = storage.init(templates.resolve("changzhou-demo").parent, identifier)
        design = layout.generate_layout(project, {})
        storage.save_design(identifier, design)
        summary = analysis.analyze(identifier, design.version, offline=True)
        saved = json.loads((temporary / f"analysis/v{design.version}/summary.json").read_text(encoding="utf-8"))
        cash = json.loads((temporary / f"analysis/v{design.version}/economics.json").read_text(encoding="utf-8"))
        native = cash["generation"]["results"]["c"]
        if saved != summary or not summary["ok"] or summary["yield_kwh"]["p50"] <= 0 or native["annual_kwh"] <= 0:
            raise RuntimeError("离线分析或 PySAM 原生计算未返回有效结果")
        result = {"passed": True, "summary": summary, "pysam_kwh": native["annual_kwh"], "failures": []}
    except Exception as error:
        result = {"passed": False, "failures": [f"{type(error).__name__}: {error}"]}
    finally:
        if temporary.exists():
            try:
                shutil.rmtree(temporary)
            except OSError as error:
                result["passed"] = False
                result["failures"].append(f"临时项目清理失败: {error}")
    return result


def selfcheck():
    """返回结构化检查结果，供安装脚本和测试共用。"""
    failures = []
    versions = {"Python": platform.python_version()}
    if platform.python_version_tuple()[:2] != ("3", "12"):
        failures.append("需要 Python 3.12")
    for distribution, module in DEPENDENCIES.items():
        try:
            importlib.import_module(module)
            versions[distribution] = version(distribution)
        except Exception as exc:
            failures.append(f"{distribution}: {type(exc).__name__}")
    # 原生扩展在子进程中验证；DLL 加载失败不能终止整份自检。
    try:
        native = subprocess.run(
            [sys.executable, "-B", "-c", "from guangzhu.native_runtime import prepare_pysam; "
             "prepare_pysam(); import PySAM.Pvwattsv8 as p; "
             "p.default('PVWattsNone')"],
            capture_output=True, timeout=60,
        )
        if native.returncode:
            failures.append(f"nrel-pysam 原生模块失败: exit {native.returncode}")
    except (OSError, subprocess.TimeoutExpired) as exc:
        failures.append(f"nrel-pysam 原生模块检查失败: {type(exc).__name__}")
    for directory in (DATA_DIR, PROJECTS_DIR, RUNS_DIR):
        if not directory.is_dir():
            failures.append(f"目录不存在: {directory.name}/")
    return {"passed": not failures, "versions": versions, "failures": failures}


def main():
    result = selfcheck()
    for name, dependency_version in result["versions"].items():
        print(f"{name}: {dependency_version}")
    for failure in result["failures"]:
        print(f"失败: {failure}")
    print("全部通过" if result["passed"] else "自检失败")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
