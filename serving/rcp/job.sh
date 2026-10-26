#!/usr/bin/env bash
# One RCP (EPFL RunAI) job: serve K2-Horizon-3.7B@final on this pod's GPU, then run one
# experiment config against it.
#
#   serving/rcp/job.sh <experiment>     experiment = a1 | n2 | a2 | n4 | n1 | n2j
#                                       (configs/rcp/<experiment>.yaml)
#
# n2j is N2 with the proposal's two-stage regulator (keyword filter, then Qwen3-32B at
# temperature 0). It needs two GPUs: K2-Horizon on GPU 0, the judge on GPU 1 (port 8001); the
# judge is checked against data/judge/n2_messages_labelled.jsonl before any game starts.
#
# Runs as user lichen inside vllm/vllm-openai:v0.30.0 with the `home` volume at /home/lichen
# (see submit.sh). Resumable: if the pod is preempted and restarted, the runner skips finished
# episodes. Everything is logged under logs/rcp_<experiment>/.
set -euo pipefail

EXP="${1:?usage: job.sh <a1|n2|a2|n4|n1|n2j|n1b|h1p|a1s|n2s|h1s|n4s|n4c|n4d|n4b|n4t>}"
[[ "$EXP" =~ ^(a1|n2|a2|n4|n1|n2j|n1b|h1p|a1s|n2s|h1s|n4s|n4c|n4d|n4b|n4t)$ ]] || { echo "unknown experiment $EXP" >&2; exit 2; }
ROOT=/home/lichen/collusiongen
# The model under test. Defaults: K2-Horizon-3.7B final; submit.sh MODEL=7b passes the 7B.
REPO="${MODEL_REPO:-IFM/K2-Horizon-3.7B}"
REV="${MODEL_REV:-d6e5432c59637093c0e125e791d89ea4a0b53559}"
NAME="${MODEL_NAME:-k2h-3.7b@final}"
CONFIGS="${CONFIG_DIR:-configs/rcp}"
# JOB_TAG (submit.sh): several n4t jobs of one model side by side, each with its own logs.
LOG="$ROOT/logs/rcp${RUN_TAG:-}_$EXP${JOB_TAG:+_$JOB_TAG}"
[[ "$REV" =~ ^[0-9a-f]{40}$ ]] || { echo "MODEL_REV must be a 40-hex commit SHA" >&2; exit 2; }
mkdir -p "$LOG"
cd "$ROOT"

# Shared model cache (downloaded once on the jump host); everything else per pod, so five
# jobs never write the same compile cache at once.
export HF_HOME=/home/lichen/hf_cache HF_HUB_OFFLINE=1
MODEL_HF="${MODEL_HF_HOME:-$HF_HOME}"
export XDG_CACHE_HOME=/tmp/cache VLLM_CACHE_ROOT=/tmp/cache/vllm TRITON_CACHE_DIR=/tmp/cache/triton
MODEL_DIR="$MODEL_HF/hub/models--${REPO//\//--}/snapshots/$REV"
[[ -f "$MODEL_DIR/config.json" ]] || { echo "model snapshot missing: $MODEL_DIR" >&2; exit 1; }

{
  echo "start $(date -u +%FT%TZ) host $(hostname) experiment $EXP"
  nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv
} | tee -a "$LOG/job.log"
python3 - "$LOG/served.json" "$REPO" "$REV" "$NAME" "$MODEL_DIR" <<'PY'
import json, sys, time
path, repo, rev, name, model_dir = sys.argv[1:]
json.dump({"repo": repo, "revision": rev, "served_model": name, "model_dir": model_dir,
           "port": 8000, "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
          open(path, "w"), indent=2)
PY

wait_healthy() {  # wait_healthy <port> <pid> <log>
  for _ in $(seq 1 180); do
    if command -v curl >/dev/null; then curl -sf "http://127.0.0.1:$1/health" >/dev/null && return 0
    else python3 -c "import sys,urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{sys.argv[1]}/health', timeout=5)" "$1" 2>/dev/null && return 0; fi
    kill -0 "$2" 2>/dev/null || { echo "server on port $1 exited during startup; see $3" | tee -a "$LOG/job.log"; exit 1; }
    sleep 5
  done
  echo "server on port $1 not healthy after 15 min" | tee -a "$LOG/job.log"; exit 1
}

# Same serving flags as serving/serve_local_metal.sh, sized for one 80 GB H100.
# REASONING_PARSER / TOOL_PARSER (submit.sh model presets) pick the model's vLLM parsers: K2
# Horizon by default; Qwen3.8 uses qwen3 / qwen3_coder (its vLLM recipe).
# N4 team games (n4c, n4d) give each agent 150 tool calls, so their histories need a longer
# context than the 16k the other experiments use; the model supports 524k.
MAX_LEN=16384
[[ "$EXP" =~ ^(n4c|n4d|n4b|n4t)$ ]] && MAX_LEN=65536
# High-reasoning runs need room for 32k-token replies on top of the history (IFM's recipe: 131072).
MAX_LEN="${MAX_LEN_OVERRIDE:-$MAX_LEN}"
# Large models (submit.sh MODEL=32b / mova) are split over TP GPUs as in IFM's vLLM recipe;
# SERVE_ARGS carries per-model flags (--model-impl vllm, --enable-expert-parallel).
TP="${TP:-1}"
PY=python3  # interpreter for the game runner; the SGLang branch switches it to the image's own
GPUS_VISIBLE=$(seq -s, 0 $((TP - 1)))
read -r -a EXTRA_SERVE <<< "${SERVE_ARGS:-}"
if [[ "${ENGINE:-vllm}" == sglang ]]; then
  # IFM's validated SGLang recipe (model card / SGLang cookbook); needs an SGLang image with the
  # K2 Horizon runtime (PR #37654, in v0.5.19+). SGL_ROUTER_PARTITIONS reproduces the MoVA
  # checkpoint's source router numerics (BF16 partial GEMMs, FP32 reduction order).
  SGL_EXTRA=()
  [[ -n "${SGL_ROUTER_PARTITIONS:-}" ]] && SGL_EXTRA=(--json-model-override-args "{\"xllm_source_router_gemm_partitions\":${SGL_ROUTER_PARTITIONS}}")
  # su resets PATH, so the image's own Python (the one with SGLang) is looked up explicitly.
  SGL_PY=""
  # lmsysorg/sglang images install SGLang in a virtualenv at /opt/sglang (image ENV PATH).
  for py in /opt/sglang/bin/python3 /usr/local/bin/python3 /opt/conda/bin/python3 /usr/bin/python3; do
    if [[ -x "$py" ]] && "$py" -c "import sglang" 2>/dev/null; then SGL_PY="$py"; break; fi
  done
  [[ -n "$SGL_PY" ]] || { echo "no Python with sglang found in this image" | tee -a "$LOG/job.log"; exit 1; }
  PY="$SGL_PY"  # the runner uses the same interpreter (it has numpy, pydantic, httpx, yaml)
  echo "sglang python: $SGL_PY ($("$SGL_PY" -c "import sglang; print(sglang.__version__)"))" | tee -a "$LOG/job.log"
  CUDA_VISIBLE_DEVICES=$GPUS_VISIBLE "$SGL_PY" -m sglang.launch_server \
    --model-path "$MODEL_DIR" \
    --served-model-name "$NAME" \
    --host 127.0.0.1 --port 8000 \
    --tp "$TP" "${EXTRA_SERVE[@]}" "${SGL_EXTRA[@]}" \
    --attention-backend fa3 \
    --reasoning-parser k2_horizon \
    --tool-call-parser k2_horizon \
    --context-length "$MAX_LEN" \
    --mem-fraction-static 0.85 \
    >> "$LOG/server.log" 2>&1 &
else
  CUDA_VISIBLE_DEVICES=$GPUS_VISIBLE vllm serve "$MODEL_DIR" \
    --tensor-parallel-size "$TP" "${EXTRA_SERVE[@]}" \
    --served-model-name "$NAME" \
    --host 127.0.0.1 --port 8000 \
    --trust-remote-code \
    --dtype bfloat16 \
    --reasoning-parser "${REASONING_PARSER:-k2_horizon}" \
    --chat-template-content-format string \
    --enable-auto-tool-choice --tool-call-parser "${TOOL_PARSER:-k2_horizon}" \
    --max-model-len "$MAX_LEN" \
    --generation-config vllm \
    --gpu-memory-utilization 0.90 \
    --max-num-seqs 256 \
    >> "$LOG/server.log" 2>&1 &
fi
SERVER=$!
JUDGE_PID=""
trap 'kill $SERVER $JUDGE_PID 2>/dev/null || true' EXIT

if [[ "$EXP" == n2j || "$EXP" == n2s ]]; then
  JUDGE_REV=9216db5781bf21249d130ec9da846c4624c16137   # Qwen/Qwen3-32B, pinned
  # 65 GB: kept on the lab scratch volume (mounted at /mnt/dlab/scratch), not the home quota.
  JUDGE_HF="${JUDGE_HF_HOME:-/mnt/dlab/scratch/dlabscratch1/lichen/hf_cache}"
  JUDGE_DIR="$JUDGE_HF/hub/models--Qwen--Qwen3-32B/snapshots/$JUDGE_REV"
  [[ -f "$JUDGE_DIR/config.json" ]] || { echo "judge snapshot missing: $JUDGE_DIR" >&2; exit 1; }
  CUDA_VISIBLE_DEVICES=1 vllm serve "$JUDGE_DIR" \
    --served-model-name qwen3-32b \
    --host 127.0.0.1 --port 8001 \
    --dtype bfloat16 \
    --max-model-len 8192 \
    --generation-config vllm \
    --gpu-memory-utilization 0.90 \
    >> "$LOG/judge_server.log" 2>&1 &
  JUDGE_PID=$!
fi

wait_healthy 8000 "$SERVER" "$LOG/server.log"
[[ -z "$JUDGE_PID" ]] || wait_healthy 8001 "$JUDGE_PID" "$LOG/judge_server.log"
echo "server ready $(date -u +%FT%TZ)" | tee -a "$LOG/job.log"

# The runner's own dependencies, per pod. numpy, pydantic, pyyaml and httpx come with the vLLM
# image; --no-deps keeps its numpy instead of pulling a newer one into the runner.
"$PY" -m pip install --quiet --no-cache-dir --no-deps --target /tmp/pydeps scipy >> "$LOG/job.log" 2>&1 || echo "scipy not installed (optional)" >> "$LOG/job.log"
# Other images (SGLang) may lack some of the runner's light dependencies.
"$PY" -c "import yaml, httpx, pydantic, numpy" 2>/dev/null || "$PY" -m pip install --quiet --no-cache-dir --target /tmp/pydeps pyyaml httpx pydantic numpy >> "$LOG/job.log" 2>&1 \
  || { echo "runner dependencies missing and pip unavailable for $PY" | tee -a "$LOG/job.log"; exit 1; }
export PYTHONPATH="/tmp/pydeps:$ROOT/src"

if [[ -n "$JUDGE_PID" ]]; then
  # Check the regulator before it fines anyone: LLM judge alone and the two-stage judge.
  python3 - "$ROOT/data/judge/n2_messages_labelled.jsonl" >> "$LOG/judge_validation.txt" 2>&1 <<'PY'
import asyncio, sys
from pathlib import Path
from collusiongen.agents.backends import OpenAIChatBackend
from collusiongen.judges.messages import KeywordJudge, LLMJudge, TwoStageJudge
from collusiongen.judges.validate import validate_judge

async def main() -> None:
    b = OpenAIChatBackend("http://127.0.0.1:8001", "qwen3-32b")
    llm = LLMJudge(b, extra_body={"chat_template_kwargs": {"enable_thinking": False}})
    for name, j in [("keyword", KeywordJudge()), ("llm", llm),
                    ("two_stage", TwoStageJudge(KeywordJudge(), llm))]:
        v = await validate_judge(j, Path(sys.argv[1]))
        print(f"{name:<10} n={v.n} accuracy={v.accuracy:.2f} precision={v.precision:.2f} "
              f"recall={v.recall:.2f} kappa={v.kappa:.2f}")
    await b.aclose()
asyncio.run(main())
PY
  cat "$LOG/judge_validation.txt" | tee -a "$LOG/job.log"
fi

set +e
if [[ "$EXP" == n4b ]]; then
  # Both N4 survey experiments at once against this one server (each resumes on its own).
  "$PY" -m collusiongen.cli -v run "$CONFIGS/n4c.yaml" >> "$LOG/run_n4c.log" 2>&1 &
  P1=$!
  "$PY" -m collusiongen.cli -v run "$CONFIGS/n4d.yaml" >> "$LOG/run_n4d.log" 2>&1 &
  P2=$!
  wait $P1; S1=$?; wait $P2; S2=$?
  echo "exit $S1" >> "$LOG/run_n4c.log"; echo "exit $S2" >> "$LOG/run_n4d.log"
  STATUS=$(( S1 > S2 ? S1 : S2 ))
elif [[ "$EXP" == n4t ]]; then
  # Every task config (one run per task and setup, written by scripts/experiments.py make) at
  # once against this one server; each resumes on its own and logs to run_<task>__<setup>.log.
  PIDS=(); NAMES=()
  # TASKS (submit.sh): a file-name pattern to run only some task configs on this job's GPU.
  for C in "$CONFIGS"/tasks/${TASKS:-*}.yaml; do
    N="$(basename "$C" .yaml)"
    "$PY" -m collusiongen.cli -v run "$C" >> "$LOG/run_$N.log" 2>&1 &
    PIDS+=($!); NAMES+=("$N")
  done
  STATUS=0
  for i in "${!PIDS[@]}"; do
    wait "${PIDS[$i]}"; S=$?
    echo "exit $S" >> "$LOG/run_${NAMES[$i]}.log"
    (( S > STATUS )) && STATUS=$S
  done
else
  "$PY" -m collusiongen.cli -v run "$CONFIGS/$EXP.yaml" >> "$LOG/run.log" 2>&1
  STATUS=$?
  echo "exit $STATUS" >> "$LOG/run.log"
fi
set -e
echo "done $(date -u +%FT%TZ) exit $STATUS" | tee -a "$LOG/job.log"
exit $STATUS
