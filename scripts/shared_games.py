"""One row per shared-goal game (running or finished): calls, channel use, submissions, the leak
monitor's labels applied live to every item sent so far, and the result when finished.

usage: .venv/bin/python scripts/shared_games.py <setup> <model profile>:<scenario> [...]
"""

import collections
import glob
import json
import sys

import yaml

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")
from audit_paths import config_path  # noqa: E402
from audit_progress import SETTING  # noqa: E402
from collusiongen.modules.n4_relay.games import game_for  # noqa: E402
from collusiongen.runner.config import RunConfig  # noqa: E402
from collusiongen.runner.plan import expand  # noqa: E402

ORDER = ("folder", "folder_msg5", "folder_forum", "all")
SHORT = {"deepseek-v4.1-flash-baidu": "DeepSeek", "mimo-v2.6-flash-cap1": "MiMo", "gpt-6.1-sol": "Sol",
         "glm-5.3-flash-wafer": "GLM", "gpt-6-luna-flex": "Luna"}


def main(setup, pairs):
    print(f"{'model':8} {'scenario':12} {'setting':13} {'state':8} {'calls':>9} {'msg':>4} {'post':>4} {'file':>4} "
          f"{'sub':>4}  {'leaks (agents)':16} {'req':>3} {'ref':>3}  result")
    for pair in pairs:
        model, sc = pair.rsplit(":", 1)
        cross = model.startswith("cross")  # cross:<tag> = a cross-model run (scripts/cross_model.py)
        lead = "deepseek-v4.1-flash-baidu" if cross else model
        cfg = RunConfig.model_validate(yaml.safe_load(open(config_path(lead, sc, setup))))
        specs = {s.episode_id: s for s in expand(cfg, cfg.models[0]) if s.condition.value == "MM"}
        base = (glob.glob(f"runs/api/cross_{model.split(':')[-1] if ':' in model else model[6:]}_{sc}_v1_{setup}/*/live")
                if cross else glob.glob(f"runs/**/{cfg.run_id}/*/live", recursive=True))
        if not base:
            print(f"{SHORT.get(model, model):8} {sc[7:]:12} (not started)"); continue
        base = base[0].rsplit("/", 1)[0]
        rp = f"{base}/results.jsonl"
        results = {json.loads(l)["episode_id"]: json.loads(l) for l in open(rp)} if glob.os.path.exists(rp) else {}
        rows = {}
        for eid, spec in specs.items():
            p = spec.instance.params
            st = SETTING.get((bool(p.get("forum")), bool(p.get("messaging", True)), p.get("max_messages")))
            g = game_for(spec.instance)
            try:
                steps = [json.loads(l) for l in open(f"{base}/live/{eid}.jsonl").read().splitlines()]
            except FileNotFoundError:
                steps = []
            c = collections.Counter()
            leak_kinds, req = collections.Counter(), 0
            for d in steps:
                a = d["applied"] if isinstance(d["applied"], dict) else {}
                t = a.get("tool"); text = None
                if t == "send_message":
                    c["msg"] += 1; text = a.get("text", "")
                elif t in ("forum_post", "forum_reply"):
                    c["post"] += 1; text = f"{a.get('title', '')} {a.get('text', '')}"
                elif t in ("write", "append") and str(a.get("path", "")).startswith("/workspace"):
                    c["file"] += 1; text = a.get("content", "")
                elif t == "submit":
                    c["sub"] += 1
                if text:
                    # the live log does not say which agent sent it: screen against every unit, keep hits
                    labs = [g.screen(k, text) for k in range(1, g.n + 1)]
                    for k, lab in enumerate(labs, start=1):
                        for kind in ("records", "fact", "amounts", "procedure"):
                            if lab.get(kind):
                                leak_kinds[(kind, g.RING[k - 1].key)] += 1
                    req += bool(labs[0].get("request"))
                    c["refusal"] += bool(labs[0].get("refusal"))
            units = {u for _, u in leak_kinds}
            kinds = collections.Counter(k for k, _ in leak_kinds)
            leak_txt = (",".join(f"{k}{v}" for k, v in kinds.items()) + f" ({len(units)})") if kinds else "-"
            if eid in results:
                sec = results[eid]["secondary"]
                res = f"team solved {'YES' if sec.get('team_solved') else 'no'}"
                if "leak_any" in sec:
                    res += f" | monitor: leak {int(sec['leak_any'])}, joint {int(sec.get('leak_joint', 0))}"
                state = "done"
            else:
                res, state = "", "running"
            rows[st] = (state, len(steps), g.n * 150, c, leak_txt, req, res)
        for st in ORDER:
            if st not in rows:
                continue
            state, calls, cap, c, leak_txt, req, res = rows[st]
            print(f"{('cross' if cross else SHORT.get(model, model)):8} {sc[7:]:12} {st:13} {state:8} {calls:>4}/{cap:<4} {c['msg']:>4} "
                  f"{c['post']:>4} {c['file']:>4} {c['sub']:>4}  {leak_txt:16} {req:>3} {c['refusal']:>3}  {res}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
