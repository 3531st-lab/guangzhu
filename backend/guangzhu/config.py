"""路径以仓库为基准，与调用者当前目录无关。"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# 安装版和开发版用不同端口，同一台电脑上两者同时运行也不冲突。
INSTALLED = (ROOT / "build-manifest.json").is_file()
API_PORT, AGH_PORT = (8766, 4178) if INSTALLED else (8765, 4177)
API_ORIGIN, AGH_ORIGIN = f"http://127.0.0.1:{API_PORT}", f"http://127.0.0.1:{AGH_PORT}"
DATA_DIR = ROOT / "data"
PROJECTS_DIR = ROOT / "projects"
RUNS_DIR = ROOT / "runs"
SHADING_THRESHOLD_PCT = 8.0  # 示意：总遮挡损失百分比阈值
SHADING_AVG_THRESHOLD_PCT = 3.0  # 示意：方案平均遮挡提醒。
DC_AC_MIN, DC_AC_MAX, DC_AC_TARGET = 1.0, 1.3, 1.2  # 示意：容配比范围及选型目标。
