#!/usr/bin/env bash
# Download the MiniMax H3 files Sovereign needs (ComfyUI-repackaged, Comfy-Org/MiniMax-H3).
# Resumable: re-run it any time; finished files are skipped, partial ones continue.
# Chosen for an RTX 5070 Ti (16 GB) with PyTorch cu130 (README: prefer int8_convrot) and
# the NVFP4 text encoder. About 70 GB in total. Licence: MiniMax H3 Community License
# (excludes the US, EU, UK and South Korea; Canada is allowed; commercial use < US$20M).
set -u
BASE="https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main"
DEST="${H3_DEST:-/c/Users/David/ComfyUI-Shared/models}"
LOG="${H3_LOG:-$DEST/../minimax_h3_download.log}"

# folder/file, smallest and most useful first so partial progress is already usable.
FILES=(
  embeddings/minimaxh3_art_is_explosion.safetensors
  embeddings/minimaxh3_blooming_flowers.safetensors
  embeddings/minimaxh3_bullet_time.safetensors
  embeddings/minimaxh3_dark_magic.safetensors
  embeddings/minimaxh3_fire_breath.safetensors
  embeddings/minimaxh3_four_seasons.safetensors
  embeddings/minimaxh3_kiss_camera.safetensors
  embeddings/minimaxh3_spiral_ascent.safetensors
  embeddings/minimaxh3_storm_magic.safetensors
  embeddings/minimaxh3_truman_show.safetensors
  vae/minimax_h3_audio_vae_fp32.safetensors
  vae/minimax_h3_video_vae_fp16.safetensors
  loras/minimax_h3_fl2v_turbo_4step_v1.0_768p_comfyui_bf16.safetensors
  text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors
  diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors
  model_patches/minimax_h3_fun_controlnet_union_pruned_int8_convrot.safetensors
  loras/minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors
  diffusion_models/minimax_h3_ref2va_pruned_int8_convrot.safetensors
  loras/minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors
)

log() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }
mkdir -p "$DEST"
fail=0
for rel in "${FILES[@]}"; do
  out="$DEST/$rel"
  mkdir -p "$(dirname "$out")"
  want=$(curl -sIL "$BASE/$rel" | tr -d '\r' | awk 'tolower($1)=="x-linked-size:"{s=$2} tolower($1)=="content-length:"{c=$2} END{print (s?s:c)}')
  if [ -z "$want" ]; then log "SKIP (size lookup failed): $rel"; fail=1; continue; fi
  have=$(stat -c %s "$out" 2>/dev/null || echo 0)
  if [ "$have" = "$want" ]; then log "have  $rel"; continue; fi
  log "get   $rel ($((want / 1000000)) MB)"
  for attempt in 1 2 3 4 5 6; do
    curl -sL --fail -C - -o "$out.part" "$BASE/$rel" && break
    log "retry $attempt for $rel"; sleep 10
  done
  got=$(stat -c %s "$out.part" 2>/dev/null || echo 0)
  if [ "$got" = "$want" ]; then mv "$out.part" "$out"; log "done  $rel"
  else log "FAILED $rel (got $got of $want)"; fail=1; fi
done
[ "$fail" = 0 ] && log "ALL DONE" || log "FINISHED WITH ERRORS (re-run to resume)"
exit "$fail"
