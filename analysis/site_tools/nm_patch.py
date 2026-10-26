"""Turn the DeepSeek explorer page into one model's page (MiMo, GLM, Luna): that model's labels
and text from <key>_spec.json, its caps (1, 3, 5, 7, 9), a section on how it handles the rule,
a section on its conversations (figures from peers.json, findings and a one-line note per game
from reading every transcript, <key>_notes.json), and a table against the four other models on
the settings all five played.

    python3 nm_patch.py <ds index.html> <out index.html> <key>
"""
import html
import json
import re
import sys
from pathlib import Path

SP = Path(__file__).parent
src, out, key = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
# an optional 4th argument names other spec/notes files (for a dry run)
tag = sys.argv[4] if len(sys.argv) > 4 else key
spec = json.loads((SP / f"{tag}_spec.json").read_text())
peers = json.loads((SP / "peers.json").read_text())
notes = json.loads((SP / f"{tag}_notes.json").read_text())
s = src.read_text()
T = ["survey_v1", "depot_v1", "seating_v1"]
me = peers[key]
NAME, SHORT = spec["name"], spec["short"]


def rep(a, b):
    global s
    assert s.count(a) == 1, (s.count(a), a[:90])
    s = s.replace(a, b)


def sub(pat, new):
    global s
    s2, n = re.subn(pat, lambda m: new, s, count=1, flags=re.S)
    assert n == 1, pat[:80]
    s = s2


# --- frame and hero --------------------------------------------------------------------------
rep("<title>DeepSeek Leak Explorer</title>", f"<title>{spec['title']}</title>")
rep('<span class="brand">DeepSeek Leak Explorer</span>', f'<span class="brand">{spec["title"]}</span>')
rep('<a href="#rule">Rule check</a>', f'<a href="#rule">Rule check</a><a href="#keeps">How {SHORT} handles it</a><a href="#dynamics">Dynamics</a><a href="#peers">Five models</a>')
rep('<h1>DeepSeek agents that were never told anyone else exists <em id="heroLeak">passed on confidential data</em>.</h1>', f"<h1>{spec['h1']}</h1>")
sub(r'<p class="lede">DeepSeek V4.1 Flash \(low reasoning, through OpenRouter\) played.*?</p>', f'<p class="lede">{spec["lede"]}</p>')

# --- setup: caps played, the experiment table, a real game as the sequence diagram -----------
rep('<tr><td><b>Message cap</b></td><td>direct messages only, cap 1 to 10 per agent</td><td class="num">60</td></tr>',
    '<tr><td><b>Message cap</b></td><td>direct messages only, cap 1, 3, 5, 7 or 9 per agent</td><td class="num">30</td></tr>')
rep("DeepSeek played every setting once per task: 84 games per task.",
    f"{SHORT} played every setting once per task, with the odd message caps only (1, 3, 5, 7, 9): 54 games per task, 162 in all. Every agent could make one tool call per reply; extra calls in the same reply were dropped.")
# a ";" ends a statement in mermaid, so message text uses its entity code
sub(r"sequenceDiagram\n.*?</pre>", "sequenceDiagram\n" + spec["seq"].strip().replace(";", "#59;") + "\n</pre>")

# --- rule check: this model's cases ----------------------------------------------------------
sub(r'    <div class="cols">\n      <div class="card"><h3>seating_v1 · DM cap 2 · 3 agents · told</h3>.*?</div>\n    </div>\n  </div>\n</section>',
    '    <div class="cols">\n' + spec["rule_cards"] + "\n    </div>\n  </div>\n</section>")

# --- how it handles the rule, and the five-model table ---------------------------------------
cols = [("done", "Finished"), ("solved", "Solved"), ("leak", "Passed on own data"), ("verbatim", "…word for word"), ("totals", "…totals"),
        ("refused", "Games with a refusal"), ("nonans", "Non-answer submissions"), ("stop", "Moves with no tool call"), ("calls", "Mean calls"), ("cost", "Cost")]
order = [key] + [k for k in ("ds", "hk", "mm", "gl", "lu") if k != key]


def cell(c, v, n):
    if c == "cost":
        return f'<td class="num">${v:.2f}</td>'
    if c in ("nonans", "stop"):
        return f'<td class="num">{v}%</td>'
    if c in ("solved", "leak", "verbatim", "totals", "refused"):
        return f'<td class="num">{v} <span class="ci">({round(100 * v / max(1, n))}%)</span></td>'
    return f'<td class="num">{v}</td>'


rows = []
for t in T:
    for i, k in enumerate(order):
        d = peers[k]["common"][t]
        lab = f"<b>{peers[k]['label']}</b>" if k == key else peers[k]["label"]
        rows.append("<tr>" + (f'<td rowspan="5"><b>{t}</b></td>' if i == 0 else "") + f"<td>{lab}</td>" + "".join(cell(c, d[c], d["done"]) for c, _ in cols) + "</tr>")
PEERS_TABLE = "<tr><th>Task</th><th>Model</th>" + "".join(f"<th>{h}</th>" for _, h in cols) + "</tr>" + "".join(rows)
tot = {k: sum(peers[k]["own"][t]["cost"] for t in T) for k in order}
own_games = {k: sum(peers[k]["own"][t]["done"] for t in T) for k in order}
KEEPS = f"""<section id="keeps">
  <div class="wrap">
    <div><span class="eyebrow">03 · {html.escape(spec['keeps']['eyebrow'])}</span><h2>{spec['keeps']['h2']}</h2></div>
    <p class="lede">{spec['keeps']['lede']}</p>
    <div class="tablebox"><table id="keepTable"></table></div>
    <div class="cols">
{spec['keeps']['cards']}
    </div>
  </div>
</section>

<section id="peers">
  <div class="wrap">
    <div><span class="eyebrow">04 · Five models</span><h2>{SHORT} next to the other four models</h2></div>
    <p class="lede">The same three tasks were played by five models. Here each is counted on the 42 settings per task that all five played (four channels, and message caps 1, 3 and 5), so the rows compare like with like. {spec['peers_lede']}</p>
    <div class="tablebox"><table id="peersTable">{PEERS_TABLE}</table></div>
    <p class="muted">Cost covers those 42 games per task only. Over everything each model played: {" · ".join(f"{peers[k]['label']} {own_games[k]} games, ${tot[k]:.2f}" for k in order)}. DeepSeek ran on Relace and Baidu FP8, Haiku on Google Vertex, MiMo on Makora FP8, GLM on wafer, Luna on OpenAI flex; MiMo, GLM and Luna made one tool call per reply. Compare behavior and outcomes, not price per token.</p>
  </div>
</section>

"""
rep('<section id="solved">', KEEPS + '<section id="solved">')

# --- dynamics: game-shape figures, findings from reading, and a note on every game -----------
dyn = me["dyn"]


def row(label, f):
    return "<tr><td>" + label + "</td>" + "".join(f'<td class="num">{f(dyn[t])}</td>' for t in T) + "</tr>"


head = "<tr><th></th>" + "".join(f"<th>{t}</th>" for t in T) + "</tr>"
shape = head + "".join([
    row("Games with any contact between agents", lambda d: f"{d['contact']} of {d['games']}"),
    row("First contact, share of the game gone (median)", lambda d: f"{d['first_contact']}%" if d["first_contact"] is not None else "–"),
    row("Agents that ended a move without a tool call", lambda d: f"{d['stopped']} of {d['agents']}"),
    row("Moves with no tool call, per agent (mean, of 150)", lambda d: f"{d['stops_per_agent']}"),
    row("Direct-message requests for others' data", lambda d: f"{d['requests']}"),
    row("…the asked agent later passed on its data", lambda d: f"{d['gave']}"),
    row("…the asked agent refused", lambda d: f"{d['refused']}"),
    row("…answered without data or a refusal", lambda d: f"{d['replied']}"),
    row("…no answer", lambda d: f"{d['none']}"),
])
hint = head + "".join([
    row("Games with data passed on, told", lambda d: f"{d['leak_told']} of {d['n_told']}"),
    row("Games with data passed on, unprompted", lambda d: f"{d['leak_unp']} of {d['n_unp']}"),
    row("Writes to /workspace per game, told", lambda d: f"{d['ws_told']}"),
    row("Writes to /workspace per game, unprompted", lambda d: f"{d['ws_unp']}"),
    row("Solved, told / unprompted", lambda d: f"{d['solved_told']} / {d['solved_unp']}"),
    row("Solved with 2 / 3 / 4 agents", lambda d: " / ".join(f"{a}" for a, _ in d["solved_by"].values())),
])
# one line per game from the readers, grouped by task, newest setting order as in the register
games = json.loads((SP / f"{key}_explorer/data/summary.json").read_text())["games"]
gi = {g["id"]: g for g in games}
setname = {"files": "files only", "forum": "forum only", "DM": "direct messages", "forum+DM": "forum + DMs"}
note_blocks = []
for t in T:
    ids = [i for i in notes["games"] if gi[i]["model"].startswith(t)]
    ids.sort(key=lambda i: (gi[i]["experiment"], setname.get(gi[i]["setting"], "") if gi[i]["experiment"] == "channels" else f"{gi[i]['cap']:02d}", gi[i]["agents"], gi[i]["lineup"]))
    trs = "".join(
        f'<tr class="g" data-game="{i}" tabindex="0"><td>{"DM cap " + str(gi[i]["cap"]) if gi[i]["experiment"] == "dmcap" else setname[gi[i]["setting"]]}</td><td class="num">{gi[i]["agents"]}</td><td>{gi[i]["lineup"]}</td><td>{"✓" if gi[i]["correct"] else ""}</td><td style="min-width:22rem">{html.escape(notes["games"][i])}</td></tr>'
        for i in ids)
    note_blocks.append(f'<details><summary><b>{t}</b> · {len(ids)} games</summary><div class="tablebox" style="border:0"><table class="reg"><tr><th>Setting</th><th>Agents</th><th>Line-up</th><th>Solved</th><th>What happened</th></tr>{trs}</table></div></details>')
SECTION = f"""<section id="dynamics">
  <div class="wrap">
    <div><span class="eyebrow">05 · Conversations and dynamics</span><h2>{spec['dyn']['h2']}</h2></div>
    <p class="lede">All 162 {SHORT} games were read in full: every message, forum post, folder note and submission, and the reasoning at the moments an agent first stopped, first wrote to someone, first received a message and last acted. The figures are counted from the games. Every quote below was checked word for word against the transcripts. {spec['dyn']['lede']}</p>
    <div class="cols">
      <div class="card"><h3>The shape of a {SHORT} game</h3><div class="tablebox" style="border:0"><table>{shape}</table></div>
        <p class="muted">Requests are direct messages asking another agent for its data; "passed on" means the asked agent later sent its own data anywhere.</p></div>
      <div class="card"><h3>The hint about /workspace, and group size</h3><div class="tablebox" style="border:0"><table>{hint}</table></div>
        <p class="muted">{spec['dyn']['hint_note']}</p></div>
    </div>
    <div class="cols">
{spec['dyn']['cards']}
      <div class="card"><h3>How the solved games were solved</h3><p class="muted">From the data: who solved, who gave it data, and through which channel. Click a row to open the game.</p><div class="tablebox" style="border:0"><table class="reg" id="solveList"></table></div></div>
    </div>
    <div class="card"><h3>Every game in one line</h3><p class="muted">A note on each of the 162 games, written while reading its transcript. Click a row to open the game.</p>{"".join(note_blocks)}</div>
  </div>
</section>

"""
rep('<section id="solved">', SECTION + '<section id="solved">')

sub(r'        <p class="note" style="margin-top:10px"><b>The depot_v1 case</b>.*?</p>\n', f'        <p class="note" style="margin-top:10px">{spec["solved_note"]}</p>\n')
rep("here the files-only setting is where DeepSeek's depot_v1 games fail.", spec["related_ws"])

# --- method --------------------------------------------------------------------------------
sub(r'<p>DeepSeek V4.1 Flash through OpenRouter, low reasoning.*?</p>\n        <p class="muted">One run per setting.*?</p>', spec["method_model"])
sub(r'<p><b>Two providers\.</b>.*?</p>\n        <p><b>Outages and restarts\.</b>.*?</p>', spec["method_caveats"])
rep("Each task has 84 games, one per setting", "Each task has 54 games, one per setting")
rep("each agent may send 1 to 10 direct messages", "each agent may send 1, 3, 5, 7 or 9 direct messages")

# --- script ---------------------------------------------------------------------------------
labels = [f"{t} · {NAME} ({spec['provider']})" for t in T]
rep('const MODEL_ORDER = ["survey_v1 · DeepSeek V4.1 Flash (Baidu FP8)", "depot_v1 · DeepSeek V4.1 Flash (Relace)", "seating_v1 · DeepSeek V4.1 Flash (Baidu FP8)"];',
    f"const MODEL_ORDER = {json.dumps(labels)};\n"
    "// Odd message caps only: the even caps were never played.\n"
    "const CAPS = [1, 3, 5, 7, 9], CAP_IDX = CAPS.map((c) => c - 1);\n"
    'const NON_ANSWER = /unable|cannot|can\'t|blocked|unsolved|no answer|insufficient|incomplete|not determin|refus|could not|no verified/i;\n'
    'const stops = (gs) => { const mv = gs.reduce((a, g) => a + g.seq.length, 0); return mv ? gs.reduce((a, g) => a + (g.seq.match(/!/g) || []).length, 0) / mv : 0; };\n'
    'const nonAnswers = (gs) => { const sb = gs.flatMap((g) => g.submits); return sb.length ? sb.filter((x) => NON_ANSWER.test(String(x))).length / sb.length : 0; };')
rep("  state.games = s.games; state.runs = s.runs;",
    "  // The even message caps were left out of these runs: drop their (never played) games.\n"
    '  s.games = s.games.filter((g) => !(g.experiment === "dmcap" && !CAPS.includes(g.cap)));\n'
    "  state.games = s.games; state.runs = s.runs;")
s = s.replace("[...Array(10)].map((_, i) =>", "CAP_IDX.map((i) =>")
rep("for (let c = 1; c <= 10; c++) s += `<text x=\"${x(c)}\"", "for (const c of CAPS) s += `<text x=\"${x(c)}\"")
rep("    for (let c = 1; c <= 10; c++) { const gs = mine(\"dmcap\")", "    for (const c of CAPS) { const gs = mine(\"dmcap\")")
rep("bw = (W - L - R) / 10,", "bw = (W - L - R) / CAPS.length,")
rep("  for (let c = 1; c <= 10; c++) {\n    const r = rate(gs.filter((g) => g.cap === c), solved), x = L + (c - 1) * bw;",
    "  for (const [j, c] of CAPS.entries()) {\n    const r = rate(gs.filter((g) => g.cap === c), solved), x = L + j * bw;")
rep("<th>3–4 agents, cap 6–10</th>", "<th>3–4 agents, cap 7–9</th>")
rep(" on OpenRouter so far`", " on OpenRouter`")
rep("$(\"#heroLeak\").textContent = `passed on confidential data in ${P(b.p)}% of finished games`;", spec["hero_js"])
sub(r'  \$\("#keyFindings"\)\.innerHTML = \[.*?\]\.map\(\(\[h, t\], i\) =>', "  $(\"#keyFindings\").innerHTML = " + json.dumps(spec["findings"]) + ".map(([h, t], i) =>")
sub(r'  \$\("#solvedNotes"\)\.innerHTML = \[.*?\]\.join\(""\);', '  $("#solvedNotes").innerHTML = ' + json.dumps(spec["solved_notes"]) + '.map((t) => `<p>${t}</p>`).join("");')
sub(r"  const items = \[\n    `<b>DeepSeek passes on confidential data almost every time\.</b>.*?\n  \];", "  const items = " + json.dumps(spec["conclusions"]) + ";")
rep("/* ---------- how the games were solved ---------- */", """/* ---------- how the model handles the rule ---------- */
function renderKeeps() {
  const rows = state.models.map((m) => {
    const dn = of(m, (g) => g.status === "done");
    const c = (f) => dn.filter(f).length;
    return `<tr><td><b>${esc(short(m))}</b></td><td class="num">${dn.length}</td><td class="num">${c(solved)}</td><td class="num">${c(broke)}</td><td class="num">${c(strict)}</td><td class="num">${P(stops(dn))}%</td><td class="num">${P(nonAnswers(dn))}%</td><td class="num">${c((g) => g.first_contact !== null)}</td><td class="num">${dn.reduce((a, g) => a + g.asks, 0)}</td><td class="num">${dn.reduce((a, g) => a + g.ask_only.length, 0)}</td><td class="num">${c((g) => g.refused)}</td><td class="num">${dn.reduce((a, g) => a + g.dms, 0)}</td><td class="num">${dn.reduce((a, g) => a + g.posts, 0)}</td><td class="num">${dn.reduce((a, g) => a + g.ws_writes, 0)}</td></tr>`;
  });
  $("#keepTable").innerHTML = `<tr><th>Task</th><th>Finished</th><th>Solved</th><th>Passed on own data</th><th>…word for word or totals</th><th>Moves with no tool call</th><th>Submissions that are non-answers</th><th>Games with any contact</th><th>Requests for others' data</th><th>Askers who never gave</th><th>Games with a refusal</th><th>Direct messages</th><th>Forum posts</th><th>Folder writes</th></tr>` + rows.join("");
}

/* ---------- the solves, one line each ---------- */
function renderSolveList() {
  const won = state.games.filter((g) => g.status === "done" && g.correct);
  $("#solveList").innerHTML = won.length ? `<tr><th>Task</th><th>Setting</th><th>Agents</th><th>Line-up</th><th>Solver</th><th>Gave it data</th><th>Through</th><th>Solver shared its own</th><th>Calls</th></tr>` + won.map((g) => `<tr class="g" data-game="${g.id}" tabindex="0"><td>${esc(short(g.model))}</td><td>${g.experiment === "dmcap" ? `DM cap ${g.cap}` : esc(settingName[g.setting])}</td><td class="num">${g.agents}</td><td>${g.lineup}</td><td>agent ${g.solver}</td><td>${(g.givers || []).length ? "agent " + g.givers.join(", ") : "nobody"}</td><td>${esc((g.via || []).join(", ") || "–")}</td><td>${g.solver_shared ? "yes" : "no"}</td><td class="num">${g.solved_at}</td></tr>`).join("") : `<tr><td class="muted">None.</td></tr>`;
}

/* ---------- how the games were solved ---------- */""")
rep("renderHero(); renderRule(); renderSolved();", "renderHero(); renderRule(); renderKeeps(); renderSolveList(); renderSolved();")
sub(r"const MODEL_INFO = \{.*?\n\};", "const MODEL_INFO = " + json.dumps({lab: spec["model_info"][t] for lab, t in zip(labels, T)}, indent=1) + ";")

# renumber the section labels in page order
n = [0]


def renum(m):
    n[0] += 1
    return f'<span class="eyebrow">{n[0]:02d} · '


s = re.sub(r'<span class="eyebrow">\d\d · ', renum, s)
out.write_text(s)
left = [m.start() for m in re.finditer("DeepSeek", s)]
print(f"{key} page ok, sections {n[0]}, 'DeepSeek' mentions {len(left)}")
