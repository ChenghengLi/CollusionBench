#!/usr/bin/env bash
# One-time local setup: vLLM core (prebuilt macOS arm64 wheel) + vllm-metal plugin (MLX),
# pinned to matching releases, plus the MLX k2_horizon model file that mlx-lm lacks.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VLLM_VERSION=0.30.0
METAL_VERSION=0.30.0
MLX_LM_VERSION=0.32.0  # the version the vendored model file was tested with

uv venv --python 3.12 "$ROOT/.venv-vllm"
VIRTUAL_ENV="$ROOT/.venv-vllm" uv pip install \
  "https://github.com/vllm-project/vllm/releases/download/v${VLLM_VERSION}/vllm-${VLLM_VERSION}%2Bcpu-cp312-cp312-macosx_11_0_arm64.whl" \
  "https://github.com/vllm-project/vllm-metal/releases/download/v${METAL_VERSION}/vllm_metal-${METAL_VERSION}-cp312-cp312-macosx_15_0_arm64.whl" \
  "mlx-lm==${MLX_LM_VERSION}"

SRC="$ROOT/serving/mlx_models/k2_horizon.py"
EXPECTED="$(cat "$SRC.sha256")"
ACTUAL="$(shasum -a 256 "$SRC" | cut -d' ' -f1)"
[[ "$ACTUAL" == "$EXPECTED" ]] || { echo "k2_horizon.py hash mismatch; refusing to install" >&2; exit 1; }

SITE="$("$ROOT/.venv-vllm/bin/python" -c 'import mlx_lm, os; print(os.path.dirname(mlx_lm.__file__))')"
cp "$SRC" "$SITE/models/k2_horizon.py"
"$ROOT/.venv-vllm/bin/python" -c "import vllm, vllm_metal, mlx_lm.models.k2_horizon; print('ok: vllm', vllm.__version__)"
