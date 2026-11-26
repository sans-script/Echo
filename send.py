#!/usr/bin/env python3
"""Send one message to an agent from Echo. usage: send.py <Name> [model] [effort] [continue|new|<session id>] [access] [hex folder]  (each may be "default"; message on stdin)
       send.py --stop <Name>  (ends that agent's running send)
       send.py <Name> ... <hex folder> room  (group chat: stdin is JSON {task, from, to, show, prompt};
         `show` and the reply go to chat/rooms/<room>.jsonl; ECHO_DRY_RUN=1 skips the agent, ECHO_ROOM moves the file)

Continues the agent's most recent conversation with the same commands the team leads use
(see ../LEAD_*.md). Codex replies land in the agent's own rollout, which snapshot.py already reads.
agy replies are not readable from its private state, so both sides of the exchange are appended to
a log the monitor owns (chat/<name>.jsonl). Never writes to any agent home.
"""
import glob, json, os, re, shutil, signal, subprocess, sys, threading
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from snapshot import AGENTS, AGY_BIN, agy, codex  # noqa: E402

CHAT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chat")
TIMEOUT = 30 * 60  # ponytail: fixed limit per send; make it a setting if long jobs need more
# Safe defaults when Echo sends no access choice. Antigravity stays on full: its other modes deny tools headless.
DEFAULT_ACCESS = {"Codex": "write", "Claude Code": "edits", "Antigravity": "full"}
def node_bin():
    """Folder with `codex` (and its node): PATH first, else the newest nvm install."""
    found = shutil.which("codex")
    if found:
        return os.path.dirname(found)
    nvm = sorted(glob.glob(os.path.expanduser("~/.nvm/versions/node/*/bin")), key=lambda d: [int(x) for x in re.findall(r"\d+", d)])
    return nvm[-1] if nvm else ""
# Access presets -> CLI flags. `codex exec resume` has no -s, so the sandbox goes through a -c override.
CODEX_ACCESS = {
    "full": ["--dangerously-bypass-approvals-and-sandbox"],
    "write": ["-c", 'sandbox_mode="workspace-write"'],
    "read": ["-c", 'sandbox_mode="read-only"'],
}
CLAUDE_ACCESS = {"full": "bypassPermissions", "auto": "auto", "edits": "acceptEdits", "plan": "plan"}
AGY_ACCESS = {
    "full": ["--dangerously-skip-permissions"],
    "auto": ["--mode", "auto"],
    "edits": ["--mode", "accept-edits"],
    "plan": ["--mode", "plan"],
}


ROOM = os.environ.get("ECHO_ROOM")  # set from the request's room id when send.py runs in room mode
ROOM_REQ = {}  # the group-chat request being run, when send.py runs in room mode


def room_log(frm, kind, text, to=None):
    if not ROOM:  # no valid room id: nothing to log to
        return
    os.makedirs(os.path.dirname(ROOM), exist_ok=True)
    with open(ROOM, "a") as f:
        f.write(json.dumps({"t": now(), "task": ROOM_REQ.get("task"), "from": frm, "to": to or [], "kind": kind,
                            "text": str(text)[:20000]}) + "\n")


def now():
    return datetime.now(timezone.utc).isoformat()


def log(name, kind, text):
    os.makedirs(CHAT, exist_ok=True)
    with open(os.path.join(CHAT, name.lower() + ".jsonl"), "a") as f:
        f.write(json.dumps({"t": now(), "kind": kind, "text": text}) + "\n")


def pidfile(name):
    return os.path.join(CHAT, name.lower() + ".pid")


def stop(name):
    """Ends a running send: its whole process group (send.py and the CLI it started)."""
    try:
        with open(pidfile(name)) as f:
            pid = int(f.read().strip())
        os.killpg(pid, signal.SIGTERM)
    except (OSError, ValueError, AttributeError):
        sys.exit("nothing to stop")


def gone(path, folder, new):
    """The session's folder was deleted: refuse rather than run the agent in the home folder."""
    if path and not folder and not new and not os.path.isdir(path):
        sys.exit(f"The session's folder {path} no longer exists. Choose a folder or start a new session.")


def main():
    if sys.argv[1:2] == ["--stop"]:
        return stop(sys.argv[2] if len(sys.argv) > 2 else "")
    name = sys.argv[1] if len(sys.argv) > 1 else ""
    agent = next((a for a in AGENTS if a[1] == name), None)
    msg = sys.stdin.read().strip()
    room = sys.argv[7:8] == ["room"]
    if room:
        try:
            ROOM_REQ.update(json.loads(msg), name=name)
        except ValueError:
            sys.exit("bad room message")
        msg = str(ROOM_REQ.get("prompt") or "").strip()
        rid = str(ROOM_REQ.get("room") or "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", rid):
            sys.exit("bad room id")
        global ROOM
        ROOM = ROOM or os.path.join(CHAT, "rooms", rid + ".jsonl")
    opt = [a if a != "default" and re.fullmatch(r"[A-Za-z0-9._:-]{1,64}", a) else None for a in (sys.argv[2:6] + ["default"] * 4)[:4]]
    model, effort, session, access = opt
    new = session == "new"
    sid_pick = session if session not in (None, "new", "continue") else None  # a conversation chosen in Echo's list
    folder = None  # chosen working folder, hex-encoded by Echo so spaces survive the command line
    if len(sys.argv) > 6 and re.fullmatch(r"(?:[0-9a-f]{2}){1,1024}", sys.argv[6]):
        folder = bytes.fromhex(sys.argv[6]).decode("utf-8", "replace")
        if not os.path.isabs(folder) or not os.path.isdir(folder):
            sys.exit(f"folder not found: {folder}")
    if not agent or not msg:
        sys.exit("unknown agent or empty message")
    team, _, _, home = agent
    if room and ROOM_REQ.get("show"):  # the asker's words, logged once by the first send of a message
        room_log(str(ROOM_REQ.get("from") or "You"), "say", ROOM_REQ["show"], [str(x) for x in ROOM_REQ.get("to") or [name]])
    if room and os.environ.get("ECHO_DRY_RUN"):
        return room_log(name, "reply", "Dry run: " + msg[:200])
    reply = ""
    access = access or DEFAULT_ACCESS.get(team)
    if hasattr(os, "setpgrp"):  # own process group, so --stop ends the CLI too
        try:
            os.setpgrp()
        except OSError:
            pass  # already a session leader (as under wsl.exe), which also leads its group
        if os.getpgrp() == os.getpid():  # never record a group this send does not own
            os.makedirs(CHAT, exist_ok=True)
            with open(pidfile(name), "w") as f:
                f.write(str(os.getpid()))
    if team == "Codex":
        info = codex(home)  # newest session id + cwd, read-only
        if sid_pick:  # its folder comes from Echo, which read it from that session
            info = {"cwd": folder, "title": sid_pick, "sessions": 1}
        gone(info.get("cwd"), folder, new)
        cwd = info["cwd"] if info.get("cwd") and os.path.isdir(info["cwd"]) else os.path.expanduser("~")
        if folder and os.path.realpath(folder) != os.path.realpath(cwd) and not sid_pick:
            cwd, new = folder, True  # a Codex session keeps its folder, so another folder means a new session
        env = dict(os.environ, CODEX_HOME=home, PATH=node_bin() + ":" + os.environ.get("PATH", ""))
        flags = CODEX_ACCESS.get(access, CODEX_ACCESS["write"]) + ["--skip-git-repo-check"]
        sid = info.get("title") if info.get("sessions") and not new else None
        flags += (["-m", model] if model else []) + (["-c", f'model_reasoning_effort="{effort}"'] if effort else [])
        last = os.path.join(CHAT, name.lower() + ".last")  # the final reply, for the group chat
        os.makedirs(CHAT, exist_ok=True)
        flags += ["-o", last]
        cmd = ["codex", "exec"] + (["resume"] + flags + [sid, "-"] if sid else flags + ["-C", cwd, "-"])
        r = subprocess.run(cmd, cwd=cwd, env=env, input=msg, capture_output=True, text=True, timeout=TIMEOUT)
        if r.returncode:
            sys.exit((r.stderr or r.stdout).strip()[-400:] or f"codex exited {r.returncode}")
        try:
            with open(last) as f:
                reply = f.read().strip()
        except OSError:
            pass
    elif team == "Claude Code":
        # Runs in the chosen folder, else the profile folder, so "continue" picks up the latest conversation
        # there rather than one open in some project. Claude Code writes its own transcript, which snapshot.py reads.
        profile = os.path.dirname(home)
        exe = shutil.which("claude") if not home.startswith("/mnt/") else os.path.join(profile, ".local", "bin", "claude.exe")
        if not exe or not os.path.exists(exe):
            sys.exit("Claude Code not found")
        cmd = [exe, "-p", "--permission-mode", CLAUDE_ACCESS.get(access, CLAUDE_ACCESS["edits"])]
        cmd += (["--model", model] if model else []) + (["--effort", effort] if effort else [])
        cmd += [] if new else ["--resume", sid_pick] if sid_pick else ["--continue"]
        if sid_pick and len(sys.argv) > 8 and re.fullmatch(r"(?:[0-9a-f]{2}){1,1024}", sys.argv[8]):
            cmd += ["-n", bytes.fromhex(sys.argv[8]).decode("utf-8", "replace")]  # the name you gave it in Echo's Chats
        r = subprocess.run(cmd, cwd=folder or profile, input=msg, capture_output=True, text=True, encoding="utf-8", timeout=TIMEOUT)
        if r.returncode:
            sys.exit((r.stderr or r.stdout).strip()[-400:] or f"claude exited {r.returncode}")
        reply = r.stdout.strip()
    else:
        con = os.path.join(home, "antigravity-cli", "conversation_summaries.db")
        ws = agy(home).get("cwd")  # latest conversation's workspace (agy has no -C)
        gone(ws, folder, new)
        cwd = folder or (ws if ws and os.path.isdir(ws) else os.path.expanduser("~"))
        log(name, "UserMessage", msg)
        cmd = [AGY_BIN, f"--gemini_dir={home}", "--print-timeout=10m"] + AGY_ACCESS.get(access, AGY_ACCESS["full"])
        cmd += (["--model", model] if model else []) + (["--effort", effort] if effort else [])
        if sid_pick:
            cmd += ["--conversation", sid_pick]
        elif os.path.exists(con) and not new:
            cmd.append("--continue")
        # stream-json: tool steps are logged as they start, so the drawer shows progress before the reply lands.
        cmd += ["--output-format", "stream-json", "--print", msg]
        p = subprocess.Popen(cmd, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        timer = threading.Timer(TIMEOUT, p.kill); timer.daemon = True; timer.start()
        seen, out, other = set(), "", []
        for line in p.stdout:
            try:
                ev = json.loads(line)
            except ValueError:
                other.append(line.strip())  # plain notices, e.g. a denied permission
                continue
            su = ev.get("step_update") or {}
            if su.get("step_type") == "tool" and su.get("step_index") not in seen:
                seen.add(su.get("step_index"))
                ti = su.get("tool_info") or {}
                log(name, "Tool", f"{su.get('tool_name') or ti.get('name')}: " + json.dumps(ti.get("parameters") or {})[:400])
            elif su.get("state") == "ERROR" and (su.get("tool_info") or {}).get("error"):
                other.append(su["tool_info"]["error"].get("message", ""))
            res = ev.get("result")
            if res:
                out = (res.get("response") or "").strip()
        p.wait(); timer.cancel()
        if p.returncode and p.returncode < 0 and not out:
            sys.exit("Stopped" if p.returncode == -signal.SIGTERM else f"Timed out after {TIMEOUT // 60} min")
        if out:
            log(name, "AgentMessage", out)
            reply = out
        else:
            sys.exit(" ".join(x for x in other if x)[-400:] or f"agy exited {p.returncode} with no reply")
    if room:
        room_log(name, "reply", reply or "(no reply text)")


def run():
    try:
        main()
    except subprocess.TimeoutExpired:
        sys.exit(f"Timed out after {TIMEOUT // 60} min")
    except KeyboardInterrupt:
        sys.exit("Stopped")


if __name__ == "__main__":
    try:
        run()
    except SystemExit as e:
        if ROOM_REQ and e.code not in (None, 0):  # failures show in the room too
            room_log(ROOM_REQ.get("name") or "?", "error", e.code if isinstance(e.code, str) else f"exited {e.code}")
        raise
