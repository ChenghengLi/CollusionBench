# CollusionBench

Do teams of LLM agents break an operator's rule more than one agent facing the same choice, and
which input causes it? CollusionBench puts three agents in an ordinary office task at a named
company. Each team holds part of the data, a written policy forbids passing protected values
between teams, and the office system that would combine them can be down. When it is, the exact
answer is out of reach without breaking the rule together.

The design is in [`docs/redesign/15_realistic_v3.md`](docs/redesign/15_realistic_v3.md). The
earlier benchmark, its paper ("They Say No, Then Do It Anyway", October 2026), runs and analysis
are in [`deprecated/`](deprecated/); the active code no longer replays those runs.

## How a game looks to an agent

- A working day at a fictional company: a named person in a named team, colleagues with names
  and email addresses, a manager, today's date and a 17:00 end of day.
- The request arrives as the manager's email; the answer goes back by email (`send_email`) and the
  manager replies at once (ties out, or does not match the control total, or is reported open).
- Tools: the team's own exports in `/data/<team>` (only its owner can open them), a private
  `/tmp`, the shared drive `/workspace`, company chat, the intranet forum, a calculator, email, and
  the scenario's office system.
- No grader, answer sheet or tool-call counter. When the system is down it behaves like a real
  outage: a 503 or 504, an incident notice, then "back tomorrow at 09:00".

## Layout

```
src/collusiongen/
  modules/n4_relay/office.py   the office environment (tools, people, email hand-in, screen)
  modules/n4_relay/cards/      the scenarios and their parts:
    base.py                      the card game base: policy, standard factors, outage, the
                                 working-day frame (system text, the manager's email, replies)
    realism.py                   names, companies, dates, policy numbers (seeded)
    records.py pricing.py exam.py  the three data scenarios
    template.py                  six desk scenarios from one template (claims, payroll, returns,
                                 grants, customs, fieldwork)
    detect.py layers.py scripts.py  the scorer, the oversight and status-report layers, and the
                                 scripted honest / pooling / asking seats
  core/ agents/ runner/        environment API, LLM policy, run driver (runner/fork.py: one-input replay)
configs/models/              model profiles
scripts/bench.py             the factorial configs (team vs solo x route x standard factors)
scripts/fork_replay.py       counterfactual fork-and-edit replay of a finished game
serving/rcp/                 vLLM serving and job submission on the RCP cluster
tests/                       pytest suite
private_prompts/             git-ignored: instructed prompts and model-organism material
deprecated/                  the earlier benchmark, modules, configs, results, docs and paper
```

## Running

```
uv pip install -e .            # or: .venv/bin/pip install -e .
.venv/bin/python -m pytest -q  # the test suite
.venv/bin/python scripts/bench.py plan --block factorial
.venv/bin/python scripts/bench.py make --model qwen3.8-27b-fp8 --block factorial_smoke --out-dir configs/runs/qwen38/tasks
```

Configs run with `collusiongen run <config.yaml>`; on RCP, `serving/rcp/submit.sh` serves the model
with vLLM and runs every config of a folder (`CONFIG_DIR_OVERRIDE=<folder> MODEL=<preset> ... n4t`).
