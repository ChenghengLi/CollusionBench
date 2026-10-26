"""One status table for dept_audit runs: final results for finished games (with the try on which
each correct agent got it right), live counts for games still running, and cost so far.

usage: .venv/bin/python scripts/audit_status.py <model profile>:<scenario>[:<setup>] [...]
"""

import glob
import json
import sys

import yaml

from audit_paths import config_path  # noqa: E402

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")
from audit_progress import SETTING  # noqa: E402
from collusiongen.runner.config import RunConfig  # noqa: E402
from collusiongen.runner.plan import expand  # noqa: E402


def main(args):
    for arg in args:
        model, sc, *rest = arg.split(":")
        setup = rest[0] if rest else "dept_audit"
        cfg = RunConfig.model_validate(yaml.safe_load(open(config_path(model, sc, setup))))
        specs = {s.episode_id: s for s in expand(cfg, cfg.models[0]) if s.condition.value == "MM"}
        R = glob.glob(f"runs/**/{cfg.run_id}/*/results.jsonl", recursive=True)[0].rsplit("/", 1)[0]
        done = {}
        for l in open(f"{R}/results.jsonl"):
            r = json.loads(l)
            if r.get("episode_id") in specs:
                done[r["episode_id"]] = r
        tries = {}
        for l in open(f"{R}/events.jsonl"):
            if '"submit_attempt"' in l:
                e = json.loads(l)
                tries.setdefault((e["episode_id"], e["payload"]["wave"]), []).append(e["payload"].get("n_correct", 0))
        cost, rows = 0.0, []
        for eid, spec in specs.items():
            p = spec.instance.params
            st = SETTING.get((bool(p.get("forum")), bool(p.get("messaging", True)), p.get("max_messages")))
            try:
                steps = [json.loads(l) for l in open(f"{R}/live/{eid}.jsonl").read().splitlines()]
            except FileNotFoundError:
                steps = []
            cost += sum(float((d.get("usage") or {}).get("cost", 0) or 0) for d in steps)
            tools = [(d["applied"] or {}).get("tool") if isinstance(d["applied"], dict) else None for d in steps]
            msgs = tools.count("send_message"); posts = tools.count("forum_post") + tools.count("forum_reply")
            if eid in done:
                sc_ = done[eid]["extra"]["scores"]
                ok = [k for k, v in sc_.items() if v == 1.0]
                how = ", ".join(f"a{k}@try{(tries.get((eid, int(k)), []) + [1]).index(1) + 1}" for k in ok)
                rows.append((p["n_waves"], st, "done", f"{len(ok)}/{p['n_waves']}", how, len(steps), msgs, posts))
            else:
                n_sub = tools.count("submit")
                rows.append((p["n_waves"], st, "running", f"-/{p['n_waves']}", f"{n_sub} submits", len(steps), msgs, posts))
        rows.sort()
        fin = sum(r[2] == "done" for r in rows)
        print(f"\n=== {model} / {sc} ({setup}): {fin}/{len(rows)} games finished, cost so far ${cost:.2f}")
        print(f"  {'n':>2} {'setting':13} {'state':8} {'correct':>7}  {'calls':>5} {'msgs':>4} {'posts':>5}  detail")
        for n, st, state, corr, how, calls, m, po in rows:
            print(f"  {n:>2} {st:13} {state:8} {corr:>7}  {calls:>5} {m:>4} {po:>5}  {how}")


if __name__ == "__main__":
    main(sys.argv[1:])
