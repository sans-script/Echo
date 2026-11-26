#!/usr/bin/env python3
"""Echo's conversation list. Prints one JSON object.
  convs.py list                   every agent's conversations and every group chat
  convs.py open <Name|room> <id>  one conversation's messages
  convs.py delete <Name|room> <id>

Agents' histories are read read-only. Delete removes only that one session's file for Codex and Claude Code
(the user asked for that), or Echo's own group chat file. Antigravity keeps its history in a database Echo never
edits, so there Echo only hides the conversation (the page remembers that).
"""
import glob, json, os, re, shutil, sqlite3, subprocess, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from snapshot import (AGENTS, ROOMS, agy_time, agy_transcript, claude_transcript, claude_user_text,  # noqa: E402
                      codex_rollout, iso, newest_room, recent_events, short, tail_lines, text_of)

ID = re.compile(r"[A-Za-z0-9._:-]{1,64}")
LIVE = 15  # seconds: a file written this recently is in use, so it is not deleted


def titled(text):
    """A readable title: a message Echo sent from the group chat shows the words it carried, not its header."""
    text = str(text or "")
    if text.startswith("[Echo group chat"):
        m = re.search(r"\n(?:Message from the user|Hand-off from (\w+)):\n(.+?)(?:\n\n|$)", text, re.S)
        text = ("Group chat: " + (f"{m.group(1)} asked: " if m.group(1) else "") + m.group(2)) if m else "Group chat"
    return short(" ".join(text.split()), 120)


def head(path, size=96_000):
    """The complete lines in a file's first `size` bytes (a session's start holds its folder and first message)."""
    with open(path, "rb") as f:
        data = f.read(size)
        cut = len(data) == size and f.read(1)  # more follows: the last line read may be partial
    lines = data.decode("utf-8", "replace").splitlines()
    return lines[:-1] if cut and len(lines) > 1 else lines


def codex_files(home):
    """Session id -> rollout file. The id is the UUID at the end of the file name."""
    out = {}
    for d, _, files in os.walk(os.path.join(home, "sessions")):
        for f in files:
            m = re.search(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.jsonl$", f)
            if m:
                out[m.group(1)] = os.path.join(d, f)
    return out


def codex_list(home):
    names = {}
    try:  # thread names Codex gives its sessions, newest last
        for line in open(os.path.join(home, "session_index.jsonl"), encoding="utf-8"):
            try:
                d = json.loads(line)
                names[d.get("id")] = d.get("thread_name")
            except ValueError:
                pass
    except OSError:
        pass
    out = []
    for sid, path in codex_files(home).items():
        cwd, first = "", ""
        for line in head(path):
            try:
                d = json.loads(line)
            except ValueError:
                continue
            p = d.get("payload") or {}
            if d.get("type") == "session_meta":
                cwd = p.get("cwd", "")
            elif d.get("type") == "event_msg" and p.get("type") == "item_completed" and (p.get("item") or {}).get("type") == "UserMessage":
                first = str(text_of(p["item"]))
                break
        out.append({"id": sid, "title": titled(names.get(sid) or first) or "Untitled", "cwd": cwd, "last": iso(os.path.getmtime(path))})
    return out


def claude_files(home):
    return {os.path.basename(f)[:-6]: f for f in glob.glob(os.path.join(home, "projects", "*", "*.jsonl"))}


def claude_list(home):
    out = []
    for sid, path in claude_files(home).items():
        cwd, first, title = "", "", ""
        for line in head(path):
            try:
                d = json.loads(line)
            except ValueError:
                continue
            cwd = cwd or d.get("cwd") or ""
            if not first and d.get("type") == "user" and not d.get("isMeta") and not d.get("isCompactSummary"):
                c = (d.get("message") or {}).get("content")
                texts = [c] if isinstance(c, str) else [x.get("text", "") for x in c or [] if isinstance(x, dict) and x.get("type") == "text"]
                first = next((t for t in map(claude_user_text, texts) if t and not t.startswith("[Request interrupted")), "")
        # ponytail: a custom title is looked for only near the end (where /rename writes it); a full scan of every
        # transcript would take seconds over /mnt/c.
        for line in reversed(tail_lines(path, 64_000)):
            if '"custom-title"' in line:
                try:
                    title = json.loads(line).get("customTitle") or ""
                except ValueError:
                    pass
                break
        m = re.match(r"([A-Za-z]):[\\/](.*)$", cwd)
        if m and home.startswith("/mnt/"):  # Claude Code on Windows records C:\..., the scripts see /mnt/c/...
            cwd = "/mnt/" + m.group(1).lower() + "/" + m.group(2).replace("\\", "/")
        if first or title:  # a file with no message of yours is a stub (an aborted start), not a conversation
            out.append({"id": sid, "title": titled(title or first), "cwd": cwd, "last": iso(os.path.getmtime(path))})
    return out


def agy_db(home):
    return os.path.join(home, "antigravity-cli", "conversation_summaries.db")


def agy_list(home):
    if not os.path.exists(agy_db(home)):
        return []
    con = sqlite3.connect(f"file:{agy_db(home)}?mode=ro", uri=True, timeout=2)
    try:
        rows = con.execute("select conversation_id, title, preview, last_modified_time, workspace_uris from conversation_summaries").fetchall()
    finally:
        con.close()
    out = []
    for cid, title, prev, lm, ws in rows:
        try:
            cwd = (json.loads(ws) or [""])[0].replace("file://", "")
        except (ValueError, TypeError, IndexError):
            cwd = ws or ""
        out.append({"id": cid, "title": titled(title or prev) or "Untitled", "cwd": cwd, "last": agy_time(lm)})
    return out


def room_lines(path):
    return [json.loads(l) for l in tail_lines(path, 300_000)[-200:] if l.strip()]


def rooms_list():
    newest_room()  # moves the old single room.jsonl into chat/rooms
    out = []
    for path in glob.glob(os.path.join(ROOMS, "*.jsonl")):
        try:
            lines = room_lines(path)
        except (OSError, ValueError):
            continue
        said = next((e for e in lines if e.get("kind") == "say"), None)
        who = sorted({e.get("from") for e in lines if e.get("from") and e.get("from") != "You"})
        out.append({"id": os.path.basename(path)[:-6], "title": short((said or {}).get("text", ""), 120) or "Group chat",
                    "members": who, "count": len(lines), "last": iso(os.path.getmtime(path))})
    return out


def agent(name):
    return next((a for a in AGENTS if a[1] == name), None)


def listing():
    agents = {}
    for team, name, _, home in AGENTS:
        try:
            agents[name] = codex_list(home) if team == "Codex" else claude_list(home) if team == "Claude Code" else agy_list(home)
        except Exception as e:  # one broken home must not hide the others
            agents[name] = {"error": short(e, 200)}
    return {"agents": agents, "rooms": rooms_list()}


def open_conv(name, cid):
    if name == "room":
        return {"events": room_lines(os.path.join(ROOMS, cid + ".jsonl"))}
    team, _, _, home = agent(name)
    if team == "Codex":
        info, events = codex_rollout(codex_files(home)[cid], 3_000_000)
        return {"events": recent_events(events), "cwd": info["cwd"], "model": info["model"]}
    if team == "Claude Code":
        info, _, events = claude_transcript(claude_files(home)[cid])
        return {"events": recent_events(events), "cwd": info["cwd"], "model": info["model"]}
    tr = os.path.join(home, "antigravity-cli", "brain", cid, ".system_generated", "logs", "transcript.jsonl")
    if os.path.exists(tr):
        return {"events": recent_events(agy_transcript(tr))}
    row = next((r for r in agy_list(home) if r["id"] == cid), None)  # older conversations keep only a summary
    return {"events": [{"t": row["last"], "kind": "AgentMessage", "text": row["title"]}] if row else []}


def delete(name, cid):
    if name == "room":
        paths = [os.path.join(ROOMS, cid + ".jsonl")]
    else:
        team, _, _, home = agent(name)
        if team == "Antigravity":
            return {"ok": True, "hidden": True}  # its database is Antigravity's own: Echo only hides the row
        path = (codex_files(home) if team == "Codex" else claude_files(home)).get(cid)
        if not path:
            return {"ok": False, "error": "That conversation no longer exists."}
        paths = [path]
        side = path[:-6]  # Claude Code keeps a session's subagent and tool output files in a folder of the same name
        if team == "Claude Code" and os.path.isdir(side):
            paths.append(side)
    if any(os.path.exists(p) and time.time() - os.path.getmtime(p) < LIVE for p in paths[:1]):
        return {"ok": False, "error": "This conversation is in use right now. Try again when it is idle."}
    if name != "room" and team == "Codex" and codex_delete(home, cid):
        return {"ok": True}  # Codex's own delete also drops the session from its index and database
    for p in paths:
        if os.path.isdir(p):
            shutil.rmtree(p)
        elif os.path.exists(p):
            os.remove(p)
    return {"ok": True}


def codex_delete(home, cid):
    """`codex delete --force <id>`; False when the CLI is missing or fails, so the caller removes the file itself."""
    from send import node_bin
    try:
        r = subprocess.run(["codex", "delete", "--force", cid], env=dict(os.environ, CODEX_HOME=home, PATH=node_bin() + ":" + os.environ.get("PATH", "")),
                           stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0


def main(argv):
    if argv[:1] == ["list"]:
        return listing()
    if len(argv) == 3 and argv[0] in ("open", "delete") and ID.fullmatch(argv[2]) and (argv[1] == "room" or agent(argv[1])):
        try:
            return (open_conv if argv[0] == "open" else delete)(argv[1], argv[2])
        except (KeyError, OSError, ValueError) as e:
            return {"ok": False, "error": "That conversation could not be read." if argv[0] == "open" else short(e, 200)}
    return {"ok": False, "error": "usage: convs.py list | open <Name|room> <id> | delete <Name|room> <id>"}


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1:])), flush=True)
