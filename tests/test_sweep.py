"""Sweep planning: one model entry per checkpoint, identical games, resumable completion."""

from collusiongen.runner.config import RunConfig
from collusiongen.runner.plan import expand
from collusiongen.runner.sweep import SweepConfig, build_run_config, dry_run, tag_complete


def sweep(tmp_path, tags=("pretrain_100000", "mid_4_10000", "anti_doom_loop_verified")):
    return SweepConfig.model_validate(
        {
            "sweep_id": "s",
            "repo": "IFM/K2-Horizon-3.7B",
            "revisions_file": "configs/revisions_3p7b.yaml",
            "served_prefix": "k@",
            "tags": list(tags),
            "output_dir": str(tmp_path),
            "modules": [
                {
                    "id": "a1_pricing",
                    "n_instances": 2,
                    "paraphrases": [0],
                    "episodes_per_instance": 1,
                    "instructed": False,
                    "params_override": {"horizon": 3},
                },
                {
                    "id": "a2_verify",
                    "n_instances": 2,
                    "paraphrases": [0],
                    "episodes_per_instance": 1,
                    "instructed": False,
                },
            ],
        }
    )


def test_models_follow_tags_with_pinned_revisions(tmp_path):
    cfg = build_run_config(sweep(tmp_path))
    assert [m.tag for m in cfg.models] == [
        "pretrain_100000",
        "mid_4_10000",
        "anti_doom_loop_verified",
    ]
    pre, mid, final = cfg.models
    assert pre.pretraining and pre.backend.kind == "openai_completion"
    assert not mid.pretraining and mid.backend.kind == "openai_chat"
    assert all(len(m.revision or "") == 40 for m in cfg.models)
    assert final.revision.startswith("0ec98993")


def test_checkpoints_play_identical_games(tmp_path):
    cfg = build_run_config(sweep(tmp_path))
    games = [
        {
            (s.instance.instance_id, s.condition)
            for s in expand(cfg, m)
            if s.module_id == "a1_pricing"
        }
        for m in cfg.models
    ]
    assert games[0] == games[1] == games[2]
    # pretraining tags only get the tool-free module
    assert {s.module_id for s in expand(cfg, cfg.models[0])} == {"a1_pricing"}


async def test_completion_is_detected_for_resume(tmp_path):
    from collusiongen.runner.experiment import make_services, run_model, write_snapshot

    cfg = build_run_config(sweep(tmp_path, tags=("mid_4_10000",)))
    trivial = cfg.models[0].model_copy(
        update={
            "backend": cfg.models[0].backend.model_copy(
                update={"kind": "trivial", "trivial": "random"}
            )
        }
    )
    cfg = RunConfig.model_validate({**cfg.model_dump(), "models": [trivial.model_dump()]})
    assert not tag_complete(cfg, cfg.models[0])
    write_snapshot(cfg)
    services, _ = make_services(cfg.judge)
    await run_model(cfg, cfg.models[0], services)
    assert tag_complete(cfg, cfg.models[0])


def test_dry_run_mentions_every_tag(tmp_path):
    out = dry_run(sweep(tmp_path))
    assert "pretrain_100000" in out and "anti_doom_loop_verified" in out
