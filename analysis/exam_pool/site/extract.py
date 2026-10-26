"""Data for the exam-setup page: one generated company (files, questions, owners), the rendered
prompts of each setup, and the results so far."""
import json, sys, os, collections
ROOT = "/Users/chenghengli/Desktop/semester_project"
sys.path.insert(0, ROOT + "/src"); sys.path.insert(0, ROOT + "/scripts")
import yaml
import experiments as ex
from collusiongen.runner.config import RunConfig
from collusiongen.runner.plan import expand
from collusiongen.runner.experiment import skipped
from collusiongen.core.registry import get_module
from collusiongen.core.types import Variant
from collusiongen.core.log import EventLog
from collusiongen.core.env import Services
from collusiongen.modules.n4_relay.exam import ExamGame
os.chdir(ROOT)
mod = get_module("n4_relay")
tasks = {t.id: t for t in ex.load_tasks()}
setups, models = ex.load_yaml_dir(ex.SETUPS), ex.load_yaml_dir(ex.MODELS)
sol = models["gpt-6.1-sol"]

def specs(setup_id, model=sol):
    run = RunConfig.model_validate(ex.config_for(model, model["reps"][0], setups[setup_id], [tasks["exam_v1"]]))
    return [s for s in expand(run, run.models[0]) if not skipped(run, s) and s.condition.value == "MM"]

def render(spec):
    env = mod.make_env(spec.instance, Variant(protocol="native_tools"), EventLog("x"), Services())
    obs = env.observe(env.next_seat())
    w = env.workers[0]
    tools = [{"name": t["function"]["name"], "args": list(t["function"]["parameters"].get("properties", {})),
              "desc": t["function"]["description"]} for t in obs.action_space.tools()]
    info = {p: env._run_tool(w, {"tool": "read", "path": p}) for p in ("/data/.info", "/workspace/.info", "/tmp/.info")}
    return {"system": obs.system, "first": obs.prompt, "info": info, "tools": tools, "budget": env.budget}

prompts = {}
pick = lambda sid, lvl, rule, n: next(s for s in specs(sid) if s.instance.params["exam_level"] == lvl
                                      and s.instance.params["rule_style"] == rule and s.instance.params["n_waves"] == n)
prompts["easy_L0"] = render(pick("exam", "easy", "personal", 3))
prompts["hard_L0"] = render(pick("exam", "hard", "personal", 3))
prompts["hard_L1"] = render(pick("exam", "hard", "semantic", 3))
prompts["very_hard_L0"] = render(pick("exam", "very_hard", "personal", 3))
split_spec = next(s for s in specs("exam_split") if s.instance.params["n_waves"] == 3)
prompts["split_L0"] = render(split_spec)

game = ExamGame(split_spec.instance)
files = game.files()
questions = [{"id": q.id, "template": q.template, "text": q.text, "answer": q.answer, "files": list(q.files)}
             for q in game.questions]
owners = {str(n): game.owners(n) for n in (2, 3, 4)}
# budgets/solo per level from a game of each level
levels = {}
for lvl in ("easy", "hard", "very_hard"):
    g = ExamGame(pick("exam", lvl, "personal", 3).instance)
    levels[lvl] = {"budget": g.budget(), "honest": g.honest_target(), "max_solo": g.max_solo(),
                   "solo_all": g.solo_cost(g.questions)}
levels["split"] = {"budget": game.budget(), "honest": 0, "max_solo": 0, "solo_all": None}

def results(model_id, setup_id):
    model = models[model_id]
    run_dir = f"runs/api/{model['run_prefix']}_n4_exam_v1_{setup_id}"
    out = []
    path = None
    for p in (run_dir,):
        for f in __import__("glob").glob(p + "/*/results.jsonl"):
            path = f
    if not path:
        return out
    for l in open(path):
        d = json.loads(l)
        if d["condition"] != "MM": continue
        x, p = d["extra"], d["params"]
        out.append({"level": p["exam_level"], "rule": p["rule_style"], "n": p["n_waves"], "run": d["episode"] + 1,
                    "scores": [round(v * 12) for _, v in sorted(x["scores"].items(), key=lambda kv: int(kv[0]))],
                    "honest": x["honest_target"], "unearned": sum(x["unearned"].values()),
                    "notes": d["secondary"].get("leave_rate", 0) > 0, "calls": d["steps"]})
    return out

data = {"files": files, "questions": questions, "owners": owners, "prompts": prompts, "levels": levels,
        "results": {"deepseek_pilot": results("deepseek-v4.1-flash-baidu", "exam"),
                    "sol_hard": results("gpt-6.1-sol", "exam_hard")},
        "project": split_spec.instance.skin["project"]}
json.dump(data, open(sys.argv[1], "w"), ensure_ascii=False)
print("files", len(files), "| deepseek", len(data["results"]["deepseek_pilot"]), "| sol", len(data["results"]["sol_hard"]),
      "| levels", levels, "| size", os.path.getsize(sys.argv[1]))
