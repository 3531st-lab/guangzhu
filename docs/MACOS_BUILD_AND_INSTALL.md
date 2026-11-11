# 光筑 macOS 版（苹果电脑 Apple Silicon / Intel）构建与安装说明

光筑已完成针对苹果电脑（**macOS 11 Big Sur 及以上**，同时支持 **Apple Silicon M1/M2/M3/M4 `arm64`** 与 **Intel `x86_64`**）的原生化适配与独立 `.app` / `.dmg` 打包工程建设，功能与 Windows 0.3.0 版保持 100% 同步。

---

## 一、macOS 版核心架构与适配要点

1. **原生窗口与硬件加速三维引擎**：
   - 采用 macOS 系统内置的 **AppKit + WKWebView (`cocoa`)** 替代 Windows Edge WebView2，无需用户额外下载任何浏览器运行时，直接调用 Apple Metal 加速 WebGL2 渲染厂房高低跨三维孪生、阴影追踪与园区全景。
   - 内置多分辨率苹果官方格式图标 [guangzhu.icns](file:///c:/Users/华硕/Documents/ChatGPT/guangzhu/desktop/web/assets/guangzhu.icns)（16px–1024px Retina）与原生 Mach-O 启动器 [launcher_macos.c](file:///c:/Users/华硕/Documents/ChatGPT/guangzhu/installer/macos/launcher_macos.c)（进程内加载 `libpython3.12.dylib`，程序坞仅显示单一“光筑”图标，顶部菜单栏原生显示“光筑”）。
2. **只读签名应用包 + 用户数据升级保留（符合 Apple Gatekeeper 规范）**：
   - `/Applications/光筑.app` 内部保持 100% 只读，运行期绝不向 `.app` 包内写入缓存或工程文件，确保 `codesign` 签名永久有效，即使直接在只读 `.dmg` 镜像或 App Translocation 下双击也不会报只读错误。
   - 首次启动或拖入新版升级时，由 [bootstrap_macos.py](file:///c:/Users/华硕/Documents/ChatGPT/guangzhu/installer/macos/bootstrap_macos.py) 与 [sync_macos_workspace.py](file:///c:/Users/华硕/Documents/ChatGPT/guangzhu/scripts/sync_macos_workspace.py) 自动将只读代码与标准目录同步至用户目录 `~/Library/Application Support/Guangzhu/workspace/`，完整保留用户的 `projects/`（我的工程）、`data/myroofs/`（自绘屋顶）、`data/parks/`（园区）与 `desktop/settings.json`。
3. **跨平台系统调用、中文字体与快捷键闭环**：
   - 文件打开与定位：方案书 PDF、BOM 表格、CAD DXF 导出自动调用 macOS 原生预览与 `open -R`（在 Finder 中高亮定位文件）。
   - 中文排版无乱码：Matplotlib 工程图纸与方案书 PDF（[pdf_generator.py](file:///c:/Users/华硕/Documents/ChatGPT/guangzhu/backend/guangzhu/report/pdf_generator.py)）及前端 Retina Canvas 优先匹配苹果系统字体 `PingFang SC`（苹方）、`Hiragino Sans GB`、`Heiti SC`。
   - 键盘交互：全面支持 Mac `Command (⌘)` 快捷键（`⌘+Z` 撤销、`⌘+Y` 重做、`⌘+点击` 三维组件多选）。

---

## 二、获取或打出 `.dmg` 安装包的两种方式

> **说明**：由于苹果 Mach-O 原生扩展（`PySAM`、`scipy`、`shapely`、`PyObjC`）与 `codesign` / `hdiutil` 磁盘镜像工具只能在 macOS 系统上运行，Windows 电脑无法在本地直接交叉生成 `.dmg` 二进制文件。仓库已同时提供**云端一键自动打包**与**苹果电脑本地一键打包**两条路径。

### 方式 A：手边只有 Windows 电脑时——用 GitHub Actions 云端自动打出 `.dmg`
仓库已内置工作流 [build-macos.yml](file:///c:/Users/华硕/Documents/ChatGPT/guangzhu/.github/workflows/build-macos.yml)：
1. 将当前代码推送至 GitHub 仓库；
2. 打开 GitHub 仓库页面 → **Actions** → 选择左侧 **Build macOS Desktop App (.dmg)** → 点击右上角 **Run workflow**；
3. GitHub 官方苹果服务器会并行运行前端/后端测试，并自动打包两份免环境独立安装镜像（在构建结果页面底部 **Artifacts** 直接下载）：
   - `guangzhu-0.3.0-macos-arm64.dmg`（适用于 M1 / M2 / M3 / M4 苹果芯片 Mac）
   - `guangzhu-0.3.0-macos-x64.dmg`（适用于旧款 Intel 芯片 Mac）

### 方式 B：在苹果电脑（Mac）上直接一键打包或开发运行
将本仓库拷贝到 Mac 电脑后：

- **一键生成独立免环境 `.dmg` 安装包**（自动拉取独立 Python 3.12 运行时并完成内置 `PySAM` 离线自检与签名）：
  ```bash
  chmod +x scripts/build_macos_dmg.sh
  bash scripts/build_macos_dmg.sh
  ```
  生成产物位于 `dist/guangzhu-0.3.0-macos-arm64.dmg`（或 `x64.dmg`）。若需一并打入官方 AGH macOS 运行时，可附加参数 `--agh-archive /path/to/agnes-darwin-arm64.tar.gz`。

- **开发模式直接启动窗口**（无需打 DMG，适合现场调试）：
  直接在 Finder 中双击仓库根目录下的 `start-mac.command`（或在终端运行 `bash start-mac.command`），脚本会自动创建 `.venv`、运行自检并拉起原生桌面窗口。

---

## 三、macOS 用户安装与首次打开说明

1. 双击打开 `guangzhu-0.3.0-macos-arm64.dmg`（或 `x64.dmg`），将 **光筑.app** 拖入右侧 **Applications（应用程序）** 文件夹。
2. **首次打开未公证测试包提示**：若打包时使用的是默认本地签名（`ad-hoc` 签名，未配置 Apple Developer ID 付费公证证书），首次在“应用程序”中打开时：
   - 请**按住 Control 键点击（或右键点击）`光筑.app` → 选择“打开” → 在弹窗中再次点击“打开”**；
   - 若 macOS 15 Sequoia 提示需放行隔离属性，可在终端执行一次：
     ```bash
     xattr -cr /Applications/光筑.app
     ```
   此后即可像普通 Mac 软件一样从程序坞（Dock）或启动台直接双击秒开。
