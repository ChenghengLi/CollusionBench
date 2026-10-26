# N4 task inventory

Each `.yaml` file here is one game of the N4 team setup: the survey (`game: survey`) or a
problem brief (`game: brief`, the default). Experiments are kept apart from the tasks:
`configs/setups/` holds the experiment settings and `configs/models/` the models and their runs.
`scripts/experiments.py make` plays every task in every setup for every model;
`scripts/experiments.py status` (and `STATUS.md` here) shows what has finished.

In a brief task the problem statement is cut into pieces of `chunk_chars` characters (20 by
default). Each piece goes in its own file in `/data`, which names the file that continues it, and
the files are dealt out to the agents in turn. Nobody can read the whole problem alone.

Fields:

- `id`: the name used in configs; must match the file name.
- `title`, `version`: for people. Versions of one problem share a title (`depot_v1`, `depot_v2`).
- `answer`: the accepted answer. `kind: number` compares numerically (commas and units ignored);
  `kind: text` compares letters and digits only, ignoring case, spaces and punctuation
  ("Ben, Ana, Cleo" matches "ben ana cleo.").
- Make answers hard to guess: agents may submit up to 10 times, so a choice among a few
  options (one of five names) can be found by trial. Ask for something with many possible values.
- `also_accept` (optional): other spellings that count as correct.
- `statement`: the full problem. Write it so the answer needs every part of the text.

Add a task by adding a file; `tests/test_team.py` checks that every task loads, splits and
reassembles, and that its answer passes its own check.
