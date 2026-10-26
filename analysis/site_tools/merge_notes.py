"""Merge the readers' part notes for one model into <key>_notes.json and re-check every quote
against the full digests. Prints coverage and any quote that is not found word for word.

    python3 merge_notes.py <key>
"""
import glob, json, sys
SP = "/private/tmp/claude-501/-Users-chenghengli-Desktop-semester-project/cf8e5b8d-1387-44e3-b034-6824de9e85b8/scratchpad"
key = sys.argv[1]
full = {t: open(f"{SP}/{key}_digest/{t}.txt").read() for t in ("survey_v1", "depot_v1", "seating_v1")}
out = {"games": {}, "tasks": {}}
bad = 0
for f in sorted(glob.glob(f"{SP}/{key}_notes/*.json")):
    part = f.split("/")[-1][:-5]
    t = part.rsplit("_p", 1)[0]
    d = json.load(open(f))
    out["games"].update(d["games"])
    for p in d.get("patterns", []):
        ok = [q for q in p.get("quotes", []) if q["text"] in full[t]]
        bad += len(p.get("quotes", [])) - len(ok)
        p["quotes"] = ok
    d["odd"] = [q for q in d.get("odd", []) if q["text"] in full[t] or not print("  bad odd quote", q["text"][:60])]
    out["tasks"].setdefault(t, []).append({"part": part, **{k: d.get(k) for k in ("patterns", "how_solved", "why_failed", "rule_reasoning", "odd")}})
ids = {l.split(" | ")[0][9:] for t in full.values() for l in t.splitlines() if l.startswith("=== GAME ")}
print(key, "games noted", len(out["games"]), "of", len(ids), "| missing", len(ids - set(out["games"])), "| extra", len(set(out["games"]) - ids), "| dropped pattern quotes", bad)
json.dump(out, open(f"{SP}/{key}_notes.json", "w"), indent=1)
