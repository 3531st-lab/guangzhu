# 配置模板

源码版读取 `desktop/settings.json`。从 [settings.example.json](../desktop/settings.example.json) 复制后填写本机的绝对路径：

```powershell
Copy-Item desktop/settings.example.json desktop/settings.json
notepad desktop/settings.json
```

JSON 中建议使用 `/`；使用反斜杠时写成 `\\`。`YOUR_WINDOWS_USER` 必须替换，程序不会展开 JSON 中的 `%USERPROFILE%`、`$env:...` 或 `~`。用 UTF-8 保存，不填任何模型密钥。

| 配置项 | 含义 |
| --- | --- |
| `agh_runtime` | 完整官方运行目录内 `agnes-win32-x64.exe` 的绝对路径。可以使用公开安装包安装后的 `%LOCALAPPDATA%/Programs/guangzhu/runtime/agh/agnes-win32-x64.exe`，但须先将环境变量展开为真实路径 |
| `agh_home` | 源码版专用的 AGH 实例目录。不要指向安装版或其他项目的凭据目录 |
| `agh_profile` | 使用 `local-dev`；桌面启动流程按该 profile 注册和运行 |

没有配置文件时保留历史开发目录默认值；换电脑运行时应显式配置。安装版由首次配置流程管理运行包和实例，不读取源码版的这个文件。

## 可选环境变量

| 变量 | 用途 |
| --- | --- |
| `GUANGZHU_NATIVE_CACHE` | PySAM 原生扩展缓存目录；设为可写的纯 ASCII 绝对路径。通常无需设置 |
| `GUANGZHU_DATA_HOME` | 安装版配置、日志与实例数据的基目录；不改变源码版 `projects/` 和 `runs/` 的路径 |
| `GUANGZHU_TEST_PYTHON` | JavaScript 测试调用的 Python，默认使用仓库 `.venv/Scripts/python.exe` |
| `AGH_HOME` | 手动运行 AGH CLI 时指定同一个 `agh_home`；不用于填写模型密钥 |

端口由 `backend/guangzhu/config.py` 固定：源码版光筑 8765、AGH 4177；安装版 8766、4178。以上均只在 `127.0.0.1` 上使用。

项目没有 dotenv 加载器，不会自动读取 `.env`。个人配置、`.env*`、私钥、用户屋顶、下载缓存及新运行目录由 `.gitignore` 排除；已跟踪文件不会因为新增忽略规则自动退出 Git。

AGH 接入、MCP 注册与模型设置见 [AGH_SETUP.md](AGH_SETUP.md)。
