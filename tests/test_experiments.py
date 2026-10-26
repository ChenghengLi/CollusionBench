"""scripts/experiments.py: tasks x setups x models make the run configs."""

import sys
from pathlib import Path

import yaml

from collusiongen.runner.config import RunConfig
from collusiongen.runner.plan import expand

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import experiments as ex

SETUPS, MODELS = ex.load_yaml_dir(ex.SETUPS), ex.load_yaml_dir(ex.MODELS)


def _ids(cfg):
    run = RunConfig.model_validate(cfg)
    return {s.episode_id for s in expand(run, run.models[0])}


def test_the_setups_reproduce_the_survey_runs_exactly():
    plain = ex.Task("survey_v1", "survey", "", {}, {"channels": "n4_channels", "dmcap": "n4_dmcap"})
    m = MODELS["k2-3.7b"]
    for sid, legacy in [("channels", "configs/rcp/n4c.yaml"), ("dmcap", "configs/rcp/n4d.yaml")]:
        cfg = ex.config_for(m, m["reps"][0], SETUPS[sid], [plain])
        cfg["run_id"] = f"{m['run_prefix']}_{ex.run_name(SETUPS[sid], plain, m)}"
        assert _ids(cfg) == _ids(yaml.safe_load((ex.ROOT / legacy).read_text()))


def test_adding_a_task_keeps_every_game_already_planned():
    m, s = MODELS["k2-7b"], SETUPS["dmcap"]
    tasks = [t for t in ex.load_tasks() if not ex.is_legacy(m, t)]
    before = _ids(ex.config_for(m, m["reps"][1], s, tasks[:-1]))
    after = _ids(ex.config_for(m, m["reps"][1], s, tasks))
    assert before < after


def test_every_task_is_planned_in_every_setting_and_run():
    m = MODELS["k2-0.9b"]
    tasks = [t for t in ex.load_tasks() if not ex.is_legacy(m, t)]
    cfg = ex.config_for(m, m["reps"][1], SETUPS["channels"], tasks)
    run = RunConfig.model_validate(cfg)
    games = [s for s in expand(run, run.models[0]) if s.condition.value in ex.MODEL_GAMES]
    assert len(games) == len(tasks) * 4 * 3 * 2 * 4  # tasks x settings x sizes x line-ups x runs
    assert {s.instance.params["task"] for s in games} == {t.id for t in tasks}


def test_each_task_has_its_own_run_so_one_task_can_run_alone():
    m, s = MODELS["deepseek-v4.1-flash"], SETUPS["channels"]
    tasks = {t.id: t for t in ex.load_tasks()}
    alone = ex.config_for(m, m["reps"][0], s, [tasks["depot_v1"]])
    assert alone["run_id"] == f"{m['run_prefix']}_n4_depot_v1_channels"
    assert ex.config_path(m, m["reps"][0], s, tasks["depot_v1"]).name == "depot_v1__channels.yaml"
    k2 = MODELS["k2-7b"]
    assert ex.config_path(k2, k2["reps"][1], s, tasks["word_v1"]).parts[-3:] == (
        "rcp7b_repra",
        "tasks",
        "word_v1__channels.yaml",
    )


def test_survey_is_a_task_like_the_others_for_models_that_have_not_played_it():
    tasks = {t.id: t for t in ex.load_tasks()}
    assert tasks["survey_v1"].game == "survey"
    assert ex.is_legacy(MODELS["k2-3.7b"], tasks["survey_v1"])
    assert not ex.is_legacy(MODELS["deepseek-v4.1-flash"], tasks["survey_v1"])
    cfg = ex.config_for(
        MODELS["deepseek-v4.1-flash"],
        MODELS["deepseek-v4.1-flash"]["reps"][0],
        SETUPS["channels"],
        list(tasks.values()),
    )
    assert {m["params_override"]["task"] for m in cfg["modules"]} == set(tasks)
