"""Builds docs/demo/site: Echo's page with a fake host and made-up data, for screenshots.

usage: python docs/demo/make_demo.py   (then docs/demo/shoot.ps1)
No agent homes are read: every name, number and message below is invented.
"""
import json, os, shutil
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
UI = os.path.join(HERE, "..", "..", "ui")
SITE = os.path.join(HERE, "site")
NOW = datetime.now(timezone.utc)
T = lambda **kw: (NOW - timedelta(**kw)).isoformat()
F = lambda **kw: (NOW + timedelta(**kw)).isoformat()

TEAM = [
    ("Codex", "Aaron", "Lead"), ("Codex", "Breeze", "Research"), ("Codex", "Clove", "Implementation"), ("Codex", "Dipper", "Review"),
    ("Antigravity", "Atlas", "Lead"), ("Antigravity", "Breach", "Research"), ("Antigravity", "Cypher", "Implementation"),
    ("Antigravity", "Draco", "Review"), ("Antigravity", "Ember", "To be decided"), ("Claude Code", "Claude", "Windows"),
]
USED = {"Aaron": 92, "Breeze": 41, "Clove": 65, "Dipper": 7, "Atlas": 58, "Breach": 23, "Cypher": 81, "Draco": 12, "Ember": 0, "Claude": 34}

def usage(team, name):
    u = USED[name]
    if team == "Codex":
        return [{"label": "5h", "used": min(100, u + 6), "resets_at": F(hours=3), "seen_at": T(minutes=2), "source": "rollout"},
                {"label": "Weekly", "used": u, "resets_at": F(days=4, hours=6), "seen_at": T(minutes=2), "source": "rollout"}]
    if team == "Antigravity":
        return [{"label": "Gemini · Weekly", "used": u, "resets_at": F(days=5), "seen_at": T(minutes=4), "source": "agy"},
                {"label": "Claude / GPT · Weekly", "used": max(0, u - 15), "resets_at": F(days=2), "seen_at": T(minutes=4), "source": "agy"},
                {"label": "Claude / GPT · 5-Hour", "used": max(0, u - 30), "resets_at": F(hours=2), "seen_at": T(minutes=4), "source": "agy"}]
    return [{"label": "5h", "used": u, "resets_at": F(hours=1, minutes=40), "seen_at": T(minutes=1), "source": "api"},
            {"label": "Weekly", "used": 18, "resets_at": F(days=3), "seen_at": T(minutes=1), "source": "api"}]

CHAT = [  # Aaron's chat: one finished turn with folded work, the Codex look
    ("UserMessage", 14, "Add a `--dry-run` flag to the export script and make sure the tests still pass.", None),
    ("CommandExecution", 13.8, "/usr/bin/zsh -lc rg -n \"def export\" src/", "src/export.py:12:def export(rows, out):"),
    ("AgentMessage", 13.6, "Found the export entry point. Adding the flag next to the other options.", None),
    ("FileChange", 13, "src/export.py", None),
    ("FileChange", 12.8, "tests/test_export.py", None),
    ("CommandExecution", 12.5, "/usr/bin/zsh -lc python -m pytest -q", "........                                    [100%]\n8 passed in 0.41s"),
    ("AgentMessage", 12.2, "Done. `--dry-run` prints what would be written and exits without touching the output file.\n\n"
     "- `src/export.py`: new flag, checked before the file is opened\n- `tests/test_export.py`: one test for the dry run\n\nAll 8 tests pass.", None),
]
ROOM = [
    ("say", 30, "you", ["Aaron", "Atlas"], "@Aaron @Atlas plan the CSV importer: who writes it, who reviews it?"),
    ("reply", 29, "Atlas", [], "Plan: Cypher writes the parser, Draco reviews it. I'll keep the task list.\n\n@Cypher: write the CSV parser with tests"),
    ("reply", 28, "Aaron", [], "Agreed. Clove can take the CLI wiring once the parser lands; Dipper reviews that part."),
    ("reply", 20, "Cypher", [], "Parser is in `importer/csv.py` with 12 tests, all green. Handles quoted commas and BOMs."),
]

def agent(team, name, role):
    busy = name in ("Clove", "Cypher")
    a = {"team": team, "name": name, "role": role, "home": "~/." + team.lower().split()[0], "pids": [4242] if busy else [],
         "running": busy, "cpu": 3.1 if busy else 0.0, "mem": 180.0 if busy else 0.0, "sessions": 3 + len(name),
         "title": "CSV importer" if busy else "Export dry run", "sid": "00000000-0000-4000-8000-%012d" % len(name),
         "cwd": "~/projects/demo", "turn": T(minutes=5), "model": None, "context": 0.31 if busy else 0.12,
         "tokens": {"input": 120000, "cached": 80000, "output": 9000, "total": 129000}, "plan": "pro",
         "last": T(minutes=1) if busy else T(hours=len(name)), "usage": usage(team, name),
         "account": {"email": name.lower() + "@example.com", "auth": "chatgpt" if team == "Codex" else "oauth"}, "events": []}
    if name == "Aaron":
        a["events"] = [{"t": T(minutes=m), "kind": k, "text": t, **({"out": o} if o else {})} for k, m, t, o in CHAT]
    return a

snap = {"at": NOW.isoformat(), "agents": [agent(*x) for x in TEAM], "room_id": "demo-room", "room_file": None, "rooms_dir": "",
        "room": [{"t": T(minutes=m), "task": "t1", "kind": k, "from": f, "to": to, "text": x} for k, m, f, to, x in ROOM],
        "models": {"Codex": [{"id": "gpt-5", "name": "GPT-5", "efforts": ["low", "medium", "high"]}], "Antigravity": [],
                   "Claude Code": [{"id": "opus", "name": "Opus", "efforts": ["low", "medium", "high", "xhigh", "max"]}]},
        "env": {"home": "/home/you", "distro": "Ubuntu", "places": {"Ubuntu": ["Codex", "Antigravity"], "Windows": ["Claude Code"]},
                "tools": {"python": "3.12", "codex": True, "agy": True, "claude": True}, "config": False}}
convs = {"agents": {n: [{"id": "c%d-%s" % (i, n), "title": t, "cwd": "~/projects/demo", "last": T(hours=i * 5 + 1)}
                        for i, t in enumerate(["Export dry run", "Flaky test in CI", "README typos"])] for _, n, _ in TEAM},
         "rooms": [{"id": "demo-room", "title": "CSV importer", "last": T(minutes=20)}]}

shutil.rmtree(SITE, ignore_errors=True)
shutil.copytree(UI, SITE)
html = open(os.path.join(SITE, "index.html"), encoding="utf-8").read()
html = html.replace("<script>", "<script src=\"mock.js\"></script>\n<script>", 1)
open(os.path.join(SITE, "index.html"), "w", encoding="utf-8").write(html)
mock = open(os.path.join(HERE, "mock.js"), encoding="utf-8").read()
open(os.path.join(SITE, "mock.js"), "w", encoding="utf-8").write(
    "const DEMO_SNAP = " + json.dumps(snap) + ";\nconst DEMO_CONVS = " + json.dumps(convs) + ";\n" + mock)
print("built", SITE)
