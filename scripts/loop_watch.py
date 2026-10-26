"""Watch running N4 games for agents stuck in a loop (the same call over and over).

usage: .venv/bin/python scripts/loop_watch.py <run id> [<run id> ...] [--every 60]

Every --every seconds it scans each run's live transcripts (model games only) and prints one line
per newly looping game. Calls of all agents are interleaved in the live log, so it looks at the game
as a whole: 15+ identical consecutive calls (25+ for wait), one identical call making up half of the
last 60, a submit loop (15+ of the last 60 calls are submits), or idling (45+ of the last 60 waits). Exits when every run's log has finished.
"""

import glob
import json
import os
import sys
import time
from collections import Counter


def signature(d: dict) -> str:
    a = d.get("applied") if isinstance(d.get("applied"), dict) else {}
    tool = a.get("tool", "?")
    arg = f'{a.get("path") or a.get("to") or a.get("post") or ""} {a.get("query") or a.get("pattern") or ""}'.strip()
    text = str(a.get("text") or a.get("content") or "")[:40]
    return f"{tool} {arg} {text}".strip()


def scan(run: str, flagged: set) -> list[str]:
    out = []
    for f in glob.glob(f"runs/**/{run}/*/live/*.jsonl", recursive=True):
        try:
            lines = open(f).read().splitlines()
        except OSError:
            continue
        if not lines or '"kind": "M"' not in lines[0]:
            continue
        sigs = [signature(json.loads(l)) for l in lines]
        streak, best, best_sig = 1, 1, sigs[0]
        for i in range(1, len(sigs)):
            streak = streak + 1 if sigs[i] == sigs[i - 1] else 1
            if streak > best:
                best, best_sig = streak, sigs[i]
        last = sigs[-60:]
        window = Counter(last).most_common(1)[0] if len(sigs) >= 60 else ("", 0)
        submits = sum(x.startswith("submit") for x in last) if len(sigs) >= 60 else 0
        waits = sum(x.startswith("wait") for x in last) if len(sigs) >= 60 else 0
        game = os.path.basename(f)[:8]
        limit = 25 if best_sig.startswith("wait") else 15
        if best >= limit and (game, "streak") not in flagged:
            flagged.add((game, "streak"))
            out.append(f"LOOP {run} game {game}: {best} identical calls in a row: {best_sig} (at call {len(sigs)})")
        if window[1] >= 30 and not window[0].startswith("wait") and (game, "window") not in flagged:
            flagged.add((game, "window"))
            out.append(f"LOOP {run} game {game}: '{window[0]}' is {window[1]} of the last 60 calls (at call {len(sigs)})")
        if submits >= 15 and (game, "submit") not in flagged:
            flagged.add((game, "submit"))
            out.append(f"LOOP {run} game {game}: submit loop, {submits} of the last 60 calls are submits (at call {len(sigs)})")
        if waits >= 45 and (game, "wait") not in flagged:
            flagged.add((game, "wait"))
            out.append(f"IDLE {run} game {game}: {waits} of the last 60 calls are waits (at call {len(sigs)})")
    return out


def finished(run: str) -> bool:
    for log in glob.glob("logs/api_*/current_log") + glob.glob("logs/cross_*/current_log"):
        path = open(log).read().strip()
        key = run.split("_n4_")[-1] if "_n4_" in run else run.split("_", 2)[1] if run.startswith("cross_") else run
        if key in log and os.path.exists(path):
            tail = open(path).read()[-300:]
            if "exit " not in tail:
                return False
    return True


def main(runs: list[str], every: int) -> None:
    flagged: set = set()
    while True:
        for run in runs:
            for line in scan(run, flagged):
                print(line, flush=True)
        if all(finished(r) for r in runs):
            print("all watched runs have finished", flush=True)
            return
        time.sleep(every)


if __name__ == "__main__":
    args = sys.argv[1:]
    every = 60
    if "--every" in args:
        i = args.index("--every")
        every = int(args[i + 1])
        del args[i:i + 2]
    main(args, every)
