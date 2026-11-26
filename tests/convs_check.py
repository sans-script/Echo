"""convs.py on throwaway homes: list, open and delete without touching any real agent. python3 tests/convs_check.py"""
import json, os, sys, tempfile, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import convs  # noqa: E402

t = tempfile.mkdtemp()
cx, cc = os.path.join(t, "codex"), os.path.join(t, "claude")
sid = "01a1c5d1-7d95-7060-830f-1bbe3118109a"
os.makedirs(os.path.join(cx, "sessions", "2026", "11", "10"))
roll = os.path.join(cx, "sessions", "2026", "11", "10", f"rollout-2026-11-10T11-16-43-{sid}.jsonl")
with open(roll, "w") as f:
    f.write(json.dumps({"type": "session_meta", "payload": {"id": sid, "cwd": "/home/x"}}) + "\n")
    f.write(json.dumps({"type": "event_msg", "timestamp": "2026-11-10T14:17:40Z", "payload": {"type": "item_completed", "item": {"type": "UserMessage", "content": [{"type": "text", "text": "[Echo group chat · task T1 · x]\nYou are A.\n\nMessage from the user:\nfix the parser\n\nHow to reply:"}]}}}) + "\n")
os.makedirs(os.path.join(cc, "projects", "C--x", "abc-1", "subagents"))
tr = os.path.join(cc, "projects", "C--x", "abc-1.jsonl")
with open(tr, "w") as f:
    f.write(json.dumps({"type": "user", "cwd": "C:\\Users\\x", "message": {"content": "<system-reminder>r</system-reminder>hello there"}}) + "\n")
open(os.path.join(cc, "projects", "C--x", "stub.jsonl"), "w").write("{}\n")  # no message of yours: not listed
convs.AGENTS[:] = [("Codex", "A", "", cx), ("Claude Code", "C", "", cc)]

lst = convs.codex_list(cx)
assert lst == [{"id": sid, "title": "Group chat: fix the parser", "cwd": "/home/x", "last": lst[0]["last"]}], lst
cl = convs.claude_list(cc)
assert [c["id"] for c in cl] == ["abc-1"] and cl[0]["title"] == "hello there", cl
assert convs.open_conv("A", sid)["events"][0]["kind"] == "UserMessage"

# Bad input never reaches the file system; a file in use is kept; then delete removes the file (and Claude's folder).
assert convs.main(["delete", "A", "../../etc"])["ok"] is False
assert convs.main(["delete", "Nobody", sid])["ok"] is False
assert convs.delete("A", sid)["ok"] is False and os.path.exists(roll)  # just written: in use
old = time.time() - 60
os.utime(roll, (old, old)); os.utime(tr, (old, old))
assert convs.delete("A", sid) == {"ok": True} and not os.path.exists(roll)
assert convs.delete("C", "abc-1") == {"ok": True} and not os.path.exists(tr) and not os.path.exists(tr[:-6])
assert convs.delete("C", "abc-1")["ok"] is False  # already gone
print("ok")
