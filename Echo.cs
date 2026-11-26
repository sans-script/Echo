// Echo: native Windows host (WinForms + WebView2) for the Codex and Antigravity agent teams.
// The UI lives in ui/ (Geist tokens). Data comes from one hidden Linux process (snapshot.py --watch) that prints a JSON line per tick;
// each line is forwarded to the page with PostWebMessageAsJson.
// Build: see build.ps1 (csc, C# 5, .NET Framework 4.8, x64, references the WebView2 DLLs in lib/).
using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Runtime.InteropServices;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

class Echo : Form
{
    // How to run Echo's scripts (any platform: "python", "py -3", "wsl.exe -- python3", ...) and where they are.
    // Set from Settings, saved per user.
    const string AppName = "Echo";
    static readonly string ConfigFile = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), AppName, "config.json");
    const string DefaultFolder = "~/agent-teams/monitor";
    static readonly string Home = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
    string python = DefaultPython(), folder = DefaultFolder;
    double zoom = 1;  // page zoom, like VS Code's window.zoomLevel: Ctrl+= / Ctrl+- / Ctrl+0 or Ctrl+wheel
    static readonly System.Text.RegularExpressions.Regex DistroRx = new System.Text.RegularExpressions.Regex("^[A-Za-z0-9._-]{1,64}$");
    // No quotes or shell characters: the command is split on spaces and started directly.
    static readonly System.Text.RegularExpressions.Regex PythonRx = new System.Text.RegularExpressions.Regex("^[A-Za-z0-9._:~\\\\/=-]+( [A-Za-z0-9._:~\\\\/=-]+){0,12}$");
    static readonly System.Text.RegularExpressions.Regex FolderRx = new System.Text.RegularExpressions.Regex("^(~|~[/\\\\][A-Za-z0-9._ /\\\\-]{0,200}|/[A-Za-z0-9._ /-]{1,200}|[A-Za-z]:[/\\\\][A-Za-z0-9._ /\\\\-]{0,200})$");
    static bool ValidFolder(string f) { return f != null && FolderRx.IsMatch(f) && !f.Contains(".."); }
    static bool ValidPython(string p) { return p != null && p.Length <= 200 && PythonRx.IsMatch(p); }

    static string DefaultPython()
    {
        // Agents running under WSL are the common setup; otherwise the local Python.
        return File.Exists(Path.Combine(Environment.SystemDirectory, "wsl.exe")) ? "wsl.exe --cd ~ -- python3" : "python";
    }
    const int IntervalSec = 3;

    readonly WebView2 web = new WebView2();
    readonly Timer restartTimer = new Timer { Interval = 5000 };
    readonly Timer procTimer = new Timer { Interval = 3000 };
    double lastCpuMs; DateTime lastCpuAt;
    readonly JavaScriptSerializer json = new JavaScriptSerializer();
    Process collector;
    string lastSnapshot;
    bool ready, closing;

    [DllImport("user32.dll")] static extern bool SetProcessDpiAwarenessContext(IntPtr value);
    [DllImport("dwmapi.dll")] static extern int DwmSetWindowAttribute(IntPtr hwnd, int attr, ref int value, int size);

    [STAThread]
    static void Main()
    {
        try { SetProcessDpiAwarenessContext(new IntPtr(-4)); } catch { }  // per-monitor v2
        // Built without a target-framework attribute, .NET 4.8 keeps its old TLS defaults, which HTTPS APIs refuse:
        // allow TLS 1.2 and 1.3 (12288) explicitly.
        System.Net.ServicePointManager.SecurityProtocol = System.Net.SecurityProtocolType.Tls12 | (System.Net.SecurityProtocolType)12288;
        Application.EnableVisualStyles();
        Application.Run(new Echo());
    }

    Echo()
    {
        Text = "Echo";
        ClientSize = new Size(1320, 860);
        MinimumSize = new Size(640, 480);
        StartPosition = FormStartPosition.CenterScreen;
        BackColor = Color.Black;
        try { Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath); } catch { }

        web.Dock = DockStyle.Fill;
        web.DefaultBackgroundColor = Color.Black;
        Controls.Add(web);

        LoadConfig();
        restartTimer.Tick += delegate { restartTimer.Stop(); StartCollector(); };
        HandleCreated += delegate { SetDarkTitle(true); };
        Load += async delegate
        {
            try
            {
                string data = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), AppName, "WebView2");
                var env = await CoreWebView2Environment.CreateAsync(null, data);
                await web.EnsureCoreWebView2Async(env);
            }
            catch (Exception ex)
            {
                MessageBox.Show(this, "Could not start WebView2:\n" + ex.Message, "Echo", MessageBoxButtons.OK, MessageBoxIcon.Error);
                Close();
                return;
            }
            var core = web.CoreWebView2;
            web.ZoomFactor = zoom;
            web.ZoomFactorChanged += delegate
            {
                if (Math.Abs(web.ZoomFactor - zoom) < 0.001) return;
                zoom = web.ZoomFactor;
                try { SaveConfig(); } catch (Exception ex) { Log("zoom not saved: " + ex.Message); }
            };
            var s = core.Settings;
            s.AreDefaultContextMenusEnabled = false;
            s.AreDevToolsEnabled = false;
            s.IsZoomControlEnabled = true;  // Ctrl+wheel, Ctrl+= / Ctrl+- / Ctrl+0; the level is kept in config.json
            s.IsStatusBarEnabled = false;
            s.AreBrowserAcceleratorKeysEnabled = false;
            string ui = Path.Combine(Path.GetDirectoryName(Application.ExecutablePath), "ui");
            core.SetVirtualHostNameToFolderMapping("echo.local", ui, CoreWebView2HostResourceAccessKind.Deny);
            // File and folder icons straight from the user's VS Code icon theme (Material Icon Theme), if installed.
            iconDir = FindIconTheme();
            if (iconDir != null) core.SetVirtualHostNameToFolderMapping("fileicons.local", iconDir, CoreWebView2HostResourceAccessKind.Allow);
            // Voice input: the microphone, for Echo's own page only.
            core.PermissionRequested += (o, e) =>
            {
                if (e.PermissionKind == CoreWebView2PermissionKind.Microphone && e.Uri.StartsWith("https://echo.local/"))
                    e.State = CoreWebView2PermissionState.Allow;
            };
            core.NewWindowRequested += (o, e) => e.Handled = true;
            core.WebMessageReceived += OnWebMessage;
            core.Navigate("https://echo.local/index.html");
            StartCollector();
            procTimer.Tick += delegate { if (ready) PostWinProcs(); };
            procTimer.Start();
        };
        FormClosing += delegate { closing = true; StopCollector(); };
    }

    void SaveConfig()
    {
        Directory.CreateDirectory(Path.GetDirectoryName(ConfigFile));
        File.WriteAllText(ConfigFile, json.Serialize(new { python = python, folder = folder,
            zoom = zoom.ToString(System.Globalization.CultureInfo.InvariantCulture) }));
    }

    void LoadConfig()
    {
        try
        {
            var c = json.Deserialize<System.Collections.Generic.Dictionary<string, string>>(File.ReadAllText(ConfigFile));
            string py, d, f;
            if (c.TryGetValue("python", out py) && ValidPython(py)) python = py;
            else if (c.TryGetValue("distro", out d) && d != null)  // older config: a WSL distribution name
                python = "wsl.exe " + (DistroRx.IsMatch(d) ? "-d " + d + " " : "") + "--cd ~ -- python3";
            if (c.TryGetValue("folder", out f) && ValidFolder(f)) folder = f;
            string z; double zv;
            if (c.TryGetValue("zoom", out z) && double.TryParse(z, System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out zv))
                zoom = Math.Max(0.25, Math.Min(5, zv));
        }
        catch { }  // no file yet, or unreadable: defaults
    }

    void PostConfig(string error)
    {
        Post(json.Serialize(new { type = "config", python = python, folder = folder, error = error }));
    }

    // Process start info for one of our scripts. Runs from the user's home, so "~/..." folders become relative paths
    // there (WSL's --cd ~ does the same on its side).
    ProcessStartInfo Script(string script, string args)
    {
        string dir = folder == "~" ? "." : folder.StartsWith("~") ? folder.Substring(2) : folder;
        int sp = python.IndexOf(' ');
        string exe = sp < 0 ? python : python.Substring(0, sp), pre = sp < 0 ? "" : python.Substring(sp + 1) + " ";
        var target = script == null ? "- \"" + dir.TrimEnd('/', '\\') + "\"" : "\"" + dir.TrimEnd('/', '\\') + "/" + script + "\"";
        var psi = new ProcessStartInfo(exe, pre + "-u " + target + " " + args)
        {
            WorkingDirectory = Home, UseShellExecute = false, CreateNoWindow = true,
            RedirectStandardOutput = true, RedirectStandardError = true,
        };
        psi.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";  // the message arrives on stdin as UTF-8 (may already be set)
        return psi;
    }

    void SetDarkTitle(bool dark)
    {
        int v = dark ? 1 : 0;
        try { DwmSetWindowAttribute(Handle, 20, ref v, 4); } catch { }
    }

    void OnWebMessage(object sender, CoreWebView2WebMessageReceivedEventArgs e)
    {
        System.Collections.Generic.Dictionary<string, object> m;
        try { m = json.Deserialize<System.Collections.Generic.Dictionary<string, object>>(e.WebMessageAsJson); }
        catch { return; }
        object cmd; m.TryGetValue("cmd", out cmd);
        switch (cmd as string)
        {
            case "ready":
                ready = true;
                if (lastSnapshot != null) web.CoreWebView2.PostWebMessageAsJson(lastSnapshot);
                PostConfig(null);
                PostIcons();
                // With a saved key, load the voices and character count now (a failed load earlier must not stick);
                // ElevenVoices posts the key state itself, and without a key it just reports that.
                ElevenVoices();
                break;
            case "zoom":  // VS Code's steps: ±10% per press, 50%–300%, 0 resets
                object st; m.TryGetValue("step", out st);
                int step = st is int ? (int)st : 0;
                zoom = step == 0 ? 1 : Math.Max(0.5, Math.Min(3, Math.Round(web.ZoomFactor + 0.1 * step, 2)));
                web.ZoomFactor = zoom;
                try { SaveConfig(); } catch (Exception ex) { Log("zoom not saved: " + ex.Message); }
                break;
            case "eleven-key":
                object ek; m.TryGetValue("key", out ek);
                SaveElevenKey(((ek as string) ?? "").Trim());
                break;
            case "eleven-voices":
                ElevenVoices();
                break;
            case "speak":
                object sid, stx, svo, smo; m.TryGetValue("id", out sid); m.TryGetValue("text", out stx); m.TryGetValue("voice", out svo); m.TryGetValue("model", out smo);
                Speak(sid as string, stx as string, svo as string, smo as string);
                break;
            case "eleven-usage":
                ElevenVoices();
                break;
            case "transcribe":
                object tid, tau; m.TryGetValue("id", out tid); m.TryGetValue("audio", out tau);
                Transcribe(tid as string, tau as string);
                break;
            case "config":
                object cp, cf; m.TryGetValue("python", out cp); m.TryGetValue("folder", out cf);
                var np = System.Text.RegularExpressions.Regex.Replace(((cp as string) ?? "").Trim(), " +", " ");
                var nf = ((cf as string) ?? "").Trim().TrimEnd('/', '\\');
                if (np.Length == 0) np = DefaultPython();
                if (nf.Length == 0) nf = DefaultFolder;
                if (!ValidPython(np)) { PostConfig("Use a plain command with arguments, without quotes or shell characters."); break; }
                if (!ValidFolder(nf)) { PostConfig("Use an absolute path or one starting with ~/, without \"..\"."); break; }
                python = np; folder = nf;
                try
                {
                    SaveConfig();
                }
                catch (Exception ex) { PostConfig("Could not save: " + ex.Message); break; }
                lastSnapshot = null;
                StartCollector();
                PostConfig(null);
                break;
            case "url":
                // Links in agent replies: only plain web links, handed to the default browser.
                object uo; m.TryGetValue("url", out uo);
                Uri uri;
                if (Uri.TryCreate(uo as string, UriKind.Absolute, out uri) && (uri.Scheme == Uri.UriSchemeHttps || uri.Scheme == Uri.UriSchemeHttp))
                    Process.Start(new ProcessStartInfo(uri.AbsoluteUri) { UseShellExecute = true });
                break;
            case "theme":
                object dark; m.TryGetValue("dark", out dark);
                SetDarkTitle(dark is bool && (bool)dark);
                break;
            case "open":
                object p, pd; m.TryGetValue("path", out p); m.TryGetValue("distro", out pd);
                var path = p as string;
                if (!ValidFolder(path) || path.StartsWith("~")) return;
                if (!path.StartsWith("/")) { Process.Start("explorer.exe", "\"" + path.Replace('/', '\\') + "\""); break; }  // a Windows folder
                // A Linux path: the page reports the WSL distribution the collector runs in.
                var dn = pd as string;
                if (dn == null || !DistroRx.IsMatch(dn)) return;
                Process.Start("explorer.exe", "\"\\\\wsl.localhost\\" + dn + path.Replace('/', '\\') + "\"");
                break;
            case "send":
                object n, t; m.TryGetValue("name", out n); m.TryGetValue("text", out t);
                var name = n as string; var text = t as string;
                // Name goes on the command line, so only plain agent names; the message travels on stdin.
                if (name == null || !System.Text.RegularExpressions.Regex.IsMatch(name, "^[A-Za-z]{1,32}$")) return;
                if (string.IsNullOrWhiteSpace(text) || text.Length > 20000 || sending.ContainsKey(name)) return;
                object mo, ef, se, ac;
                m.TryGetValue("model", out mo); m.TryGetValue("effort", out ef);
                m.TryGetValue("session", out se); m.TryGetValue("access", out ac);
                object wd, rm, ti; m.TryGetValue("cwd", out wd); m.TryGetValue("room", out rm); m.TryGetValue("title", out ti);
                SendToAgent(name, text, Opt(mo as string) + " " + Opt(ef as string) + " " + Opt(se as string) + " " + Opt(ac as string) + " " + Hex(wd as string) + (rm is bool && (bool)rm ? " room" : " -") + " " + Hex(ti as string));
                break;
            case "stop":
                object sn; m.TryGetValue("name", out sn);
                StopSend(sn as string);
                break;
            case "pickdir":
                // Native folder dialog; the answer is the folder as the scripts see it (a Linux path when they run in WSL).
                object pn, ps, pdi; m.TryGetValue("name", out pn); m.TryGetValue("start", out ps); m.TryGetValue("distro", out pdi);
                var who = pn as string; var distro = pdi as string;
                if (who == null || !System.Text.RegularExpressions.Regex.IsMatch(who, "^[A-Za-z]{1,32}$")) return;
                if (distro != null && !DistroRx.IsMatch(distro)) distro = null;
                var picked = FolderDialog.Pick(Handle, "Choose the folder " + who + " works in", ToWindows(ps as string, distro));
                if (picked != null) Post(json.Serialize(new { type = "dir", name = who, path = FromWindows(picked) }));
                break;
            case "convs":
                // The conversations screen: convs.py list | open <Name|room> <id> | delete <Name|room> <id>.
                object ca, cn, ci; m.TryGetValue("action", out ca); m.TryGetValue("name", out cn); m.TryGetValue("id", out ci);
                var act = ca as string; var cname = cn as string; var cid = ci as string;
                if (act == "list") Convs(act, "list");
                else if ((act == "open" || act == "delete") && cname != null && cid != null
                         && System.Text.RegularExpressions.Regex.IsMatch(cname, "^[A-Za-z]{1,32}$")
                         && System.Text.RegularExpressions.Regex.IsMatch(cid, "^[A-Za-z0-9._:-]{1,64}$"))
                    Convs(act, act + " " + cname + " " + cid, cname, cid);
                break;
        }
    }

    string iconDir;

    // Ends a running send: send.py --stop kills its process group on the Linux side; the Windows-side
    // process tree goes too, for a native Python where there are no process groups.
    void StopSend(string name)
    {
        Process p;
        if (name == null || !sending.TryGetValue(name, out p)) return;
        Log("stop " + name);
        try { var k = Process.Start(Script("send.py", "--stop " + name)); k.WaitForExit(5000); } catch { }
        var timer = new Timer { Interval = 2000 };
        timer.Tick += delegate
        {
            timer.Dispose();
            try { if (!p.HasExited) Process.Start(new ProcessStartInfo("taskkill.exe", "/T /F /PID " + p.Id) { CreateNoWindow = true, UseShellExecute = false }); } catch { }
        };
        timer.Start();
    }

    // A small program fed to Python on stdin: writes the bundled scripts into the scripts folder when they
    // changed (never agents.json or chat logs), then runs snapshot.py from there. Null if nothing is bundled.
    string Bootstrap()
    {
        var dir = Path.Combine(Path.GetDirectoryName(Application.ExecutablePath), "scripts");
        if (!File.Exists(Path.Combine(dir, "snapshot.py"))) return null;
        var files = new System.Text.StringBuilder();
        foreach (var f in new[] { "snapshot.py", "send.py", "convs.py" })
            files.Append("\"" + f + "\": \"" + Convert.ToBase64String(File.ReadAllBytes(Path.Combine(dir, f))) + "\", ");
        return "import base64, os, sys, runpy\n" +
               "d = os.path.abspath(os.path.expanduser(sys.argv[1]))\n" +
               "os.makedirs(d, exist_ok=True)\n" +
               "for n, b in {" + files + "}.items():\n" +
               "    p, data = os.path.join(d, n), base64.b64decode(b)\n" +
               "    try:\n        old = open(p, 'rb').read()\n    except OSError:\n        old = None\n" +
               "    if old != data:\n        open(p + '.tmp', 'wb').write(data); os.replace(p + '.tmp', p)\n" +
               "        print('deployed ' + n, file=sys.stderr, flush=True)\n" +
               "sys.argv = [os.path.join(d, 'snapshot.py')] + sys.argv[2:]\n" +
               "sys.path.insert(0, d)\n" +
               "runpy.run_path(sys.argv[0], run_name='__main__')\n";
    }

    // %LOCALAPPDATA%\Echo\echo.log, kept under about 1 MB (one older file is kept as echo.log.old).
    static readonly string LogFile = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), AppName, "echo.log");
    static readonly object logLock = new object();
    static void Log(string line)
    {
        lock (logLock)
        {
            try
            {
                Directory.CreateDirectory(Path.GetDirectoryName(LogFile));
                if (File.Exists(LogFile) && new FileInfo(LogFile).Length > 1024 * 1024)
                {
                    if (File.Exists(LogFile + ".old")) File.Delete(LogFile + ".old");
                    File.Move(LogFile, LogFile + ".old");
                }
                File.AppendAllText(LogFile, DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + "  " + line + Environment.NewLine);
            }
            catch { }
        }
    }

    // Claude Code runs on Windows, where the WSL collector cannot see processes: measure claude.exe here.
    // The Claude desktop app also ships a claude.exe (under WindowsApps); that one is not the agent.
    void PostWinProcs()
    {
        double cpuMs = 0; long mem = 0; var pids = new System.Collections.Generic.List<int>();
        foreach (var p in Process.GetProcessesByName("claude"))
        {
            try
            {
                if (p.MainModule.FileName.IndexOf(@"\WindowsApps\", StringComparison.OrdinalIgnoreCase) >= 0) continue;
                cpuMs += p.TotalProcessorTime.TotalMilliseconds; mem += p.WorkingSet64; pids.Add(p.Id);
            }
            catch { }
            finally { p.Dispose(); }
        }
        var now = DateTime.UtcNow; double cpu = 0;
        if (lastCpuAt != default(DateTime) && cpuMs >= lastCpuMs) cpu = 100.0 * (cpuMs - lastCpuMs) / (now - lastCpuAt).TotalMilliseconds;
        lastCpuMs = cpuMs; lastCpuAt = now;
        Post(json.Serialize(new { type = "winproc", team = "Claude Code", pids = pids, cpu = Math.Round(cpu, 1), mem = Math.Round(mem / 1048576.0, 1) }));
    }

    static string FindIconTheme()
    {
        try
        {
            var ext = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".vscode", "extensions");
            var dirs = Directory.GetDirectories(ext, "pkief.material-icon-theme-*");
            Array.Sort(dirs, (a, b) => new Version(Ver(a)).CompareTo(new Version(Ver(b))));
            for (int i = dirs.Length - 1; i >= 0; i--)
                if (File.Exists(Path.Combine(dirs[i], "dist", "material-icons.json"))) return dirs[i];
        }
        catch { }
        return null;
    }
    static string Ver(string dir)
    {
        var v = System.Text.RegularExpressions.Regex.Match(dir, @"(\d+)\.(\d+)\.(\d+)$");
        return v.Success ? v.Value : "0.0.0";
    }

    // The theme's manifest (extension/name -> icon) goes to the page once; the SVGs load from fileicons.local.
    void PostIcons()
    {
        if (iconDir == null) return;
        try { Post("{\"type\":\"fileicons\",\"manifest\":" + File.ReadAllText(Path.Combine(iconDir, "dist", "material-icons.json")) + "}"); }
        catch { }
    }

    /* ---------------- ElevenLabs (voice) ----------------
       The API key never reaches the page: it is stored with DPAPI (this Windows user only) and used here. */
    static readonly string ElevenKeyFile = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), AppName, "elevenlabs.key");
    static readonly System.Net.Http.HttpClient http = new System.Net.Http.HttpClient { BaseAddress = new Uri("https://api.elevenlabs.io/"), Timeout = TimeSpan.FromMinutes(2) };
    static readonly System.Text.RegularExpressions.Regex IdRx = new System.Text.RegularExpressions.Regex("^[A-Za-z0-9_-]{1,64}$");

    static string ElevenKey()
    {
        try
        {
            if (!File.Exists(ElevenKeyFile)) return null;
            var raw = System.Security.Cryptography.ProtectedData.Unprotect(File.ReadAllBytes(ElevenKeyFile), null, System.Security.Cryptography.DataProtectionScope.CurrentUser);
            return System.Text.Encoding.UTF8.GetString(raw);
        }
        catch { return null; }
    }

    void SaveElevenKey(string key)
    {
        try
        {
            if (key.Length == 0) { if (File.Exists(ElevenKeyFile)) File.Delete(ElevenKeyFile); PostEleven(null); return; }
            if (key.Length > 200 || !System.Text.RegularExpressions.Regex.IsMatch(key, "^[A-Za-z0-9_-]+$")) { PostEleven("That does not look like an ElevenLabs API key."); return; }
            Directory.CreateDirectory(Path.GetDirectoryName(ElevenKeyFile));
            File.WriteAllBytes(ElevenKeyFile, System.Security.Cryptography.ProtectedData.Protect(System.Text.Encoding.UTF8.GetBytes(key), null, System.Security.Cryptography.DataProtectionScope.CurrentUser));
            ElevenVoices();  // checks the key and fills the voice list
        }
        catch (Exception ex) { PostEleven("Could not save the key: " + ex.Message); }
    }

    void PostEleven(string error, object voices = null)
    {
        Post(json.Serialize(new { type = "eleven", hasKey = ElevenKey() != null, error = error, voices = voices }));
    }

    System.Net.Http.HttpRequestMessage ElevenRequest(System.Net.Http.HttpMethod method, string path, string key)
    {
        var r = new System.Net.Http.HttpRequestMessage(method, path);
        r.Headers.Add("xi-api-key", key);
        return r;
    }

    // "An error occurred while sending the request" hides the cause; the innermost exception names it (TLS, DNS, proxy...).
    static string Unreachable(Exception ex)
    {
        var why = ex.GetBaseException().Message;
        Log("ElevenLabs: " + why);
        return "Could not reach ElevenLabs: " + why;
    }

    static string ElevenError(string body, System.Net.HttpStatusCode code)
    {
        // {"detail":{"message":...}} or {"detail":"..."}; never echo the key
        try
        {
            var d = new JavaScriptSerializer().Deserialize<System.Collections.Generic.Dictionary<string, object>>(body);
            object det; d.TryGetValue("detail", out det);
            var dd = det as System.Collections.Generic.Dictionary<string, object>;
            object msg = null; if (dd != null) dd.TryGetValue("message", out msg);
            var s = (msg ?? det) as string;
            if (!string.IsNullOrEmpty(s)) return s.Length > 300 ? s.Substring(0, 300) : s;
        }
        catch { }
        return "ElevenLabs returned " + (int)code + " " + code;
    }

    async void ElevenVoices()
    {
        var key = ElevenKey();
        if (key == null) { PostEleven(null); return; }
        try
        {
            var res = await http.SendAsync(ElevenRequest(System.Net.Http.HttpMethod.Get, "v2/voices?page_size=100&sort=name&sort_direction=asc", key));
            var body = await res.Content.ReadAsStringAsync();
            if (!res.IsSuccessStatusCode) { PostEleven(ElevenError(body, res.StatusCode)); return; }
            var d = json.Deserialize<System.Collections.Generic.Dictionary<string, object>>(body);
            var list = new System.Collections.Generic.List<object>();
            foreach (var v in (System.Collections.ArrayList)d["voices"])
            {
                var vd = (System.Collections.Generic.Dictionary<string, object>)v;
                object cat, prev; vd.TryGetValue("category", out cat); vd.TryGetValue("preview_url", out prev);
                var pv = prev as string;  // ElevenLabs' public sample clip; playing it costs no characters
                if (pv != null && !pv.StartsWith("https://", StringComparison.Ordinal)) pv = null;
                list.Add(new { id = vd["voice_id"], name = vd["name"], category = cat, preview = pv });
            }
            object usage = null;
            try
            {
                var sr = await http.SendAsync(ElevenRequest(System.Net.Http.HttpMethod.Get, "v1/user/subscription", key));
                if (sr.IsSuccessStatusCode)
                {
                    var sd = json.Deserialize<System.Collections.Generic.Dictionary<string, object>>(await sr.Content.ReadAsStringAsync());
                    object used, limit, reset; sd.TryGetValue("character_count", out used); sd.TryGetValue("character_limit", out limit); sd.TryGetValue("next_character_count_reset_unix", out reset);
                    usage = new { used = used, limit = limit, reset = reset };
                }
            }
            catch { }  // the quota line is optional
            Post(json.Serialize(new { type = "eleven", hasKey = true, error = (string)null, voices = list, usage = usage }));
        }
        catch (Exception ex) { PostEleven(Unreachable(ex)); }
    }

    // Text to speech with character timings, for the transcript highlight.
    async void Speak(string id, string text, string voice, string model)
    {
        if (id == null || !IdRx.IsMatch(id)) return;
        var key = ElevenKey();
        if (key == null) { Post(json.Serialize(new { type = "speech", id = id, error = "Add an ElevenLabs API key in Settings." })); return; }
        if (string.IsNullOrWhiteSpace(text) || voice == null || !IdRx.IsMatch(voice)) { Post(json.Serialize(new { type = "speech", id = id, error = "Choose a voice in Settings." })); return; }
        if (text.Length > 5000) text = text.Substring(0, 5000);
        if (model == null || !IdRx.IsMatch(model)) model = "eleven_multilingual_v2";
        try
        {
            var req = ElevenRequest(System.Net.Http.HttpMethod.Post, "v1/text-to-speech/" + voice + "/with-timestamps?output_format=mp3_44100_128", key);
            req.Content = new System.Net.Http.StringContent(json.Serialize(new { text = text, model_id = model }), System.Text.Encoding.UTF8, "application/json");
            var res = await http.SendAsync(req);
            var body = await res.Content.ReadAsStringAsync();
            if (!res.IsSuccessStatusCode) { Post(json.Serialize(new { type = "speech", id = id, error = ElevenError(body, res.StatusCode) })); return; }
            // Forward ElevenLabs' JSON as is (audio_base64 + alignment), tagged with the request id.
            Post("{\"type\":\"speech\",\"id\":" + json.Serialize(id) + ",\"result\":" + body + "}");
        }
        catch (Exception ex) { Post(json.Serialize(new { type = "speech", id = id, error = Unreachable(ex) })); }
    }

    // Speech to text for voice input; the page records webm/opus and sends it base64.
    async void Transcribe(string id, string audio)
    {
        if (id == null || !IdRx.IsMatch(id)) return;
        var key = ElevenKey();
        if (key == null) { Post(json.Serialize(new { type = "transcript", id = id, error = "Add an ElevenLabs API key in Settings." })); return; }
        byte[] bytes;
        try { bytes = Convert.FromBase64String(audio ?? ""); } catch { return; }
        if (bytes.Length == 0 || bytes.Length > 25 * 1024 * 1024) return;
        try
        {
            var form = new System.Net.Http.MultipartFormDataContent();
            form.Add(new System.Net.Http.StringContent("scribe_v2"), "model_id");
            var file = new System.Net.Http.ByteArrayContent(bytes);
            file.Headers.ContentType = new System.Net.Http.Headers.MediaTypeHeaderValue("audio/webm");
            form.Add(file, "file", "speech.webm");
            var req = ElevenRequest(System.Net.Http.HttpMethod.Post, "v1/speech-to-text", key);
            req.Content = form;
            var res = await http.SendAsync(req);
            var body = await res.Content.ReadAsStringAsync();
            if (!res.IsSuccessStatusCode) { Post(json.Serialize(new { type = "transcript", id = id, error = ElevenError(body, res.StatusCode) })); return; }
            var d = json.Deserialize<System.Collections.Generic.Dictionary<string, object>>(body);
            object t; d.TryGetValue("text", out t);
            Post(json.Serialize(new { type = "transcript", id = id, text = (t as string ?? "").Trim() }));
        }
        catch (Exception ex) { Post(json.Serialize(new { type = "transcript", id = id, error = Unreachable(ex) })); }
    }

    readonly System.Collections.Generic.Dictionary<string, Process> sending = new System.Collections.Generic.Dictionary<string, Process>();

    // Model / effort ids also go on the command line: plain ids only, anything else means "account default".
    static string Opt(string v)
    {
        return v != null && System.Text.RegularExpressions.Regex.IsMatch(v, "^[A-Za-z0-9._:-]{1,64}$") ? v : "default";
    }

    bool Wsl { get { return python.StartsWith("wsl", StringComparison.OrdinalIgnoreCase); } }

    // Script-side path -> a path Windows can open. Linux paths map into the distro's share, /mnt/x/ to X:\.
    string ToWindows(string p, string distro)
    {
        if (string.IsNullOrEmpty(p) || !Wsl || !p.StartsWith("/")) return p;
        var mnt = System.Text.RegularExpressions.Regex.Match(p, "^/mnt/([a-z])(/.*)?$");
        if (mnt.Success) return mnt.Groups[1].Value.ToUpper() + ":" + (mnt.Groups[2].Value.Length > 0 ? mnt.Groups[2].Value : "/").Replace('/', '\\');
        return distro == null ? null : @"\\wsl.localhost\" + distro + p.Replace('/', '\\');
    }

    // Windows path from the dialog -> the path the scripts use.
    string FromWindows(string p)
    {
        if (!Wsl) return p;
        var unc = System.Text.RegularExpressions.Regex.Match(p, @"^\\\\wsl(?:\.localhost|\$)\\[^\\]+(.*)$", System.Text.RegularExpressions.RegexOptions.IgnoreCase);
        if (unc.Success) return unc.Groups[1].Value.Length > 0 ? unc.Groups[1].Value.Replace('\\', '/') : "/";
        var drive = System.Text.RegularExpressions.Regex.Match(p, @"^([A-Za-z]):\\?(.*)$");
        if (drive.Success) return "/mnt/" + drive.Groups[1].Value.ToLower() + "/" + drive.Groups[2].Value.Replace('\\', '/');
        return p;
    }

    // Folder paths go on the command line as hex, so spaces and quotes need no escaping.
    static string Hex(string v)
    {
        if (string.IsNullOrEmpty(v) || v.Length > 1024) return "default";
        return BitConverter.ToString(System.Text.Encoding.UTF8.GetBytes(v)).Replace("-", "").ToLowerInvariant();
    }

    // Runs convs.py off the UI thread and posts its JSON back as {type:"convs", action, name, id, result}.
    void Convs(string action, string args, string name = null, string id = null)
    {
        System.Threading.Tasks.Task.Run(() =>
        {
            string result;
            try
            {
                using (var p = Process.Start(Script("convs.py", args)))
                {
                    var err = p.StandardError.ReadToEndAsync();
                    result = p.StandardOutput.ReadToEnd().Trim();
                    if (!p.WaitForExit(60000)) { try { p.Kill(); } catch { } }
                    if (!result.StartsWith("{")) { Log("convs " + action + " failed: " + err.Result); result = json.Serialize(new { ok = false, error = "Could not read the conversations." }); }
                }
            }
            catch (Exception ex) { result = json.Serialize(new { ok = false, error = "Could not start the Linux side: " + ex.Message }); }
            Post("{\"type\":\"convs\",\"action\":" + json.Serialize(action) + ",\"name\":" + json.Serialize(name) + ",\"id\":" + json.Serialize(id) + ",\"result\":" + result + "}");
        });
    }

    // opts: already-validated "model effort session access" tokens (see Opt).
    void SendToAgent(string name, string text, string opts)
    {
        var psi = Script("send.py", name + " " + opts);
        psi.RedirectStandardInput = true;
        var err = new System.Text.StringBuilder();
        var p = new Process { StartInfo = psi, EnableRaisingEvents = true };
        p.ErrorDataReceived += (o, e) => { if (e.Data != null) lock (err) err.AppendLine(e.Data); };
        p.OutputDataReceived += (o, e) => { };
        p.Exited += delegate
        {
            p.WaitForExit();  // drain the async readers
            bool ok = p.ExitCode == 0;
            string msg; lock (err) msg = err.ToString().Trim();
            if (msg.Length > 400) msg = msg.Substring(msg.Length - 400);
            p.Dispose();
            try { BeginInvoke((Action)delegate { sending.Remove(name); }); } catch (InvalidOperationException) { }
            if (!ok) Log("send " + name + " failed: " + msg);
            Post(json.Serialize(new { type = "sent", name = name, ok = ok, error = ok ? null : (msg.Length > 0 ? msg : "Send failed") }));
        };
        try
        {
            p.Start();
            sending[name] = p;
            p.BeginOutputReadLine();
            p.BeginErrorReadLine();
            var bytes = new System.Text.UTF8Encoding(false).GetBytes(text);
            p.StandardInput.BaseStream.Write(bytes, 0, bytes.Length);
            p.StandardInput.Close();
            Post(json.Serialize(new { type = "accepted", name = name }));
        }
        catch (Exception ex)
        {
            sending.Remove(name);
            Post(json.Serialize(new { type = "sent", name = name, ok = false, error = "Could not start the Linux side: " + ex.Message }));
        }
    }

    void Post(string jsonText)
    {
        if (closing || IsDisposed) return;
        try
        {
            BeginInvoke((Action)delegate
            {
                if (ready && web.CoreWebView2 != null) web.CoreWebView2.PostWebMessageAsJson(jsonText);
            });
        }
        catch (InvalidOperationException) { }
    }

    void Status(string state, string text)
    {
        Post(json.Serialize(new { type = "collector", state = state, text = text }));
    }

    void StartCollector()
    {
        StopCollector();
        var boot = Bootstrap();
        var psi = boot != null ? Script(null, "--watch " + IntervalSec) : Script("snapshot.py", "--watch " + IntervalSec);
        if (boot != null) psi.RedirectStandardInput = true;
        Log("collector start: " + psi.FileName + " " + psi.Arguments);
        try
        {
            collector = new Process { StartInfo = psi, EnableRaisingEvents = true };
            collector.OutputDataReceived += (o, e) =>
            {
                if (string.IsNullOrEmpty(e.Data) || e.Data[0] != '{') return;
                lastSnapshot = e.Data;
                Post(e.Data);
            };
            collector.ErrorDataReceived += (o, e) => { if (!string.IsNullOrEmpty(e.Data)) Log("collector: " + e.Data); };
            collector.Exited += delegate
            {
                if (closing) return;
                Log("collector exited");
                Status("down", "Collector stopped, restarting");
                try { BeginInvoke((Action)restartTimer.Start); } catch (InvalidOperationException) { }
            };
            collector.Start();
            collector.BeginOutputReadLine();
            collector.BeginErrorReadLine();
            if (boot != null)
            {
                var b = new System.Text.UTF8Encoding(false).GetBytes(boot);
                collector.StandardInput.BaseStream.Write(b, 0, b.Length);
                collector.StandardInput.Close();
            }
        }
        catch (Exception ex)
        {
            Log("collector failed to start: " + ex.Message);
            Status("down", "Could not start the collector: " + ex.Message);
            restartTimer.Start();
        }
    }

    void StopCollector()
    {
        if (collector == null) return;
        try { if (!collector.HasExited) collector.Kill(); } catch { }
        collector.Dispose();
        collector = null;
    }
}

// The Vista+ folder picker (IFileOpenDialog with FOS_PICKFOLDERS), the same one VS Code's "Open Folder" uses.
static class FolderDialog
{
    [ComImport, Guid("DC1C5A9C-E88A-4dde-A5A1-60F82A20AEF7")] class FileOpenDialogCom { }

    [ComImport, Guid("42f85136-db7e-439c-85f1-e4075d135fc8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IFileDialog
    {
        [PreserveSig] int Show(IntPtr parent);
        void SetFileTypes(uint c, IntPtr f); void SetFileTypeIndex(uint i); void GetFileTypeIndex(out uint i);
        void Advise(IntPtr e, out uint c); void Unadvise(uint c);
        void SetOptions(uint fos); void GetOptions(out uint fos);
        void SetDefaultFolder(IShellItem si); void SetFolder(IShellItem si); void GetFolder(out IShellItem si); void GetCurrentSelection(out IShellItem si);
        void SetFileName([MarshalAs(UnmanagedType.LPWStr)] string n); void GetFileName([MarshalAs(UnmanagedType.LPWStr)] out string n);
        void SetTitle([MarshalAs(UnmanagedType.LPWStr)] string t); void SetOkButtonLabel([MarshalAs(UnmanagedType.LPWStr)] string t);
        void SetFileNameLabel([MarshalAs(UnmanagedType.LPWStr)] string t); void GetResult(out IShellItem si);
    }

    [ComImport, Guid("43826D1E-E718-42EE-BC55-A1E261C37BFE"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IShellItem
    {
        void BindToHandler(IntPtr pbc, ref Guid bhid, ref Guid riid, out IntPtr ppv); void GetParent(out IShellItem si);
        void GetDisplayName(uint sigdn, [MarshalAs(UnmanagedType.LPWStr)] out string name);
    }

    [DllImport("shell32.dll", CharSet = CharSet.Unicode, PreserveSig = false)]
    static extern void SHCreateItemFromParsingName(string path, IntPtr pbc, [MarshalAs(UnmanagedType.LPStruct)] Guid riid, out IShellItem item);

    public static string Pick(IntPtr owner, string title, string start)
    {
        var d = (IFileDialog)new FileOpenDialogCom();
        try
        {
            d.SetOptions(0x20 | 0x40 | 0x800);  // FOS_PICKFOLDERS | FOS_FORCEFILESYSTEM | FOS_PATHMUSTEXIST
            d.SetTitle(title);
            d.SetOkButtonLabel("Use Folder");
            if (!string.IsNullOrEmpty(start))
                try { IShellItem si; SHCreateItemFromParsingName(start, IntPtr.Zero, typeof(IShellItem).GUID, out si); d.SetFolder(si); } catch { }
            if (d.Show(owner) != 0) return null;  // cancelled
            IShellItem r; d.GetResult(out r);
            string path; r.GetDisplayName(0x80058000, out path);  // SIGDN_FILESYSPATH
            return path;
        }
        finally { Marshal.ReleaseComObject(d); }
    }
}
