#!/usr/bin/env bash
# Submit one RunAI training job per experiment on RCP, each on its own H100.
# Run on the RCP jump host after `runai login`:
#
#   serving/rcp/submit.sh a1 n2 a2 n4 n1        (DRY=1 prints the commands only)
#   serving/rcp/submit.sh n2j                   N2 with the LLM regulator: 2 GPUs (model + judge)
#   MODEL=7b serving/rcp/submit.sh a1 n2j a2 n4 n1b    the same experiments on K2-Horizon-7B
#   MODEL=7b TASKS='audit_school_v1__*' JOB_TAG=school serving/rcp/submit.sh n4t
#                                               only some task configs, as its own job (own H100)
#
# Billing: the dlab project pays per GPU hour. Jobs beyond the project's guaranteed GPUs run
# over quota and can be preempted; the runner resumes where it stopped when the job restarts.
set -euo pipefail

PROJECT="${PROJECT:-dlab-lichen}"
IMAGE="${IMAGE:-vllm/vllm-openai:v0.30.0}"
POOL="${POOL:-h100}"
USER_UID=316680
USER_GID="$(id -g)"
LAB_GID=60220   # dlab_AppGrpU: owns the lab scratch volume (judge weights live there)
SCRATCH_HF=/mnt/dlab/scratch/dlabscratch1/lichen/hf_cache

# Model presets: the job reads these through `runai submit -e`.
case "${MODEL:-3.7b}" in
  3.7b) PREFIX=cg; MODEL_ENV=() ;;
  7b)   PREFIX=cg7
        MODEL_ENV=(-e MODEL_REPO=IFM/K2-Horizon-7B
                   -e MODEL_REV=3b6ae394c1b863c27a306d168b25555837955192   # main = anti_doom_loop_verified weights
                   -e MODEL_NAME=k2h-7b@final -e MODEL_HF_HOME=$SCRATCH_HF
                   -e CONFIG_DIR=configs/rcp7b -e RUN_TAG=7b) ;;
  # Further sizes for the N4 channel experiments (experiment n4b runs both on one server).
  # 32B and MoVA use IFM's official FP8 builds (k2-horizon-quantization collection), made from an
  # earlier checkpoint than the BF16 `main`; served over 2 GPUs as in IFM's vLLM recipe.
  0.9b) PREFIX=cg09
        MODEL_ENV=(-e MODEL_REPO=IFM/K2-Horizon-0.9B
                   -e MODEL_REV=383cb66347be4d361138e8157c2f8779b7440752   # main = rl-mopd_249
                   -e MODEL_NAME=k2h-0.9b@final -e MODEL_HF_HOME=$SCRATCH_HF
                   -e CONFIG_DIR=configs/rcp09b -e RUN_TAG=09b) ;;
  32b)  PREFIX=cg32
        MODEL_ENV=(-e MODEL_REPO=IFM/K2-Horizon-32B-FP8
                   -e MODEL_REV=409c1648fa3a92f80a0c0b55cea8b2d675a85bf1
                   -e MODEL_NAME=k2h-32b-fp8 -e MODEL_HF_HOME=$SCRATCH_HF
                   -e CONFIG_DIR=configs/rcp32b -e RUN_TAG=32b
                   -e TP=2 -e SERVE_ARGS=--model-impl=vllm) ;;
  mova) PREFIX=cgmv
        MODEL_ENV=(-e MODEL_REPO=IFM/K2-Horizon-MoVA-36B-A4B-FP8
                   -e MODEL_REV=8ca253eb585f5ec45bf7823adcf2b81d79630837
                   -e MODEL_NAME=k2h-mova-36b-fp8 -e MODEL_HF_HOME=$SCRATCH_HF
                   -e CONFIG_DIR=configs/rcpmova -e RUN_TAG=mova
                   -e TP=2 -e SERVE_ARGS=--enable-expert-parallel) ;;
  # Ablation: the MoVA's final BF16 weights (main = sft_2_2500) instead of the earlier FP8 build.
  movabf16) PREFIX=cgmb
        MODEL_ENV=(-e MODEL_REPO=IFM/K2-Horizon-MoVA-36B-A4B
                   -e MODEL_REV=cca48b6631d03c338a0e1d8beb0c392af8becbd3
                   -e MODEL_NAME=k2h-mova-36b@final -e MODEL_HF_HOME=$SCRATCH_HF
                   -e CONFIG_DIR=configs/rcpmovabf16 -e RUN_TAG=movabf16
                   -e TP=2 -e SERVE_ARGS=--enable-expert-parallel) ;;
  # Reasoning ablation of the MoVA FP8 run: high reasoning and the card's settings, served by
  # vLLM (movahi) or by IFM's validated SGLang recipe with the router override (movasg).
  movahi) PREFIX=cgmh
        MODEL_ENV=(-e MODEL_REPO=IFM/K2-Horizon-MoVA-36B-A4B-FP8
                   -e MODEL_REV=8ca253eb585f5ec45bf7823adcf2b81d79630837
                   -e MODEL_NAME=k2h-mova-36b-fp8-high -e MODEL_HF_HOME=$SCRATCH_HF
                   -e CONFIG_DIR=configs/rcpmovahi -e RUN_TAG=movahi -e MAX_LEN_OVERRIDE=131072
                   -e TP=2 -e SERVE_ARGS=--enable-expert-parallel) ;;
  movasg) PREFIX=cgms; IMAGE=lmsysorg/sglang:v0.5.21
        MODEL_ENV=(-e MODEL_REPO=IFM/K2-Horizon-MoVA-36B-A4B-FP8
                   -e MODEL_REV=8ca253eb585f5ec45bf7823adcf2b81d79630837
                   -e MODEL_NAME=k2h-mova-36b-fp8-high-sglang -e MODEL_HF_HOME=$SCRATCH_HF
                   -e CONFIG_DIR=configs/rcpmovasg -e RUN_TAG=movasg -e MAX_LEN_OVERRIDE=131072
                   -e TP=2 -e SERVE_ARGS=--ep=2 -e ENGINE=sglang -e SGL_ROUTER_PARTITIONS=2) ;;
  # A non-K2 comparison model (2026-10-24): Qwen's official FP8 build of the dense Qwen3.8-27B, one
  # H100, served with the parsers from its vLLM recipe.
  qwen38) PREFIX=cgq
        MODEL_ENV=(-e MODEL_REPO=Qwen/Qwen3.8-27B-FP8
                   -e MODEL_REV=017b9c7af6b5689d5dd426a76e0bc077eb5ca20a
                   -e MODEL_NAME=qwen3.8-27b-fp8 -e MODEL_HF_HOME=$SCRATCH_HF
                   -e CONFIG_DIR=configs/rcpqwen38 -e RUN_TAG=qwen38
                   -e REASONING_PARSER=qwen3 -e TOOL_PARSER=qwen3_coder) ;;
  # Model organism (2026-11-04): BF16 Qwen3.8-27B with the sft_v1 LoRA (epoch-1 checkpoint of the transformers+peft
  # retrain, job_train_tf.sh) merged in by
  # private_prompts/organisms/sft_v1/train/cluster/merge_lora.py; a local snapshot, no Hub revision.
  # BF16 27B (about 54 GB): fits one 80 GB H100 (hybrid attention keeps the KV cache small); POOL=h200 also works.
  qwen38lora) PREFIX=cgql
        MODEL_ENV=(-e MODEL_REPO=local/qwen38-lora-tf-e1
                   -e MODEL_REV=c34a9f1090bd99d11be37a77dc02994a0a1828cd
                   -e MODEL_NAME=qwen38-lora-e1 -e MODEL_HF_HOME=$SCRATCH_HF
                   -e CONFIG_DIR=configs/rcpqwen38lora -e RUN_TAG=qwen38lora
                   -e REASONING_PARSER=qwen3 -e TOOL_PARSER=qwen3_coder) ;;
  qwen38lora2) PREFIX=cgql2   # the same organism after epoch 2 (checkpoint-76)
        MODEL_ENV=(-e MODEL_REPO=local/qwen38-lora-tf-e2
                   -e MODEL_REV=a3db8e4eeba863c62410507b38c0e9454518b63f
                   -e MODEL_NAME=qwen38-lora-e2 -e MODEL_HF_HOME=$SCRATCH_HF
                   -e CONFIG_DIR=configs/rcpqwen38lora_e2 -e RUN_TAG=qwen38lora2
                   -e REASONING_PARSER=qwen3 -e TOOL_PARSER=qwen3_coder) ;;
  qwen38lora3) PREFIX=cgql3   # the same organism after epoch 3 (checkpoint-114)
        MODEL_ENV=(-e MODEL_REPO=local/qwen38-lora-tf-e3
                   -e MODEL_REV=9a168c842aa32f2ffe2a41339f54a3cb8c256d37
                   -e MODEL_NAME=qwen38-lora-e3 -e MODEL_HF_HOME=$SCRATCH_HF
                   -e CONFIG_DIR=configs/rcpqwen38lora_e3 -e RUN_TAG=qwen38lora3
                   -e REASONING_PARSER=qwen3 -e TOOL_PARSER=qwen3_coder) ;;
  # The three organisms after the anti-doom-loop (FTPO) stage (2026-11-05): antidoom LoRA merged by
  # private_prompts/organisms/sft_v1/antidoom/job_train.sh; revisions = sha1 of qwen38-lora-tf-e<k>-antidoom.
  qwen38lora1ad) PREFIX=cgqa1
        MODEL_ENV=(-e MODEL_REPO=local/qwen38-lora-tf-e1-antidoom
                   -e MODEL_REV=5bfdca8807ab449f549303c35012db7fd1e997be
                   -e MODEL_NAME=qwen38-lora-e1-ad -e MODEL_HF_HOME=$SCRATCH_HF
                   -e CONFIG_DIR=configs/rcpqwen38lora_e1ad -e RUN_TAG=qwen38lora1ad
                   -e REASONING_PARSER=qwen3 -e TOOL_PARSER=qwen3_coder) ;;
  qwen38lora2ad) PREFIX=cgqa2
        MODEL_ENV=(-e MODEL_REPO=local/qwen38-lora-tf-e2-antidoom
                   -e MODEL_REV=feb8d3bf797a8a4496dfee9aa9572bf952ad21a4
                   -e MODEL_NAME=qwen38-lora-e2-ad -e MODEL_HF_HOME=$SCRATCH_HF
                   -e CONFIG_DIR=configs/rcpqwen38lora_e2ad -e RUN_TAG=qwen38lora2ad
                   -e REASONING_PARSER=qwen3 -e TOOL_PARSER=qwen3_coder) ;;
  qwen38lora3ad) PREFIX=cgqa3
        MODEL_ENV=(-e MODEL_REPO=local/qwen38-lora-tf-e3-antidoom
                   -e MODEL_REV=36de84dda12cc0de1055664d2e1cd98ed5ed8433
                   -e MODEL_NAME=qwen38-lora-e3-ad -e MODEL_HF_HOME=$SCRATCH_HF
                   -e CONFIG_DIR=configs/rcpqwen38lora_e3ad -e RUN_TAG=qwen38lora3ad
                   -e REASONING_PARSER=qwen3 -e TOOL_PARSER=qwen3_coder) ;;
  # GRPO-RLVR pilot checkpoints on the e3 organism (2026-11-06): adapters/step000<k> merged by
  # private_prompts/organisms/grpo_rlvr/job_merge.sh; revisions = sha1 of qwen38-grpo-e3-step<k>.
  qwen38grpo5) PREFIX=cgqg5
        MODEL_ENV=(-e MODEL_REPO=local/qwen38-grpo-s5
                   -e MODEL_REV=96f9795c7db7409fa39786541797ea0b4c72bd76
                   -e MODEL_NAME=qwen38-grpo-s5 -e MODEL_HF_HOME=$SCRATCH_HF
                   -e CONFIG_DIR=configs/rcpqwen38grpo_s5 -e RUN_TAG=qwen38grpo5
                   -e REASONING_PARSER=qwen3 -e TOOL_PARSER=qwen3_coder) ;;
  qwen38grpo7) PREFIX=cgqg7
        MODEL_ENV=(-e MODEL_REPO=local/qwen38-grpo-s7
                   -e MODEL_REV=8f02f41e5cd620ca848227c4877570dc46767061
                   -e MODEL_NAME=qwen38-grpo-s7 -e MODEL_HF_HOME=$SCRATCH_HF
                   -e CONFIG_DIR=configs/rcpqwen38grpo_s7 -e RUN_TAG=qwen38grpo7
                   -e REASONING_PARSER=qwen3 -e TOOL_PARSER=qwen3_coder) ;;
  qwen38grpo9) PREFIX=cgqg9
        MODEL_ENV=(-e MODEL_REPO=local/qwen38-grpo-s9
                   -e MODEL_REV=ac1c1295002bcb49f2d991544f8c959fc754b804
                   -e MODEL_NAME=qwen38-grpo-s9 -e MODEL_HF_HOME=$SCRATCH_HF
                   -e CONFIG_DIR=configs/rcpqwen38grpo_s9 -e RUN_TAG=qwen38grpo9
                   -e REASONING_PARSER=qwen3 -e TOOL_PARSER=qwen3_coder) ;;
  # Qwen3.6-35B-A3B (2026-11-18): Qwen's official FP8 build of the mixture-of-experts model (35B total,
  # ~3B active), one H100, parsers from its model card. Candidate for the RL organism.
  qwen36moe) PREFIX=cgqm
        MODEL_ENV=(-e MODEL_REPO=Qwen/Qwen3.6-35B-A3B-FP8
                   -e MODEL_REV=c653bba46dfa06e9658dcc0b0dc87fe4685f14a2
                   -e MODEL_NAME=qwen3.6-35b-a3b-fp8 -e MODEL_HF_HOME=$SCRATCH_HF
                   -e CONFIG_DIR=configs/rcpqwen36moe -e RUN_TAG=qwen36moe
                   -e REASONING_PARSER=qwen3 -e TOOL_PARSER=qwen3_coder) ;;
  # Any merged Qwen3.8-27B organism in the scratch HF cache (2026-11-17, distill_v1):
  # LOCAL_NAME=qwen38-distill-d1-e2 LOCAL_REV=<40 hex> MODEL=qwen38local CONFIG_DIR_OVERRIDE=... submit.sh n4t
  qwen38local) PREFIX=cgqx
        [[ "${LOCAL_NAME:-}" =~ ^qwen38-[a-z0-9-]+$ && "${LOCAL_REV:-}" =~ ^[0-9a-f]{40}$ ]] \
          || { echo "MODEL=qwen38local needs LOCAL_NAME=qwen38-... and a 40-hex LOCAL_REV" >&2; exit 2; }
        MODEL_ENV=(-e MODEL_REPO=local/$LOCAL_NAME -e MODEL_REV=$LOCAL_REV
                   -e MODEL_NAME=$LOCAL_NAME -e MODEL_HF_HOME=$SCRATCH_HF
                   -e CONFIG_DIR=configs/unused -e RUN_TAG=${LOCAL_NAME//-/_}
                   -e REASONING_PARSER=qwen3 -e TOOL_PARSER=qwen3_coder) ;;
  # Meta's Muse Glimmer 30B (2026-10-24): dense, official BF16 weights (no official 8-bit build; the
  # FP8 one is RedHatAI's), over 2 H100s, with the parsers from its vLLM recipe. Its effort is set
  # in the system prompt ("Reasoning strength: low", configs/models/muse-glimmer-30b.yaml).
  glimmer) PREFIX=cgg
        MODEL_ENV=(-e MODEL_REPO=meta-models/Muse-Glimmer-30B
                   -e MODEL_REV=cec94fcfd6512f2cfe708138c32533b346ea4f69
                   -e MODEL_NAME=muse-glimmer-30b -e MODEL_HF_HOME=$SCRATCH_HF
                   -e CONFIG_DIR=configs/rcpglimmer -e RUN_TAG=glimmer -e TP=2
                   -e REASONING_PARSER=muse_glimmer -e TOOL_PARSER=muse_glimmer) ;;
  # K2-Horizon-7B intermediate checkpoints for the card benchmark (the user's picks, 2026-10-24):
  # CKPT_TAG=<branch> CKPT_REV=<40-hex commit>, e.g. mid_4_10000, rl_merged, sft_1_10000, sft_2_2500.
  # Served exactly like the final 7B, one H100; configs in configs/rcp7b_<tag>/.
  7bckpt) PREFIX=cg7c
        [[ "${CKPT_TAG:-}" =~ ^[a-z0-9_-]+$ && "${CKPT_REV:-}" =~ ^[0-9a-f]{40}$ ]] \
          || { echo "MODEL=7bckpt needs CKPT_TAG and a 40-hex CKPT_REV" >&2; exit 2; }
        MODEL_ENV=(-e MODEL_REPO=IFM/K2-Horizon-7B -e MODEL_REV=$CKPT_REV
                   -e MODEL_NAME=k2h-7b@$CKPT_TAG -e MODEL_HF_HOME=$SCRATCH_HF
                   -e CONFIG_DIR=configs/rcp7b_$CKPT_TAG -e RUN_TAG=7b_$CKPT_TAG) ;;
  # Google's Gemma 4 12B and 31B instruction models (2026-10-25). Google ships no FP8 build, so the
  # official BF16 weights are quantized to FP8 by vLLM at load (--quantization fp8), one H100 each,
  # with the parsers and tool chat template from vLLM's Gemma 4 recipe (template copied from vLLM
  # v0.30.0 examples/), text only.
  gemma12|gemma31) PREFIX=cgm${MODEL#gemma}
        case "$MODEL" in
          gemma12) GREPO=google/gemma-4-12B-it; GREV=707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7 ;;
          gemma31) GREPO=google/gemma-4-31B-it; GREV=842da3794eaa0b77d5f08bae87a17459d91ff475 ;;
        esac
        MODEL_ENV=(-e MODEL_REPO=$GREPO -e MODEL_REV=$GREV
                   -e MODEL_NAME=gemma-4-${MODEL#gemma}b-it-fp8 -e MODEL_HF_HOME=$SCRATCH_HF
                   -e CONFIG_DIR=configs/rcp$MODEL -e RUN_TAG=$MODEL
                   -e REASONING_PARSER=gemma4 -e TOOL_PARSER=gemma4
                   -e "SERVE_ARGS=--quantization fp8 --chat-template /home/lichen/collusiongen/serving/rcp/templates/tool_chat_template_gemma4.jinja --limit-mm-per-prompt.image 0 --limit-mm-per-prompt.audio 0") ;;
  # The same sweep for K2-Horizon-3.7B (the user's request, 2026-10-25): served like the final 3.7B,
  # one H100; configs in configs/rcp3b_<tag>/.
  3bckpt) PREFIX=cg3c
        [[ "${CKPT_TAG:-}" =~ ^[a-z0-9_-]+$ && "${CKPT_REV:-}" =~ ^[0-9a-f]{40}$ ]] \
          || { echo "MODEL=3bckpt needs CKPT_TAG and a 40-hex CKPT_REV" >&2; exit 2; }
        MODEL_ENV=(-e MODEL_REPO=IFM/K2-Horizon-3.7B -e MODEL_REV=$CKPT_REV
                   -e MODEL_NAME=k2h-3.7b@$CKPT_TAG -e MODEL_HF_HOME=$SCRATCH_HF
                   -e CONFIG_DIR=configs/rcp3b_$CKPT_TAG -e RUN_TAG=3b_$CKPT_TAG) ;;
  *) echo "unknown MODEL ${MODEL}" >&2; exit 2 ;;
esac

# REP=ra|rb|...: a repetition of the same games (configs/<dir>_rep<REP>, see episode_offset).
# Its configs, logs and job name get the suffix; everything else is the model's preset.
if [[ -n "${REP:-}" ]]; then
  [[ "$REP" =~ ^r[a-z]$ ]] || { echo "REP must look like ra, rb, ..." >&2; exit 2; }
  BASE_DIR=configs/rcp; BASE_TAG=""
  KEPT=()
  for ((i = 0; i < ${#MODEL_ENV[@]}; i++)); do
    if [[ "${MODEL_ENV[i]}" == -e && "${MODEL_ENV[i+1]:-}" =~ ^(CONFIG_DIR|RUN_TAG)=(.*)$ ]]; then
      [[ "${BASH_REMATCH[1]}" == CONFIG_DIR ]] && BASE_DIR="${BASH_REMATCH[2]}"
      [[ "${BASH_REMATCH[1]}" == RUN_TAG ]] && BASE_TAG="${BASH_REMATCH[2]}"
      i=$((i + 1)); continue
    fi
    KEPT+=("${MODEL_ENV[i]}")
  done
  MODEL_ENV=("${KEPT[@]}" -e "CONFIG_DIR=${BASE_DIR}_rep$REP" -e "RUN_TAG=${BASE_TAG}_rep$REP")
fi

# CONFIG_DIR_OVERRIDE=<dir> [RUN_TAG_OVERRIDE=<tag>]: the model's preset served as usual, but the
# task configs (and log folder) of another directory, e.g. the private organism-data runs.
if [[ -n "${CONFIG_DIR_OVERRIDE:-}" ]]; then
  [[ "${RUN_TAG_OVERRIDE:-x}" =~ ^[a-z0-9_]+$ ]] || { echo "RUN_TAG_OVERRIDE: [a-z0-9_]+" >&2; exit 2; }
  KEPT=()
  for ((i = 0; i < ${#MODEL_ENV[@]}; i++)); do
    if [[ "${MODEL_ENV[i]}" == -e && "${MODEL_ENV[i+1]:-}" =~ ^(CONFIG_DIR|RUN_TAG)= ]]; then
      i=$((i + 1)); continue
    fi
    KEPT+=("${MODEL_ENV[i]}")
  done
  MODEL_ENV=("${KEPT[@]}" -e "CONFIG_DIR=$CONFIG_DIR_OVERRIDE"
             -e "RUN_TAG=${RUN_TAG_OVERRIDE:-$(basename "$CONFIG_DIR_OVERRIDE")}")
fi

# TP_OVERRIDE=1 (2026-11-18): serve a model the preset splits over 2 GPUs on one GPU instead, e.g.
# MoVA BF16 (72 GB) on one H200 (POOL=h200); drops the preset's SERVE_ARGS (expert parallel).
if [[ -n "${TP_OVERRIDE:-}" ]]; then
  [[ "$TP_OVERRIDE" =~ ^[12]$ ]] || { echo "TP_OVERRIDE: 1 or 2" >&2; exit 2; }
  KEPT=()
  for ((i = 0; i < ${#MODEL_ENV[@]}; i++)); do
    if [[ "${MODEL_ENV[i]}" == -e && "${MODEL_ENV[i+1]:-}" =~ ^(TP|SERVE_ARGS)= ]]; then
      i=$((i + 1)); continue
    fi
    KEPT+=("${MODEL_ENV[i]}")
  done
  MODEL_ENV=("${KEPT[@]}" -e "TP=$TP_OVERRIDE")
fi

# Each job runs a private copy of job.sh: the home volume is NFS, so replacing job.sh while a
# job reads it kills that job with "Stale file handle" (seen 2026-10-07).
JOB_SRC="${JOB_SCRIPT:-/home/lichen/collusiongen/serving/rcp/job.sh}"
SNAP_DIR=/home/lichen/collusiongen/.jobs
mkdir -p "$SNAP_DIR"

for EXP in "$@"; do
  [[ "$EXP" =~ ^(a1|n2|a2|n4|n1|n2j|n1b|h1p|a1s|n2s|h1s|n4s|n4c|n4d|n4b|n4t)$ ]] || { echo "unknown experiment $EXP" >&2; exit 2; }
  NAME="$PREFIX-$EXP${REP:+-$REP}${JOB_TAG:+-$JOB_TAG}"
  SNAP="$SNAP_DIR/job-$EXP-$(date +%Y%m%d-%H%M%S).sh"
  cp "$JOB_SRC" "$SNAP" && chmod 700 "$SNAP"
  GPUS=1; MEM=96G
  [[ "${MODEL:-3.7b}" =~ ^(32b|mova|movabf16|movahi|movasg|glimmer)$ ]] && { GPUS=2; MEM=160G; }
  [[ -n "${TP_OVERRIDE:-}" ]] && GPUS=$TP_OVERRIDE
  EXTRA=()
  [[ "${MODEL:-3.7b}" == 3.7b ]] || EXTRA=(--existing-pvc "claimname=dlab-scratch,path=/mnt/dlab/scratch")
  if [[ "$EXP" == n2j || "$EXP" == n2s ]]; then
    GPUS=2; MEM=160G
    EXTRA=(--existing-pvc "claimname=dlab-scratch,path=/mnt/dlab/scratch")  # judge weights
  fi
  CMD=(runai submit --name "$NAME" -p "$PROJECT" -i "$IMAGE"
       -g "$GPUS" --node-pools "$POOL" --cpu 16 --memory "$MEM" --large-shm
       --backoff-limit 3
       --existing-pvc "claimname=home,path=/home/lichen" "${EXTRA[@]}" "${MODEL_ENV[@]}"
       ${ROOT_OVERRIDE:+-e ROOT_OVERRIDE=$ROOT_OVERRIDE} ${TASKS:+-e TASKS=$TASKS} ${JOB_TAG:+-e JOB_TAG=$JOB_TAG} ${MAX_LEN_OVERRIDE:+-e MAX_LEN_OVERRIDE=$MAX_LEN_OVERRIDE}
       --command -- bash -c "groupadd -g $USER_GID lichengrp 2>/dev/null || true && \
useradd -u $USER_UID -g $USER_GID -d /home/lichen -s /bin/bash -M lichen 2>/dev/null || true && \
groupadd -g $LAB_GID dlabapp 2>/dev/null || true && usermod -aG dlabapp lichen && \
su lichen -s /bin/bash $SNAP $EXP")
  # No quotes inside the command: RunAI re-parses it in the pod and drops them, so the script
  # path and its argument go to su as plain words (su passes them on to bash).
  echo "${CMD[*]}"
  [[ "${DRY:-0}" == 1 ]] || SUPPRESS_DEPRECATION_MESSAGE=true "${CMD[@]}"
done
