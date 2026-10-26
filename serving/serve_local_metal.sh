#!/usr/bin/env bash
# Serve one K2-Horizon checkpoint locally on Apple Silicon with vLLM + vllm-metal (MLX backend).
#
#   serving/serve_local_metal.sh <revision-sha> <served-name> [port]
#
# The checkpoint is resolved to a local snapshot of an exact commit SHA first, so the server
# can never silently pick up a moved tag. The served name should encode the tag, e.g.
# k2h-3.7b@final, and must match `served_model` in the run config. The served revision is
# recorded in logs/served_<name>.json, which `collusiongen preflight --config ...` checks.
#
# Optional environment: K2H_API_KEY (require this bearer token; set api_key_env in the run
# config), K2H_MAX_MODEL_LEN (default 16384), K2H_EXTRA_ARGS (extra vllm flags, space-separated).
#
# --trust-remote-code only loads IFM's configuration_k2_horizon.py (a plain config dataclass,
# reviewed 2026-10-06); vLLM builds the model from its own registered implementation and
# vllm-metal runs it through MLX (serving/mlx_models/k2_horizon.py).
#
# One-time setup: serving/setup_local_metal.sh
set -euo pipefail

REPO="${K2H_REPO:-IFM/K2-Horizon-3.7B}"
REV="${1:?usage: serve_local_metal.sh <revision-sha> <served-name> [port]}"
NAME="${2:?served name required}"
PORT="${3:-8000}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$ROOT/.venv-vllm"

[[ "$REV" =~ ^[0-9a-f]{40}$ ]] || { echo "revision must be a 40-hex commit SHA" >&2; exit 1; }
[[ "$NAME" =~ ^[A-Za-z0-9_.@-]+$ ]] || { echo "served name must match [A-Za-z0-9_.@-]+" >&2; exit 1; }
[[ "$PORT" =~ ^[0-9]+$ ]] || { echo "port must be numeric" >&2; exit 1; }

MODEL_DIR="$("$VENV/bin/hf" download "$REPO" --revision "$REV" --quiet 2>/dev/null \
             || hf download "$REPO" --revision "$REV" --quiet)"
echo "serving $REPO@$REV from $MODEL_DIR as $NAME on 127.0.0.1:$PORT"

mkdir -p "$ROOT/logs"
"$VENV/bin/python" - "$ROOT/logs/served_${NAME}.json" "$REPO" "$REV" "$NAME" "$MODEL_DIR" "$PORT" <<'PY'
import json, sys, time
path, repo, rev, name, model_dir, port = sys.argv[1:]
json.dump({"repo": repo, "revision": rev, "served_model": name, "model_dir": model_dir,
           "port": int(port), "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
          open(path, "w"), indent=2)
PY

ARGS=(
  serve "$MODEL_DIR"
  --served-model-name "$NAME"
  --host 127.0.0.1 --port "$PORT"   # localhost only: nothing off this machine can reach it
  --trust-remote-code
  --dtype bfloat16
  --reasoning-parser k2_horizon
  # vLLM auto-detects this template as "openai" (list-of-parts) content and then renders the
  # user message as empty; the template expects plain strings.
  --chat-template-content-format string
  # The model's own tool-call format (<ifm|tool_calls> ...), parsed into OpenAI tool_calls.
  # Requests without "tools" are unaffected.
  --enable-auto-tool-choice
  --tool-call-parser k2_horizon
  --max-model-len "${K2H_MAX_MODEL_LEN:-16384}"
  --generation-config vllm
)
if [[ -n "${K2H_API_KEY:-}" ]]; then ARGS+=(--api-key "$K2H_API_KEY"); fi
if [[ -n "${K2H_EXTRA_ARGS:-}" ]]; then read -r -a EXTRA <<< "$K2H_EXTRA_ARGS"; ARGS+=("${EXTRA[@]}"); fi

# MLX-native sampling for seedless requests (about 45% more requests/s measured on an M5 Pro);
# seeded requests still fall back to the torch sampler automatically.
export VLLM_METAL_NATIVE_SAMPLING="${VLLM_METAL_NATIVE_SAMPLING:-1}"

exec "$VENV/bin/vllm" "${ARGS[@]}"
