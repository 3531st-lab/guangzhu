# 安装、运行与复现

复现分为三层：不调用模型的离线计算、已归档真实运行的核验，以及由自己的模型账号发起的新设计。前两层不需要 AGH 正在运行，也不产生模型调用费。

## 环境与源码安装

- Windows 10/11 x64，Python 3.12（建议 3.12.10）、Git。
- 桌面界面需要 WebView2；PDF 和浏览器测试需要系统 Microsoft Edge。
- 重建插件与运行 JavaScript 测试需要 Node.js / npm；本次核验版本见 [开源检查记录](OPEN_SOURCE_CHECKLIST.md)。
- 首次安装需要访问 PyPI；依赖通过 `requirements.lock.txt`、`requirements-dev.txt` 锁定，Python 安装路径可用 `-Python` 参数指定。

```powershell
git clone https://github.com/3531st-lab/guangzhu.git
cd guangzhu
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup.ps1
```

Python 不在默认目录时，将最后一行改为：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup.ps1 -Python 'C:/path/to/Python312/python.exe'
```

安装脚本会创建 `.venv`、安装依赖和光筑包，最后运行依赖 / PySAM 原生加载自检，成功时输出“全部通过”。不要使用无版本锁定的 `requirements.txt` 代替锁文件做复现。

若 PyPI 下载超时，可在当前 PowerShell 设置 `$env:PIP_DEFAULT_TIMEOUT = '120'` 后重跑安装脚本；已有下载缓存会复用。下载失败不等于安装成功，必须等到自检通过。

## 1. 离线计算

在仓库根目录执行：

```powershell
.\.venv\Scripts\python.exe -m guangzhu.selfcheck
.\.venv\Scripts\python.exe -c "from guangzhu.selfcheck import offline_analysis; import json; r=offline_analysis(); print(json.dumps(r, ensure_ascii=False, indent=2)); raise SystemExit(0 if r['passed'] else 1)"
```

第二条命令使用 `data/demo/projects/changzhou-demo` 创建临时项目，从本地天气快照计算排板、发电、规则与经济结果，并检查 PySAM 原生计算；结束后清理本次临时项目。成功标准是 `passed: true`、`failures: []`、正的 P50 与 PySAM 发电量及退出码 0。该默认参数计算不是历史 Agent 选定的最终方案，不能拿它冒充 51/54 的历史评测。

太阳位置也可从公开响应录样重算：

```powershell
.\.venv\Scripts\python.exe scripts/check_official_sun.py
```

它读取 `data/field/sun-official/`，更新 `reports/assets/T12/sun-official.md` 等计算输出。NASA / PVGIS 原始缓存不需要从开发者电脑复制。

## 2. 核验公开的真实设计与独立审核

仓库包含 `runs/gz-changzhou-demo-1008-2113/`，其中保存设计会话、独立审核会话、版本、导出结果和原生账本。以下命令重新读取账本并写入 `verification.json`，不调用模型：

```powershell
.\.venv\Scripts\python.exe scripts/agh_verify_run.py runs/gz-changzhou-demo-1008-2113/captures/fff0c410d7ef366cd4d3 --review-run runs/gz-changzhou-demo-1008-2113/reviews/42cd14cf5d1c2743bc94
```

成功标准：任务规划、能力调用、反馈处理、结果验证逐项通过，独立审核通过，退出码 0。核验重新计算校验结果，不重写原始 `ledger.agnes.jsonl`。

没有 AGH / key 也可以启动本机网页查看公开案例：

```powershell
.\.venv\Scripts\python.exe -m uvicorn guangzhu.api:app --host 127.0.0.1 --port 8765
```

打开 `http://127.0.0.1:8765/`；未启动 AGH 时嵌入会话区不可用，回放和已有结果不等同于发起新设计。

## 3. 运行自动测试

```powershell
.\.venv\Scripts\python.exe -m pytest -q
node --test agh-plugin/guangzhu-studio/test/*.test.js
node --test tests/embed_harness/*.test.mjs
node --test tests/desktop/*.test.mjs
.\.venv\Scripts\python.exe scripts/check_secrets.py
```

`pytest` 默认排除 `network` 标记；浏览器测试使用系统 Edge。公共仓库没有全部历史过程归档，`tests/conftest.py` 对明确依赖缺失归档的历史用例记录 skip；应分别报告通过、跳过、失败数，不把跳过计为通过，也不引用内部全量仓库的测试数替代本次结果。

插件源码与生成文件的独立一致性检查：

```powershell
npm --prefix agh-plugin/guangzhu-studio ci
.\.venv\Scripts\python.exe scripts/build_agh_plugin.py --check --release
```

## 4. 用自己的模型发起设计

按 [CONFIGURATION.md](CONFIGURATION.md) 创建本机配置，再按 [AGH_SETUP.md](AGH_SETUP.md) 配好完整 AGH 运行目录、12 个 MCP 工具、插件、Skill 与模型。最后运行：

```powershell
.\start.cmd
```

AGH 是所有模型调用的唯一入口。使用自己的 key 和新项目编号，保留实际模型、需求、数据、工具输出、审批和独立审核记录。模型改版、随机性和天气变化会影响结果；新运行不保证与历史案例逐字或逐数相同。

## 5. 安装包构建与历史评测的范围

完整安装器构建除了源码还需要原始官方 AGH ZIP 和固定提交的 AGH 源码；获取方式及不可替代的摘要见 [DEPENDENCIES.md](DEPENDENCIES.md)。取得这些输入后，在根目录显式传入本机路径：

```powershell
powershell -NoProfile -File scripts/build_installer.ps1 -AghArchive 'C:/inputs/agnes-win32-x64-5da4073.zip' -AghSource 'C:/src/agnes-harness'
```

脚本校验原始 ZIP、源码 revision、Python 和 Inno Setup 的来源，输出 `dist/guangzhu-setup.exe`。未取得原 ZIP 时只能核验公开安装包及源码运行，不能宣称本次重新构建成功。本次补充文档不替换既有 v0.2.0 安装器。

24 个评测任务在 `eval/cases.json`，驱动和评分器在 `scripts/eval_run.py`、`scripts/eval_score.py`。评分器需要完整的运行归档，公开仓库的单个案例不足以重算历史 51/54。批量驱动保留历史时间截止和费用约束，重新做评测须明确新的实验窗口、预算、模型和数据版本；不要把 `--plan` 的任务列表当作实跑结果。
