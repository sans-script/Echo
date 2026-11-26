#!/usr/bin/env python3
"""Read-only status of every agent. Prints one JSON line per tick.

usage: snapshot.py [--watch SECONDS]

Never writes to any agent home; SQLite is opened with mode=ro.
Antigravity quota comes from `agy -p /usage --output-format json` (no model call, 0 tokens),
polled in the background every AGY_QUOTA_EVERY seconds per instance.
"""
import base64, glob, json, os, re, shutil, sqlite3, subprocess, sys, threading, time
from datetime import datetime, timezone

H = os.path.expanduser("~")
C, G = H + "/.codex", H + "/.gemini"
AGY_BIN = shutil.which("agy") or H + "/.local/bin/agy"
HERE = os.path.dirname(os.path.abspath(__file__))


def load_config():
    """agents.json next to this script (optional): {"agents": [{"team", "name", "role", "home"}], "agyQuotaEvery": 300}."""
    try:
        with open(os.path.join(HERE, "agents.json")) as f:
            cfg = json.load(f)
        return cfg if isinstance(cfg, dict) else {}
    except (OSError, ValueError):
        return {}


CONFIG = load_config()
AGY_QUOTA_EVERY = max(60, int(CONFIG.get("agyQuotaEvery") or 300))
DEFAULT_AGENTS = [
    ("Codex", "Aaron", "Lead", C),
    ("Codex", "Breeze", "Research", C + "/.codex"),
    ("Codex", "Clove", "Implementation", C + "/.codex/.codex"),
    ("Codex", "Dipper", "Review", C + "/.codex/.codex/.codex"),
    ("Antigravity", "Atlas", "Lead", G),
    ("Antigravity", "Breach", "Research", G + "/.gemini"),
    ("Antigravity", "Cypher", "Implementation", G + "/.gemini/.gemini"),
    ("Antigravity", "Draco", "Review", G + "/.gemini/.gemini/.gemini"),
    ("Antigravity", "Ember", "To be decided", G + "/.gemini/.gemini/.gemini/.gemini"),
]
TEAMS = ("Codex", "Antigravity", "Claude Code")
AGENTS = [(a.get("team"), a.get("name"), a.get("role", ""), os.path.expanduser(a.get("home", "")))
          for a in CONFIG.get("agents") or [] if isinstance(a, dict) and a.get("team") in TEAMS
          and re.fullmatch(r"[A-Za-z]{1,32}", str(a.get("name", ""))) and a.get("home")]
if not AGENTS:  # no config: the default team, keeping only the homes that exist on this machine
    AGENTS = [a for a in DEFAULT_AGENTS if os.path.isdir(a[3])]
TICKS = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100
PAGE = os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else 4096
_cpu_prev = {}  # pid -> (ticks, wall time)


def iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat() if ts else None


TALK = ("UserMessage", "AgentMessage", "Compacted")


def recent_events(events, talk=30, cap=250):
    """The last `talk` messages and every tool call between them: a count of all events lets a busy turn push the chat out."""
    idx = [i for i, e in enumerate(events) if e["kind"] in TALK]
    start = idx[-talk] if len(idx) >= talk else 0
    return events[start:][-cap:]


def short(s, n=300):
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[: n - 1] + "…"


def jwt_email(token):
    try:
        p = token.split(".")[1]
        p += "=" * (-len(p) % 4)
        return json.loads(base64.urlsafe_b64decode(p)).get("email")
    except Exception:
        return None


# ---------------------------------------------------------------- processes

def processes():
    """Map agent home -> [pid], from /proc (same user, read-only)."""
    out = {}
    if not os.path.isdir("/proc"):
        return out
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            args = [a.decode(errors="replace") for a in open(f"/proc/{pid}/cmdline", "rb").read().split(b"\0") if a]
            if not args:
                continue
            exe = os.path.basename(args[0])
            home = None
            if exe == "agy":
                if any(a in ("-p", "--print", "--prompt") and i + 1 < len(args) and args[i + 1].startswith("/") for i, a in enumerate(args)):
                    continue  # our own /usage probes are not agent activity
                gd = [a.split("=", 1)[1] for a in args if a.startswith("--gemini_dir=")]
                home = os.path.realpath(gd[0]) if gd else G
            elif exe == "codex" or (exe == "node" and len(args) > 1 and args[1].endswith("/codex")):
                env = open(f"/proc/{pid}/environ", "rb").read().split(b"\0")
                ch = [e.split(b"=", 1)[1].decode() for e in env if e.startswith(b"CODEX_HOME=")]
                home = os.path.realpath(ch[0]) if ch else C
        except OSError:
            continue
        if home:
            out.setdefault(home, []).append(int(pid))
    return out


def proc_stats(pids):
    """CPU % (since previous tick) and resident memory in MB, summed over pids."""
    cpu, rss, now = 0.0, 0, time.time()
    for pid in pids:
        try:
            f = open(f"/proc/{pid}/stat").read().rsplit(")", 1)[1].split()
            ticks = int(f[11]) + int(f[12])
            rss += int(open(f"/proc/{pid}/statm").read().split()[1]) * PAGE
        except (OSError, IndexError, ValueError):
            continue
        prev = _cpu_prev.get(pid)
        if prev and now > prev[1]:
            cpu += 100.0 * (ticks - prev[0]) / TICKS / (now - prev[1])
        _cpu_prev[pid] = (ticks, now)
    return round(cpu, 1), round(rss / 1048576, 1)


# ---------------------------------------------------------------- codex

def text_of(item):
    if isinstance(item.get("changes"), dict):
        return " ".join(item["changes"])
    for k in ("text", "message", "command", "last_agent_message", "output"):
        v = item.get(k)
        if isinstance(v, str) and v.strip():
            return v
        if isinstance(v, list):
            return " ".join(x if isinstance(x, str) else " ".join(x) if isinstance(x, list) else "" for x in v)
    c = item.get("content")
    if isinstance(c, list):
        return " ".join(x.get("text", "") for x in c if isinstance(x, dict))
    return ""


def window_label(minutes):
    if not minutes:
        return "Limit"
    if minutes <= 360:
        return f"{round(minutes / 60)}h"
    if minutes <= 10080:
        return "Weekly"
    return f"{round(minutes / 1440)}-day"


def tail_lines(path, limit=400_000):
    size = os.path.getsize(path)
    with open(path, "rb") as fh:
        fh.seek(max(0, size - limit))
        lines = fh.read().decode(errors="replace").splitlines()
    return lines[1:] if size > limit else lines


def codex_rollout(path, limit=400_000):
    """One Codex session file: its id, folder, turn state, model, tokens and events (read-only)."""
    events, info = [], {"cwd": "", "sid": "", "turn": "idle", "model": None, "tokens": None, "context": None}
    for line in tail_lines(path, limit):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        p, t, ts = d.get("payload") or {}, d.get("type"), d.get("timestamp", "")
        if t == "session_meta":
            info["cwd"], info["sid"] = p.get("cwd", ""), p.get("id", "")
        elif t == "turn_context":
            info["cwd"] = p.get("cwd", info["cwd"])
            info["model"] = p.get("model") or info["model"]
        elif t == "event_msg":
            pt = p.get("type")
            if pt == "task_started":
                info["turn"] = "working"
            elif pt == "task_complete":
                info["turn"] = "idle"
            elif pt == "token_count" and p.get("info"):
                tot, last = p["info"].get("total_token_usage") or {}, p["info"].get("last_token_usage") or {}
                win = p["info"].get("model_context_window")
                info["tokens"] = {"input": tot.get("input_tokens"), "cached": tot.get("cached_input_tokens"),
                                  "output": tot.get("output_tokens"), "total": tot.get("total_tokens")}
                if win and last.get("total_tokens"):
                    info["context"] = round(100.0 * last["total_tokens"] / win, 1)
            elif pt == "item_completed":
                it = p.get("item") or {}
                kind, txt = it.get("type", "?"), text_of(it)
                if kind != "Reasoning":
                    ev = {"t": ts, "kind": kind, "text": str(txt)[:20000] if kind in ("UserMessage", "AgentMessage") else short(txt, 600)}
                    if kind == "CommandExecution" and it.get("aggregated_output"):
                        ev["out"] = it["aggregated_output"][-4000:]
                    events.append(ev)
        elif t == "response_item" and p.get("type") in ("function_call", "custom_tool_call") and p.get("name") != "exec":  # exec shows up again as CommandExecution/FileChange
            events.append({"t": ts, "kind": "Tool", "text": f"{p.get('name')}: " + short(p.get("arguments") or p.get("input") or "", 400)})

    return info, events


def codex(home):
    rollouts = []
    for d, _, files in os.walk(home + "/sessions"):
        rollouts += [os.path.join(d, f) for f in files if f.endswith(".jsonl")]
    rollouts.sort(key=os.path.getmtime, reverse=True)
    acct = {}
    try:
        a = json.load(open(home + "/auth.json"))
        acct = {"email": jwt_email((a.get("tokens") or {}).get("id_token", "")), "auth": a.get("auth_mode")}
    except (OSError, ValueError):
        pass
    if not rollouts:
        return {"title": None, "events": [], "usage": [], "account": acct, "sessions": 0}

    newest = rollouts[0]
    info, events = codex_rollout(newest)

    # Rate limits: newest token_count that carries them, searching back across sessions.
    usage, plan = [], None
    for path in rollouts[:20]:  # ponytail: last 20 sessions is plenty; limits update on every turn
        rl = None
        for line in reversed(tail_lines(path)):
            if '"rate_limits"' in line:
                try:
                    d = json.loads(line)
                    rl, seen = (d.get("payload") or {}).get("rate_limits") or d.get("rate_limits"), d.get("timestamp")
                except ValueError:
                    rl = None
                # Only the core "codex" limit; other ids (premium, spark) must not stand in for it.
                if rl and rl.get("limit_id") in (None, "codex") and (rl.get("primary") or rl.get("secondary")):
                    break
                rl = None
        if rl:
            plan = rl.get("plan_type")
            for key in ("primary", "secondary"):
                w = rl.get(key)
                if w and w.get("used_percent") is not None:
                    usage.append({"label": window_label(w.get("window_minutes")), "used": w["used_percent"],
                                  "resets_at": iso(w.get("resets_at")), "seen_at": seen, "source": "last turn"})
            break

    return {"title": info["sid"] or os.path.basename(newest), "sid": info["sid"], "cwd": info["cwd"], "turn": info["turn"],
            "model": info["model"], "tokens": info["tokens"], "context": info["context"], "plan": plan,
            "last": iso(os.path.getmtime(newest)), "events": recent_events(events), "usage": usage,
            "account": acct, "sessions": len(rollouts)}


# ---------------------------------------------------------------- claude code

def windows_home():
    """The Windows profile folder when running under WSL (Claude Code installed on Windows), else None."""
    if not os.environ.get("WSL_DISTRO_NAME"):
        return None
    try:
        win = subprocess.run(["cmd.exe", "/c", "echo %USERPROFILE%"], cwd="/mnt/c", stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=15).stdout.strip()
        return subprocess.run(["wslpath", "-u", win], stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=5).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def claude_code(home):
    """Newest Claude Code session in <home>/projects (read-only): messages, tool calls, model and tokens."""
    # ponytail: full rescan every 30 s (listing and stat-ing every transcript over /mnt/c cost ~300 ms a tick); in
    # between only the newest is checked, so a different session becoming the newest shows up within 30 s.
    seen = _cc_files.get(home)
    if not seen or time.time() - seen[0] > 30 or not os.path.exists(seen[1][0] if seen[1] else home):
        files = []
        for d in glob.glob(os.path.join(home, "projects", "*")):
            files += [os.path.join(d, f) for f in os.listdir(d) if f.endswith(".jsonl")] if os.path.isdir(d) else []
        files.sort(key=os.path.getmtime, reverse=True)
        _cc_files[home] = (time.time(), files)
    files = _cc_files[home][1]
    acct = {}
    try:
        o = json.load(open(os.path.join(os.path.dirname(home), ".claude.json"), encoding="utf-8")).get("oauthAccount") or {}
        acct = {"email": o.get("emailAddress"), "auth": o.get("billingType")}
    except (OSError, ValueError):
        pass
    q = _claude_quota.get(home, {})
    if not files:
        return {"title": None, "events": [], "usage": q.get("usage", []), "quota_at": q.get("at"), "quota_error": q.get("error"),
                "account": acct, "sessions": 0}
    newest = files[0]
    st = os.stat(newest)
    key = (newest, st.st_mtime, st.st_size)
    hit = _cc_cache.get(home)
    if hit and hit[0] == key:  # unchanged transcript: reading 3 MB over /mnt/c every tick cost ~300 ms
        info, tok, events = hit[1]
    else:
        info, tok, events = claude_transcript(newest)
        _cc_cache[home] = (key, (info, tok, events))
    recent = time.time() - st.st_mtime < 15
    return {"title": info["title"] or info["sid"], "sid": info["sid"], "cwd": info["cwd"], "turn": "working" if recent else "idle",
            "model": info["model"], "tokens": tok, "context": None, "last": iso(st.st_mtime),
            "events": recent_events(events), "usage": q.get("usage", []), "quota_at": q.get("at"), "quota_error": q.get("error"),
            "account": acct, "sessions": len(files)}


_cc_cache = {}  # home -> ((path, mtime, size), parsed transcript)
_cc_files = {}  # home -> (scanned at, transcripts newest first)


# What Claude Code adds around your words: reminders, task notices, command echoes. Pastes become a short marker.
CLAUDE_NOISE = re.compile(r"<(system-reminder|task-notification|command-name|command-message|command-args|local-command-stdout|local-command-caveat)>.*?</\1>\s*", re.S)
CLAUDE_PASTE = re.compile(r"<pasted_content[^>]*>\n?(.*?)(?:</pasted_content>|\Z)", re.S)  # an unclosed paste runs to the end


def claude_user_text(t):
    t = CLAUDE_NOISE.sub("", t)
    t = CLAUDE_PASTE.sub(lambda m: f"[Pasted text · {m.group(1).rstrip().count(chr(10)) + 1} lines]", t)
    return t.strip()


def claude_transcript(newest):
    """Messages, tool calls, model and tokens from the tail of one Claude Code transcript."""
    info = {"cwd": "", "sid": "", "model": None, "title": None}
    tok = {"input": 0, "cached": 0, "output": 0}
    events = []
    with open(newest, "rb") as f:  # transcripts grow large: the tail holds the recent turns
        f.seek(max(0, os.path.getsize(newest) - 12_000_000))
        lines = f.read().decode("utf-8", "replace").splitlines()[1:]
    for line in lines:
        if len(line) > 100_000 and '"tool_result"' in line[:3000]:
            continue  # screenshots and big outputs: Echo never shows tool results, and parsing them is the slow part
        try:
            o = json.loads(line)
        except ValueError:
            continue
        info["cwd"] = o.get("cwd") or info["cwd"]
        info["sid"] = o.get("sessionId") or info["sid"]
        if o.get("type") == "custom-title":
            info["title"] = o.get("customTitle") or info["title"]
        m, ts = o.get("message") or {}, o.get("timestamp")
        c = m.get("content")
        if o.get("type") == "user" and not o.get("isMeta") and (o.get("origin") or {}).get("kind") != "task-notification":
            texts = [c] if isinstance(c, str) else [x.get("text", "") for x in c or [] if isinstance(x, dict) and x.get("type") == "text"]
            for t in texts:
                if o.get("isCompactSummary"):  # the summary Claude Code writes when it compacts: not something you typed
                    events.append({"t": ts, "kind": "Compacted", "text": t[:20000]})
                elif t.startswith("[Request interrupted"):
                    events.append({"t": ts, "kind": "Interrupted", "text": ""})
                elif (t := claude_user_text(t)):
                    events.append({"t": ts, "kind": "UserMessage", "text": t[:20000]})
        elif o.get("type") == "assistant":
            info["model"] = m.get("model") or info["model"]
            u = m.get("usage") or {}
            tok["input"] += (u.get("input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0) + (u.get("cache_read_input_tokens") or 0)
            tok["cached"] += u.get("cache_read_input_tokens") or 0
            tok["output"] += u.get("output_tokens") or 0
            for x in c or []:
                if x.get("type") == "text" and x.get("text", "").strip():
                    events.append({"t": ts, "kind": "AgentMessage", "text": x["text"][:20000]})
                elif x.get("type") == "tool_use":
                    events.append({"t": ts, "kind": "Tool", "text": f"{x.get('name')}: " + short(json.dumps(x.get("input") or {}), 400)})
    tok["total"] = tok["input"] + tok["output"]
    return info, tok, events


CLAUDE_HOME = os.path.join(windows_home() or H, ".claude")
if os.path.isdir(CLAUDE_HOME) and not any(a[0] == "Claude Code" for a in AGENTS):
    AGENTS.append(("Claude Code", "Claude", "Windows" if CLAUDE_HOME.startswith("/mnt/") else "Local", CLAUDE_HOME))
# Aliases the claude CLI accepts for --model, with the levels of its --effort flag.
# ponytail: fixed list of current Claude models; update when a new family ships
CLAUDE_EFFORTS = ["low", "medium", "high", "xhigh", "max"]  # claude --help: --effort low|medium|high|xhigh|max
CLAUDE_MODELS = [{"id": i, "name": n, "efforts": CLAUDE_EFFORTS} for i, n in (
    ("claude-opus-5-5", "Opus 5.5"), ("claude-sonnet-5-5", "Sonnet 5.5"), ("claude-haiku-5-5", "Haiku 5.5"), ("claude-fable-5-2", "Fable 5.2"))]


# Claude's plan limits, as Claude Code's /usage and Codenotch read them: GET /api/oauth/usage with the token
# Claude Code keeps in <home>/.credentials.json. Read only: an expired token is never sent (the endpoint answers
# it with an hour-long 429) and never renewed here; Claude Code renews it the next time it runs.
CLAUDE_USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
_claude_quota = {}  # home -> {"usage": [...], "at": iso, "error": str|None}


def claude_limit_label(kind):
    named = {"session": "5h", "five_hour": "5h", "seven_day": "Weekly", "weekly_all": "Weekly", "weekly": "Weekly",
             "seven_day_opus": "Opus · Weekly", "weekly_opus": "Opus · Weekly", "seven_day_sonnet": "Sonnet · Weekly",
             "weekly_sonnet": "Sonnet · Weekly", "weekly_scoped": "Model-scoped · Weekly"}
    return named.get(kind) or kind.replace("_", " ").capitalize()


def claude_limits(v):
    """The usage reply as Echo's usage rows: `limits` first, then the named windows it may have dropped."""
    out = []
    for l in v.get("limits") or []:
        if isinstance(l, dict) and isinstance(l.get("percent"), (int, float)) and l.get("resets_at") and l.get("kind"):
            out.append({"label": claude_limit_label(l["kind"]), "used": round(float(l["percent"]), 1),
                        "resets_at": l["resets_at"], "window": l["kind"], "source": "Claude usage"})
    for field, w in v.items():  # five_hour, seven_day, seven_day_opus, ...: {utilization, resets_at} or null
        if not (field == "five_hour" or field.startswith("seven_day")) or not isinstance(w, dict):
            continue
        if not isinstance(w.get("utilization"), (int, float)) or "oauth" in field:
            continue
        row = {"label": claude_limit_label(field), "used": round(float(w["utilization"]), 1),
               "resets_at": w.get("resets_at"), "window": field, "source": "Claude usage"}
        if not any(r["label"] == row["label"] for r in out):
            out.append(row)
    out.sort(key=lambda r: r["label"] != "5h")  # the session first, as Claude shows it
    return out


def claude_quota_poller(home):
    import urllib.error, urllib.request
    backoff = 0
    while True:
        wait = AGY_QUOTA_EVERY
        prev = _claude_quota.get(home, {})
        try:
            with open(os.path.join(home, ".credentials.json"), encoding="utf-8") as f:
                o = json.load(f).get("claudeAiOauth") or {}
            if not o.get("accessToken"):
                raise KeyError
            if (o.get("expiresAt") or 0) / 1000 < time.time() + 60:
                err = "token_expired"
            else:
                req = urllib.request.Request(CLAUDE_USAGE_URL, headers={
                    "Authorization": "Bearer " + o["accessToken"], "anthropic-beta": "oauth-2025-04-20", "User-Agent": "echo-monitor"})
                with urllib.request.urlopen(req, timeout=15) as r:
                    usage = claude_limits(json.load(r))
                _claude_quota[home] = {"usage": usage, "at": datetime.now(timezone.utc).isoformat(), "error": None}
                backoff = 0
                err = None
        except (OSError, ValueError, KeyError) as e:
            err = "not_logged_in" if isinstance(e, (FileNotFoundError, KeyError)) else None
            if isinstance(e, urllib.error.HTTPError):
                err = {401: "token_expired", 403: "access_denied", 429: "rate_limited"}.get(e.code, f"HTTP {e.code}")
                if e.code == 429:  # 60 s doubling to 15 min; Retry-After only raises it
                    ra = e.headers.get("Retry-After")
                    wait = max(min(60 * 2 ** backoff, 900), int(ra) if ra and ra.isdigit() else 0)
                    backoff += 1
            err = err or short(type(e).__name__, 60)  # never the message: it could quote the request
        if err:
            _claude_quota[home] = {"usage": prev.get("usage", []), "at": prev.get("at"), "error": err}
        time.sleep(wait)


# ---------------------------------------------------------------- antigravity

_agy_quota = {}  # home -> {"usage": [...], "at": iso, "error": str|None}


def agy_quota_poller(home):
    while True:
        tok = home + "/antigravity-cli/antigravity-oauth-token"
        if os.path.exists(tok):
            try:
                r = subprocess.run([AGY_BIN, f"--gemini_dir={home}", "--output-format", "json", "-p", "/usage"],
                                   cwd="/tmp", stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=90)
                data = json.loads(r.stdout)["command"]["data"]
                usage = []
                for g in data.get("groups", []):
                    for b in g.get("buckets", []):
                        rem = b.get("remaining_fraction")
                        if rem is not None:
                            name = g.get("name", "").replace("Claude and GPT models", "Claude / GPT").replace("Gemini Models", "Gemini")
                            win = {"weekly": "Weekly", "5h": "5-Hour"}.get(b.get("window"), "")
                            reset = b.get("reset_time")
                            if not reset or reset.startswith("1970"):  # epoch 0 = window not started yet
                                reset = None
                            usage.append({"label": f"{name} · {win}" if win else name, "used": round(100 * (1 - rem), 1), "resets_at": reset,
                                          "window": b.get("window"), "source": "/usage"})
                _agy_quota[home] = {"usage": usage, "at": datetime.now(timezone.utc).isoformat(), "error": None}
            except Exception as e:
                prev = _agy_quota.get(home, {})
                _agy_quota[home] = {"usage": prev.get("usage", []), "at": prev.get("at"), "error": short(e, 160)}
        else:
            _agy_quota[home] = {"usage": [], "at": None, "error": "not_logged_in"}
        time.sleep(AGY_QUOTA_EVERY)


AGY_EFFORTS = ["low", "medium", "high", "xhigh", "max"]  # agy --help: --effort low|medium|high|xhigh|max
_agy_models = []


def agy_models_once():
    """`agy models` hits the network, so the collector asks once at start (Atlas's login)."""
    try:
        r = subprocess.run([AGY_BIN, f"--gemini_dir={G}", "models"], cwd="/tmp", stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, timeout=60)
        _agy_models[:] = [{"id": l.split("\t")[0], "name": l.split("\t")[1], "efforts": AGY_EFFORTS}
                          for l in r.stdout.splitlines() if "\t" in l]
    except Exception:
        pass


def codex_models():
    """Codex keeps the server's model list in models_cache.json; only the user-visible ones."""
    try:
        with open(C + "/models_cache.json") as f:
            ms = json.load(f).get("models", [])
    except (OSError, ValueError):
        return []
    ms = sorted((m for m in ms if m.get("visibility") == "list"), key=lambda m: m.get("priority", 99))
    return [{"id": m["slug"], "name": m.get("display_name") or m["slug"], "default_effort": m.get("default_reasoning_level"),
             "efforts": [r["effort"] for r in m.get("supported_reasoning_levels", [])]} for m in ms]


def agy_time(s):
    """agy stamps: '2026-11-21 12:00:00.123456789+00:00', '...Z', or '0001-01-01...' while a run is open."""
    m = re.match(r"(\d{4}-\d\d-\d\d)[ T](\d\d:\d\d:\d\d)(\.\d+)?", s or "")
    return None if not m or m.group(1).startswith("0001") else f"{m.group(1)}T{m.group(2)}{(m.group(3) or '')[:4]}+00:00"


AGY_ARG = ("AbsolutePath", "Path", "DirectoryPath", "SearchPath", "query", "Query", "Url", "Pattern", "Prompt")


def agy_arg(v):  # tool args arrive JSON-encoded: '"pwd"', 'true', '["*.md"]'
    try:
        v = json.loads(v) if isinstance(v, str) else v
    except ValueError:
        pass
    return v if isinstance(v, str) else json.dumps(v)


def agy_transcript(path):
    events = []
    for line in tail_lines(path):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        t, ty, c = agy_time(d.get("created_at")), d.get("type"), d.get("content") or ""
        if ty == "USER_INPUT":
            m = re.search(r"<USER_REQUEST>\s*(.*?)\s*</USER_REQUEST>", c, re.S)
            events.append({"t": t, "kind": "UserMessage", "text": (m.group(1) if m else c)[:20000]})
        elif ty == "PLANNER_RESPONSE":
            if c.strip():
                events.append({"t": t, "kind": "AgentMessage", "text": c[:20000]})
            for tc in d.get("tool_calls") or []:
                n, a = tc.get("name") or "?", {k: agy_arg(v) for k, v in (tc.get("args") or {}).items()}
                if n == "run_command":
                    events.append({"t": t, "kind": "CommandExecution", "text": short(a.get("CommandLine", ""), 600)})
                elif a.get("TargetFile") or re.search(r"write|edit|replace", n) and a.get("Path"):
                    events.append({"t": t, "kind": "FileChange", "text": a.get("TargetFile") or a["Path"]})
                else:
                    events.append({"t": t, "kind": "Tool", "text": f"{n}: " + short(next((a[k] for k in AGY_ARG if a.get(k)), ""), 300)})
        elif ty == "GENERIC" and "Command output:" in c and events and events[-1]["kind"] == "CommandExecution":
            events[-1]["out"] = c.split("Command output:", 1)[1].strip()[-4000:]
    return [e for e in events if e["t"]][-80:]


def agy(home):
    root = home + "/antigravity-cli"
    acct, model = {}, None
    try:
        t = json.load(open(root + "/antigravity-oauth-token"))
        acct = {"email": t.get("id_token_email") or jwt_email(t.get("id_token", "")), "auth": t.get("auth_method")}
    except (OSError, ValueError):
        pass
    try:
        model = json.load(open(root + "/settings.json")).get("model")
    except (OSError, ValueError):
        pass
    q = _agy_quota.get(home, {})
    base = {"usage": q.get("usage", []), "quota_at": q.get("at"), "quota_error": q.get("error"),
            "account": acct, "model": model if isinstance(model, str) else None}
    db = root + "/conversation_summaries.db"
    if not os.path.exists(db):
        return dict(base, title=None, events=[], sessions=0)
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=2)
    try:
        rows = con.execute(
            "select conversation_id, title, status, step_count, last_modified_time, preview, workspace_uris, not_fully_idle "
            "from conversation_summaries order by last_modified_time desc limit 12").fetchall()
        total = con.execute("select count(*) from conversation_summaries").fetchone()[0]
    finally:
        con.close()
    # ponytail: agy step details are protobuf blobs; we show conversation summaries only.
    if not rows:
        return dict(base, title=None, events=[], sessions=0)
    rows.sort(key=lambda r: bool(r[7]) or "RUNNING" in (r[2] or ""), reverse=True)  # an open run has no time yet
    cid, title, st, steps, lm, prev, ws, busy = rows[0]
    try:
        cwd = (json.loads(ws) or [""])[0].replace("file://", "")
    except (ValueError, TypeError, IndexError):
        cwd = ws or ""
    tr = f"{root}/brain/{cid}/.system_generated/logs/transcript.jsonl"
    if os.path.exists(tr):
        events, steps = agy_transcript(tr), steps or None
    else:  # older conversations: one summary row each
        events = [{"t": agy_time(r[4]), "kind": (r[2] or "").replace("CASCADE_RUN_STATUS_", "").title(),
                   "text": short(r[1] or r[5] or "(Untitled)", 400), "steps": r[3]} for r in reversed(rows) if agy_time(r[4])]
    last = agy_time(lm) or (iso(os.path.getmtime(tr)) if os.path.exists(tr) else None)
    return dict(base, title=short(title or prev, 160) or cid, sid=cid, cwd=cwd, steps=steps,
                turn="working" if busy or "RUNNING" in (st or "") else "idle",
                last=last, events=events, sessions=total, transcript=os.path.exists(tr))


# ---------------------------------------------------------------- main

TOOLS = {
    "python": sys.version.split()[0],
    "codex": bool(shutil.which("codex") or glob.glob(os.path.expanduser("~/.nvm/versions/node/*/bin/codex"))),
    "agy": os.path.exists(AGY_BIN),
    "claude": os.path.isdir(CLAUDE_HOME),
}


ROOMS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chat", "rooms")


def newest_room():
    """The most recently written group chat file, or None. The old single room.jsonl becomes the first one."""
    old = os.path.join(os.path.dirname(ROOMS), "room.jsonl")
    if os.path.exists(old):
        os.makedirs(ROOMS, exist_ok=True)
        os.replace(old, os.path.join(ROOMS, "r" + format(int(os.path.getmtime(old)), "x") + ".jsonl"))
    files = glob.glob(os.path.join(ROOMS, "*.jsonl"))
    return max(files, key=os.path.getmtime) if files else None


def places():
    """Where the collector reads each team: this Linux, or Windows through /mnt."""
    out = {}
    for team, _, _, home in AGENTS:
        where = "Windows" if home.startswith("/mnt/") else os.environ.get("WSL_DISTRO_NAME", "") or "Linux"
        if team not in out.setdefault(where, []):
            out[where].append(team)
    return out


def snapshot():
    procs = processes()
    out = []
    for team, name, role, home in AGENTS:
        try:
            info = codex(home) if team == "Codex" else claude_code(home) if team == "Claude Code" else agy(home)
        except Exception as e:  # one broken home must not hide the others
            info = {"title": None, "events": [], "usage": [], "error": short(e, 200)}
        if team == "Antigravity" and not info.get("transcript"):  # messages sent from the monitor (send.py); agy replies are not readable elsewhere
            try:
                with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "chat", name.lower() + ".jsonl")) as f:
                    info["events"] = info.get("events", []) + [json.loads(l) for l in f.readlines()[-40:] if l.strip()]
            except (OSError, ValueError):
                pass
        pids = procs.get(os.path.realpath(home), [])
        try:
            cpu, mem = proc_stats(pids)
        except Exception:
            cpu, mem = 0.0, 0.0
        info.update(team=team, name=name, role=role, home=home, pids=pids, running=bool(pids) or (team == "Claude Code" and info.get("turn") == "working"), cpu=cpu, mem=mem)
        out.append(info)
    room, room_file = [], newest_room()
    try:  # the newest group chat, written by send.py in room mode; older ones open through convs.py
        room = [json.loads(l) for l in tail_lines(room_file, 300_000)[-200:] if l.strip()] if room_file else []
    except (OSError, ValueError):
        pass
    return {"at": datetime.now(timezone.utc).isoformat(), "agents": out, "room": room, "room_file": room_file,
            "room_id": os.path.basename(room_file)[:-6] if room_file else None, "rooms_dir": ROOMS,
            "models": {"Codex": codex_models(), "Antigravity": _agy_models, "Claude Code": CLAUDE_MODELS},
            "env": {"home": H, "distro": os.environ.get("WSL_DISTRO_NAME", ""), "places": places(), "tools": TOOLS, "config": bool(CONFIG.get("agents"))}}


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--watch":
        for _, _, _, home in [a for a in AGENTS if a[0] == "Antigravity"]:
            threading.Thread(target=agy_quota_poller, args=(home,), daemon=True).start()
        for _, _, _, home in [a for a in AGENTS if a[0] == "Claude Code"]:
            threading.Thread(target=claude_quota_poller, args=(home,), daemon=True).start()
        threading.Thread(target=agy_models_once, daemon=True).start()
        while True:
            try:
                print(json.dumps(snapshot()), flush=True)
            except Exception as e:  # keep the collector alive; Echo logs stderr
                print(f"snapshot failed: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
            time.sleep(float(sys.argv[2]))
    else:
        for _, _, _, home in [a for a in AGENTS if a[0] == "Antigravity"][:1]:  # one-shot: probe only the first agy home
            threading.Thread(target=agy_quota_poller, args=(home,), daemon=True).start()
        time.sleep(8)
        print(json.dumps(snapshot(), indent=1))
