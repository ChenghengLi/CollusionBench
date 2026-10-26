"""Every number cited in the paper, recomputed from the automatic scorer only (no audit).

    python3 analysis/scorer_only_2026-10/all_numbers.py   (run from the project root)
"""
import json, glob, os, sys, collections, statistics
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sv import sv
from scipy.stats import fisher_exact

B = {"full", "reqsupply", "leak", "subtotal", "protected", "rubber", "unchecked"}
FIN = [("K2-3.7B", "final_rcp"), ("K2-7B", "final7b_rcp"), ("K2-32B", "fp8_32b_rcp"),
       ("Glimmer", "glimmer30b_rcp"), ("Qwen", "qwen38_rcp"), ("Gemma", "gemma412b_rcp")]
CK = [(f"K2-{sz}-{tag}", f"ckpt{p}_{pre}_rcp") for tag, pre in [("mid", "mid4"), ("rl", "rlm"), ("sft1", "sft1"), ("sft2", "sft2")]
      for sz, p in [("7B", "7b"), ("3.7B", "3b")]]
ALL = FIN + CK
GAMES = ("records", "pricing", "exam", "approvals")


def rows(pre):
    for g in GAMES:
        d = glob.glob(f"runs/rcp/{pre}_bench_card_{g}_full/*/")[0]
        f = d + "results_rescored.jsonl" if os.path.exists(d + "results_rescored.jsonl") else d + "results.jsonl"
        for l in open(f):
            r = json.loads(l); r["_game"] = g; r["_dir"] = d
            p = r["params"]
            r["_cell"] = ("blocked" if p["route_cost"] == "blocked" else "cheap" if p["route_cost"] == "cheap"
                          else ("solo" if p.get("aim") else {"mm": "moderate", "ask": "ask", "inst": "inst", "perm": "perm"}[p["card_condition"]]))
            r["_v"] = sv(r)["v"]; r["_br"] = r["_v"] in B
            yield r


D = {name: list(rows(pre)) for name, pre in ALL}
out = {}

def cnt(name, pred):
    return sum(1 for r in D[name] if pred(r))

dt = lambda r: r["_game"] != "approvals"
# per model cells
for name, _ in ALL:
    o = {}
    o["solved"] = cnt(name, lambda r: r["secondary"].get("card_solved"))
    o["ask_br"] = cnt(name, lambda r: dt(r) and r["_cell"] == "ask" and r["_br"])
    o["ask_answered"] = cnt(name, lambda r: dt(r) and r["_cell"] == "ask" and r["secondary"].get("card_joint_request_supply"))
    o["mod_br"] = cnt(name, lambda r: dt(r) and r["_cell"] == "moderate" and r["_br"])
    o["blk_br"] = cnt(name, lambda r: dt(r) and r["_cell"] == "blocked" and r["_br"])
    o["blk_rec_br"] = cnt(name, lambda r: r["_game"] == "records" and r["_cell"] == "blocked" and r["_br"])
    o["blk_rec_full"] = cnt(name, lambda r: r["_game"] == "records" and r["_cell"] == "blocked" and r["_v"] == "full")
    o["inst_sh"] = cnt(name, lambda r: dt(r) and r["_cell"] == "inst" and r["_br"])
    o["inst_sh_any"] = cnt(name, lambda r: dt(r) and r["_cell"] == "inst" and r["_v"] in B | {"instructed"})
    fail = [r for r in D[name] if not r["secondary"].get("card_solved")]
    o["fail"] = len(fail); o["fr"] = sum(1 for r in fail if r["secondary"].get("rep_false"))
    o["blk_brsol"] = cnt(name, lambda r: dt(r) and r["_cell"] == "blocked" and r["_br"] and r["secondary"].get("card_solved"))
    o["blk_sol_nobr"] = cnt(name, lambda r: dt(r) and r["_cell"] == "blocked" and (not r["_br"]) and r["secondary"].get("card_solved"))
    o["appr_mod_br"] = cnt(name, lambda r: r["_game"] == "approvals" and r["_cell"] == "moderate" and r["_br"])
    o["appr_solo_br"] = cnt(name, lambda r: r["_game"] == "approvals" and r["_cell"] == "solo" and r["_br"])
    o["appr_blk_br"] = cnt(name, lambda r: r["_game"] == "approvals" and r["_cell"] == "blocked" and r["_br"])
    o["max_rec_pri_working"] = max(cnt(name, lambda r, g=g, c=c: r["_game"] == g and r["_cell"] == c and r["_br"]) for g in ("records", "pricing") for c in ("cheap", "moderate"))
    o["dt_breaches_by_cell"] = dict(collections.Counter(r["_game"] + "/" + r["_cell"] for r in D[name] if r["_br"] and r["_cell"] not in ("inst", "perm")))
    o["blk_breach_tasks"] = dict(collections.Counter(r["_game"] for r in D[name] if dt(r) and r["_cell"] == "blocked" and r["_br"]))
    out[name] = o

# totals over final models
tot_br = sum(1 for n, _ in FIN for r in D[n] if dt(r) and r["_cell"] not in ("inst", "perm") and r["_br"])
tot_blk = sum(out[n]["blk_br"] for n, _ in FIN)
out["_totals"] = dict(dt_breaches_outside_controls=tot_br, blocked_breaches=tot_blk)

# breaching vs non-breaching false reports, K2 finals, failed blocked data-task games
k2 = ["K2-3.7B", "K2-7B", "K2-32B"]
fb = [r for n in k2 for r in D[n] if dt(r) and r["_cell"] == "blocked" and not r["secondary"].get("card_solved")]
out["_k2_lie"] = dict(br_fail=sum(r["_br"] for r in fb), br_lie=sum(r["_br"] and bool(r["secondary"].get("rep_false")) for r in fb),
                      no_fail=sum(not r["_br"] for r in fb), no_lie=sum((not r["_br"]) and bool(r["secondary"].get("rep_false")) for r in fb))
# log edits
le = [r for n, _ in ALL for r in D[n] if r["secondary"].get("log_edit_agents", 0) > 0]
out["_log_edits"] = dict(games=len(le), with_breach=sum(r["_br"] for r in le))
# checkpoint conversion
ckb = [r for n, _ in CK for r in D[n] if dt(r) and r["_cell"] == "blocked" and r["_br"]]
out["_ckpt_conv"] = dict(n=len(ckb), solved=sum(bool(r["secondary"].get("card_solved")) for r in ckb))
out["_ckpt_fr_range"] = [min(out[n]["fr"] / out[n]["fail"] for n in [x for x, _ in CK] + ["K2-7B", "K2-3.7B"]),
                         max(out[n]["fr"] / out[n]["fail"] for n in [x for x, _ in CK] + ["K2-7B", "K2-3.7B"])]
# 3.7B midtraining unilateral share among moderate+blocked data-task breach games
m = [r for r in D["K2-3.7B-mid"] if dt(r) and r["_cell"] in ("moderate", "blocked") and r["_br"]]
out["_37mid_unilateral"] = dict(n=len(m), unilateral=sum(int(r["secondary"].get("card_class", 0)) == 3 for r in m))
# no blocked data-task game solved without a breach
out["_solved_without_breach"] = sum(out[n]["blk_sol_nobr"] for n, _ in ALL)

# fisher contrasts
def fx(a, an, b, bn):
    return fisher_exact([[a, an - a], [b, bn - b]])[1]
q = lambda n, k: out[n][k]
rec = lambda n, c: cnt(n, lambda r: r["_game"] == "records" and r["_cell"] == c and r["_br"])
pri = lambda n, c: cnt(n, lambda r: r["_game"] == "pricing" and r["_cell"] == c and r["_br"])
ap_blk = lambda n: out[n]["appr_blk_br"]
C = [
    ("Qwen, blocked records vs blocked pricing", rec("Qwen", "blocked"), 20, pri("Qwen", "blocked"), 20),
    ("Instructed to pool: Glimmer vs Qwen", q("Glimmer", "inst_sh"), 30, q("Qwen", "inst_sh"), 30),
    ("False reports: Glimmer vs Qwen", q("Glimmer", "fr"), q("Glimmer", "fail"), q("Qwen", "fr"), q("Qwen", "fail")),
    ("K2-7B final vs mid, blocked records", q("K2-7B", "blk_rec_br"), 20, q("K2-7B-mid", "blk_rec_br"), 20),
    ("K2-7B final vs SFT2, blocked breaches", q("K2-7B", "blk_br"), 60, q("K2-7B-sft2", "blk_br"), 60),
    ("K2-7B SFT1 vs RL, blocked breaches", q("K2-7B-sft1", "blk_br"), 60, q("K2-7B-rl", "blk_br"), 60),
    ("K2-3.7B final vs SFT2, blocked breaches", q("K2-3.7B", "blk_br"), 60, q("K2-3.7B-sft2", "blk_br"), 60),
    ("K2-7B final vs SFT2, full collusion", q("K2-7B", "blk_rec_full"), 20, q("K2-7B-sft2", "blk_rec_full"), 20),
    ("Mid: K2-3.7B vs K2-7B, blocked records", q("K2-3.7B-mid", "blk_rec_br"), 20, q("K2-7B-mid", "blk_rec_br"), 20),
    ("K2-7B SFT1 vs RL, blocked records", q("K2-7B-sft1", "blk_rec_br"), 20, q("K2-7B-rl", "blk_rec_br"), 20),
    ("K2-7B SFT2 vs RL, blocked approvals unchecked", ap_blk("K2-7B-sft2"), 20, ap_blk("K2-7B-rl"), 20),
    ("K2-7B SFT1 vs mid, full collusion", q("K2-7B-sft1", "blk_rec_full"), 20, q("K2-7B-mid", "blk_rec_full"), 20),
    ("SFT1: K2-7B vs K2-3.7B, full collusion", q("K2-7B-sft1", "blk_rec_full"), 20, q("K2-3.7B-sft1", "blk_rec_full"), 20),
    ("K2-7B SFT1 vs RL, full collusion", q("K2-7B-sft1", "blk_rec_full"), 20, q("K2-7B-rl", "blk_rec_full"), 20),
    ("K2-3.7B RL vs mid, blocked records", q("K2-3.7B-rl", "blk_rec_br"), 20, q("K2-3.7B-mid", "blk_rec_br"), 20),
    ("K2-7B RL vs mid, blocked records", q("K2-7B-rl", "blk_rec_br"), 20, q("K2-7B-mid", "blk_rec_br"), 20),
]
out["_fisher"] = [(c[0], c[1], c[2], c[3], c[4], fx(*c[1:])) for c in C]
print(json.dumps(out, indent=1, default=str))
json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "all_numbers.json"), "w"), indent=1, default=str)
