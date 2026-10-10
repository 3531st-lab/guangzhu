// 光筑.exe：先显示启动画面，再用安装目录里的内置 Python 打开光筑窗口；主窗口出现后启动画面自动关闭。
// 自己不联网，也不读写任何数据。构建时用 Windows 自带的 C# 编译器生成（scripts/build_installer.ps1）。
using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Windows.Forms;

[assembly: AssemblyTitle("光筑")]
[assembly: AssemblyProduct("光筑")]
[assembly: AssemblyDescription("光筑：工厂屋顶光伏方案设计")]
[assembly: AssemblyCompany("验形工坊")]
[assembly: AssemblyVersion("0.2.0.0")]
[assembly: AssemblyFileVersion("0.2.0.0")]

static class Launcher
{
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern IntPtr FindWindow(string className, string title);
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr window, out uint processId);
    [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr window);

    static Form Splash()
    {
        var form = new Form { Text = "光筑启动中", FormBorderStyle = FormBorderStyle.None, StartPosition = FormStartPosition.CenterScreen,
            Size = new Size(380, 210), BackColor = Color.FromArgb(27, 23, 20), Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath) };
        var logo = new PictureBox { Image = form.Icon.ToBitmap(), SizeMode = PictureBoxSizeMode.Zoom, Bounds = new Rectangle(40, 58, 72, 72) };
        var name = new Label { Text = "光筑", ForeColor = Color.FromArgb(224, 138, 79), Font = new Font("Microsoft YaHei UI", 26, FontStyle.Bold),
            AutoSize = true, Location = new Point(128, 52) };
        var hint = new Label { Text = "正在启动……", ForeColor = Color.FromArgb(185, 171, 157), Font = new Font("Microsoft YaHei UI", 11),
            AutoSize = true, Location = new Point(134, 108) };
        form.Controls.AddRange(new Control[] { logo, name, hint });
        return form;
    }

    [STAThread]
    static int Main()
    {
        string root = AppDomain.CurrentDomain.BaseDirectory;
        string python = Path.Combine(root, @"runtime\python\pythonw.exe");
        string app = Path.Combine(root, @"desktop\app.py");
        if (!File.Exists(python) || !File.Exists(app))
        {
            MessageBox.Show("光筑的安装文件不完整，请重新安装光筑。", "光筑", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
        var info = new ProcessStartInfo(python, "\"" + app + "\"") { WorkingDirectory = root, UseShellExecute = false };
        using (var child = Process.Start(info))
        {
            Application.EnableVisualStyles();
            using (var splash = Splash())
            {
                var started = DateTime.Now;
                var timer = new Timer { Interval = 200 };
                timer.Tick += (sender, args) =>
                {
                    IntPtr window = FindWindow(null, "光筑");
                    uint owner = 0;
                    if (window != IntPtr.Zero) GetWindowThreadProcessId(window, out owner);
                    bool shown = window != IntPtr.Zero && owner == (uint)child.Id && IsWindowVisible(window);
                    if (shown || child.HasExited || (DateTime.Now - started).TotalSeconds > 90)
                    {
                        timer.Stop();
                        splash.Close();
                    }
                };
                timer.Start();
                Application.Run(splash);
            }
            child.WaitForExit();
            return child.ExitCode;
        }
    }
}
