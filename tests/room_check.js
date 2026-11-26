// Group chat logic from ui/index.html, run without a page: node tests/room_check.js ui/index.html
const fs = require("fs"), assert = require("assert");
const html = fs.readFileSync(process.argv[2] || "ui/index.html", "utf8"), js = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const cut = (from, to) => { const a = js.indexOf(from), b = js.indexOf(to, a); assert(a >= 0 && b > a, "missing " + from); return js.slice(a, b); };

// Minimal stand-ins for the page.
const sent = [], spoken = [];
global.localStorage = { getItem: () => null, setItem: () => {} };
global.DEFAULT_ACCESS = { Codex: "write", "Claude Code": "edits", Antigravity: "full" };
global.state = { pending: {}, sendError: {}, snap: null, selected: null };
global.settings = { roomCap: 12, roomRecap: true, roomSpeak: false, voices: {}, voice: "v0" };
global.voice = { hasKey: true, voices: [] };
global.player = { loading: false, audio: null };
global.choices = {}; global.ICONS = {}; global.host = true;
global.send = m => sent.push(m);
global.speak = (name, text) => spoken.push([name, text]);
global.render = global.renderDrawer = global.renderTeamVoices = () => {};
global.saveSetting = (k, v) => { settings[k] = v; };
global.$ = () => ({ dataset: {} });
global.day = () => "Dec 1";
global.esc = s => String(s);
global.spokenText = t => (String(t).match(/Voice summary:\s*(.+)$/im) || [])[1] || "";
eval(cut("const ROOM = ", "/* ---- room panel ---- */").replace(/^const (\w+)/gm, "global.$1").replace(/^function (\w+)/gm, "global.$1 = function $1"));
eval(cut("const voiceOf = ", "/* The one voice popover").replace(/^const (\w+)/gm, "global.$1").replace(/^function (\w+)/gm, "global.$1 = function $1"));
global.renderTeamVoices = () => {};  // drawing needs the page
eval(cut("const isMention = ", "/* The group box").replace(/^const (\w+)/gm, "global.$1"));

const ag = (name, team, role, used) => ({ name, team, role, usage: used == null ? [] : [{ label: "Weekly", used, resets_at: "2026-12-01T00:00:00Z" }] });
roomCfg.id = "r1";
state.snap = { room: [], room_id: "r1", rooms_dir: "/x/chat/rooms", agents: [ag("Aaron", "Codex", "Lead", 40), ag("Dipper", "Codex", "Review", 10),
  ag("Atlas", "Antigravity", "Lead", 20), ag("Cypher", "Antigravity", "Implementation", 95), ag("Claude", "Claude Code", "Engineer", null)] };

// Mentions: names outside code; none -> leads.
assert.deepStrictEqual(roomTargets("@dipper and @Atlas please, not `@Aaron`"), ["Dipper", "Atlas"]);
assert.deepStrictEqual(roomTargets("no one named"), ["Aaron", "Atlas"]);
assert.deepStrictEqual(roomTargets("mail me@Aaron.com"), ["Aaron", "Atlas"]);
assert.deepStrictEqual(roomTargets("@all go"), ["Aaron", "Dipper", "Atlas", "Cypher", "Claude"]);
assert.deepStrictEqual(roomTargets("`@all` me@all.com"), ["Aaron", "Atlas"]);
assert.strictEqual(mentionHl("hi @all and @Dipper, not @Bob"), 'hi <span class="mention">@all</span> and <span class="mention">@Dipper</span>, not @Bob');
// Hand-offs: "@Name: brief" lines only, not in code, not to oneself, once per agent.
const h = roomHandoffs("Plan:\n- **@Dipper:** write tests\n@Atlas — review it\n@Dipper: again\n@Aaron: me\n```\n@Claude: no\n```\nask @Claude later", "Aaron");
assert.deepStrictEqual(h, [{ to: "Dipper", brief: "write tests" }, { to: "Atlas", brief: "review it" }]);

// Prompt: only the room since the agent's last turn, capped; team table with limits.
state.snap.room = [
  { t: "1", from: "You", kind: "say", text: "old task", to: ["Aaron"] },
  { t: "2", from: "Aaron", kind: "reply", text: "old reply" },
  { t: "3", from: "You", kind: "say", text: "x".repeat(900), to: ["Dipper"] },
  { t: "4", from: "Dipper", kind: "error", text: "boom" }];
roomRun.task = "T1";
let p = roomPrompt("Aaron", "do it", "You");
assert(!p.includes("old reply") && !p.includes("old task") && p.includes("x".repeat(600) + " … (cut") && !p.includes("boom"));
assert(p.includes("Cypher (Implementation, Antigravity): 95% of weekly limit used, resets Dec 1, AT LIMIT") && p.includes("Claude (Engineer, Claude Code): usage unknown"));
assert(p.includes("/x/chat/rooms/r1.jsonl") && p.includes("Message from the user:\ndo it") && p.includes("Voice summary:"));
assert(roomPrompt("Dipper", "q", "Aaron").includes("Hand-off from Aaron:\nq"));
// English always, natural tone, and a note when others got the same message.
assert(p.includes("Write in English") && p.includes("Do not narrate your process") && !p.includes("user's language"));
assert(roomPrompt("Aaron", "@all", "You", 9).includes("9 teammates were called") && !p.includes("teammates were called"));

// Access -> each agent's mode; at-limit agents are never sent to.
state.snap.room = [];
roomCfg.access = "read"; roomSubmit("@Dipper @Atlas @Cypher go");
assert.deepStrictEqual(sent.map(m => [m.name, m.access, m.room]), [["Dipper", "read", true], ["Atlas", "plan", true]]);
assert.strictEqual(JSON.parse(sent[0].text).show, "@Dipper @Atlas @Cypher go");  // first send logs your words once
assert.strictEqual(JSON.parse(sent[1].text).show, "");
assert(roomRun.notes.some(n => /Cypher is at its usage limit/.test(n.text)));

// Not Full access: hand-offs become cards.
const T = roomRun.task;
roomTick();  // first tick: everything already there is history
state.snap.room.push({ t: "10", from: "Dipper", kind: "reply", task: T, text: "@Aaron: check this\nVoice summary: I reviewed it." });
roomTick();
assert.strictEqual(roomRun.cards.length, 1); assert.strictEqual(roomRun.cards[0].to, "Aaron");

// Full access: sent on by itself; a hand-off straight back, or past the turn limit, waits on a card.
sent.length = 0; roomRun.cards = []; roomCfg.access = "full";
state.pending = {}; roomRun.busy.clear();
state.snap.room.push({ t: "11", from: "Atlas", kind: "reply", task: T, text: "@Claude: build it" });
roomTick();
assert.deepStrictEqual(sent.map(m => [m.name, m.access]), [["Claude", "full"]]);
state.snap.room.push({ t: "12", from: "Claude", kind: "reply", task: T, text: "@Atlas: done, check" });
roomTick();
assert.strictEqual(roomRun.cards.pop().why, "Sends the work back");
roomRun.turns[T] = 12; roomRun.busy.clear(); state.pending = {};
state.snap.room.push({ t: "13", from: "Dipper", kind: "reply", task: T, text: "@Aaron: one more" });
roomTick();
assert.strictEqual(roomRun.cards.pop().why, "Turn limit reached");

// An agent's @all never reaches anyone; one reply calling many teammates sends two, the rest wait on cards.
sent.length = 0; roomRun.cards = []; roomRun.turns[T] = 0; roomRun.busy.clear(); state.pending = {}; roomRun.lastFrom = {};
state.snap.room.push({ t: "14", from: "Atlas", kind: "reply", task: T, text: "@all: everyone check in\n@Aaron: a\n@Dipper: b\n@Claude: c\n@Cypher: d" });
roomTick();
assert.deepStrictEqual(sent.map(m => m.name), ["Aaron", "Dipper"]);
assert.deepStrictEqual(roomRun.cards.map(c => [c.to, c.why]), [["Claude", "Calls many teammates at once"], ["Cypher", "Calls many teammates at once"]]);
assert(roomRun.notes.some(n => /Atlas tried to call everyone/.test(n.text)));
roomRun.cards = [];

// Busy agent: the hand-off waits in line and goes when it frees up.
sent.length = 0; roomRun.busy.clear(); state.pending = {};
roomSend("Dipper", "a", "You", "", ["Dipper"]); roomSend("Dipper", "b", "Aaron", "", ["Dipper"]);
assert.strictEqual(sent.length, 1); assert.strictEqual(roomRun.queue.length, 1);
delete state.pending.Dipper; roomSent({ name: "Dipper", ok: true });
assert.strictEqual(sent.length, 2); assert.strictEqual(roomRun.queue.length, 0);

// Done: nothing running, every send answered -> recap in each agent's voice, in order, once.
const now = Date.now();
roomRun.task = "T2"; roomRun.busy.clear(); roomRun.queue = []; roomRun.cards = []; spoken.length = 0;
roomRun.sent = [{ name: "Dipper", t: now, task: "T2" }, { name: "Atlas", t: now, task: "T2" }];
state.snap.room = [{ t: new Date(now + 1000).toISOString(), from: "Dipper", kind: "reply", task: "T2", text: "x\nVoice summary: I wrote tests." },
  { t: new Date(now + 2000).toISOString(), from: "Atlas", kind: "reply", task: "T2", text: "y\nVoice summary: I reviewed them." },
  { t: new Date(now + 3000).toISOString(), from: "Dipper", kind: "reply", task: "T2", text: "z\nVoice summary: I fixed one." }];
roomCheckDone(); roomCheckDone();
assert.deepStrictEqual(spoken, [["Dipper", "Voice summary: I wrote tests. I fixed one."], ["Atlas", "Voice summary: I reviewed them."]]);

// Voices: every agent its own; a pick another agent has swaps the two.
voice.voices = ["a", "b", "c", "d", "e", "f"].map(id => ({ id, name: id }));
settings.voices = { Aaron: "c", Dipper: "c", Ghost: "a", Atlas: "zz" };
assignVoices();
const vs = Object.values(settings.voices);
assert.strictEqual(new Set(vs).size, vs.length); assert.strictEqual(vs.length, 5);
assert.strictEqual(settings.voices.Aaron, "c"); assert(!("Ghost" in settings.voices));
const before = { ...settings.voices };
setAgentVoice("Atlas", before.Aaron);
assert.strictEqual(settings.voices.Atlas, before.Aaron); assert.strictEqual(settings.voices.Aaron, before.Atlas);
console.log("ok");
