/*
 * 光筑.app native macOS Mach-O launcher (Apple Silicon arm64 & Intel x86_64).
 *
 * Embeds bundled libpython3.12.dylib in-process so macOS registers a single
 * Dock icon (`guangzhu.icns`), menu bar title (`光筑`), and bundle identity
 * (`cn.guangzhu.desktop`), while still forwarding CLI invocations (`-B -c ...`)
 * when `sys.executable` is used for isolated subprocess checks.
 */

#include <dlfcn.h>
#include <libgen.h>
#include <limits.h>
#include <mach-o/dyld.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>

typedef int (*py_bytes_main_fn)(int, char **);

static void show_native_alert(const char *message) {
    pid_t pid = fork();
    if (pid == 0) {
        execl(
            "/usr/bin/osascript",
            "osascript",
            "-e", "on run argv",
            "-e", "display alert \"光筑\" message (item 1 of argv) as critical buttons {\"好\"} default button 1",
            "-e", "end run",
            message,
            (char *)NULL
        );
        _exit(1);
    } else if (pid > 0) {
        int status = 0;
        waitpid(pid, &status, 0);
    }
    fprintf(stderr, "光筑: %s\n", message);
}

int main(int argc, char **argv) {
    char raw_exec[PATH_MAX];
    uint32_t buf_size = sizeof(raw_exec);
    if (_NSGetExecutablePath(raw_exec, &buf_size) != 0) {
        show_native_alert("无法定位光筑应用程序路径，请重新安装。");
        return 1;
    }

    char resolved_exec[PATH_MAX];
    if (realpath(raw_exec, resolved_exec) == NULL) {
        strncpy(resolved_exec, raw_exec, sizeof(resolved_exec) - 1);
        resolved_exec[sizeof(resolved_exec) - 1] = '\0';
    }

    char macos_dir[PATH_MAX];
    strncpy(macos_dir, resolved_exec, sizeof(macos_dir) - 1);
    macos_dir[sizeof(macos_dir) - 1] = '\0';
    char *dir1 = dirname(macos_dir);

    char contents_dir[PATH_MAX];
    strncpy(contents_dir, dir1, sizeof(contents_dir) - 1);
    contents_dir[sizeof(contents_dir) - 1] = '\0';
    char *contents = dirname(contents_dir);

    char resources_dir[PATH_MAX];
    char runtime_dir[PATH_MAX];
    char python_home[PATH_MAX];
    char dylib_path[PATH_MAX];
    char bootstrap_py[PATH_MAX];
    char fallback_pythonpath[PATH_MAX * 2];

    snprintf(resources_dir, sizeof(resources_dir), "%s/Resources", contents);
    snprintf(runtime_dir, sizeof(runtime_dir), "%s/runtime", resources_dir);
    snprintf(python_home, sizeof(python_home), "%s/python", runtime_dir);
    snprintf(dylib_path, sizeof(dylib_path), "%s/lib/libpython3.12.dylib", python_home);
    snprintf(bootstrap_py, sizeof(bootstrap_py), "%s/bootstrap_macos.py", resources_dir);

    setenv("PYTHONHOME", python_home, 1);
    setenv("PYTHONUTF8", "1", 1);
    setenv("PYTHONDONTWRITEBYTECODE", "1", 1);
    setenv("GUANGZHU_RUNTIME_ROOT", runtime_dir, 0);

    const char *home = getenv("HOME");
    if (home != NULL && getenv("PYTHONPATH") == NULL) {
        snprintf(
            fallback_pythonpath,
            sizeof(fallback_pythonpath),
            "%s/Library/Application Support/Guangzhu/workspace/backend:%s/payload/backend",
            home,
            resources_dir
        );
        setenv("PYTHONPATH", fallback_pythonpath, 1);
    }

    void *libpython = dlopen(dylib_path, RTLD_LAZY | RTLD_GLOBAL);
    if (libpython == NULL) {
        show_native_alert("光筑安装文件不完整（无法加载内置 Python 3.12 运行库），请重新将光筑拖入“应用程序”文件夹。");
        return 1;
    }

    py_bytes_main_fn py_bytes_main = (py_bytes_main_fn)dlsym(libpython, "Py_BytesMain");
    if (py_bytes_main == NULL) {
        show_native_alert("光筑内置运行时符号异常，请重新安装光筑 Mac 版。");
        return 1;
    }

    int is_finder_launch = (argc == 1) || (argc == 2 && strncmp(argv[1], "-psn_", 5) == 0);
    if (is_finder_launch) {
        char *py_argv[4];
        py_argv[0] = argv[0];
        py_argv[1] = (char *)"-B";
        py_argv[2] = bootstrap_py;
        py_argv[3] = NULL;
        return py_bytes_main(3, py_argv);
    }

    return py_bytes_main(argc, argv);
}
