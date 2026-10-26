# CollusionBench

Code, configurations and paper for **"Refuse When Asked, Collude When Blocked: Emergent Collusion in
AI Agent Teams"** (AI Collusion Research Sprint, Apart Research with Poseidon Research and AE Studio,
October 2026).

Three copies of one language model run three departments of a made-up company. Each department holds
records the others need, a written policy forbids passing them between departments, and an office tool
(the *official route*) is the only allowed way to combine them. We switch that route on or off, compare
it with a single scripted request from a colleague, and follow every game through four stages of
collusion: discovery, coordination, joint execution and concealment. We run six final models and the
training checkpoints of K2-Horizon-7B and K2-Horizon-3.7B.

The paper is in [`paper/apart_2026/`](paper/apart_2026/) (`main.tex`, compiled `main.pdf`).

## Repository layout

```
src/collusiongen/        the benchmark package
  modules/n4_relay/cards/  the four card-game scenarios used in the paper
                           (records, pricing, exam, approvals), the scorer (detect.py)
                           and the oversight and status-report layers (layers.py)
  modules/                 earlier modules (pricing, verification, market, mirror)
  core/ agents/ runner/    environment, LLM policy, run driver
  judges/ analysis/        message judges and run analysis
configs/                 run configurations (rcp*/ = the paper's runs, one folder per model/checkpoint)
serving/                 vLLM serving scripts (RCP cluster and local Apple Silicon)
scripts/                 benchmark, rescoring and reporting scripts
analysis/
  scorer_only_2026-10/     recomputes every number in the paper from the game logs
  card_audit_2026-10/      data builders and earlier audit tooling (packets not included)
paper/apart_2026/        LaTeX source, figures (figures/src/ builds them from figures/data/)
docs/                    design notes, scenario catalogue and benchmark specification
tests/                   unit tests
private_prompts/         instructed-condition prompts (git-ignored, never released)
```

Run outputs (`runs/`, about 19 GB) and logs are not in the repository.

## Install

```bash
uv venv --python 3.12 && uv pip install -e ".[dev]"
pytest
```

## Run a scenario

```bash
python -m collusiongen.cli -v run configs/rcpgemma12/tasks/card_records__bench_full.yaml
```

Each run writes `results.jsonl` (one record per game, with the scorer's labels), `events.jsonl`
(every tool call), `transcripts.jsonl` and per-game logs under `live/`. Runs are resumable.

## Reproduce the paper's numbers and figures

```bash
python analysis/scorer_only_2026-10/all_numbers.py          # every count, rate and Fisher test
python paper/apart_2026/figures/src/fig_results.py          # result figures from figures/data/
cd paper/apart_2026 && tectonic main.tex                    # the paper
```

The scripts expect the run outputs under `runs/rcp/`.

## Safety note

The scenarios contain no personal data. Prompts that instruct agents to collude are kept out of the
repository.
