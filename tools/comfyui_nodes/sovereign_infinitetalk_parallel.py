"""Sovereign InfiniteTalk (parallel voices): two-speaker InfiniteTalk where both voices share ONE timeline.

ComfyUI's WanInfiniteTalkToVideo combines two speakers in MultiTalk's "add" layout: speaker 2's audio is
placed AFTER speaker 1's (a turn-taking conversation). Sovereign's Multi-Performer Director passes each
performer's audio already aligned to the song (silence where they are not singing), so the voices must be
laid out in parallel ("para"): frame t of speaker 2 is song time t, exactly like speaker 1. With "add",
speaker 2 received zeros or the wrong slice of their voice in every window.

This node runs the stock node unchanged (masks, motion frames, patches) and only rebuilds the audio
embedding in the parallel layout, padding with each track's own first frame (silence) instead of zeros.
Install: copy into ComfyUI/custom_nodes/. Written by Claude for Sovereign Creative Studio, 2026-10-21.
"""
from __future__ import annotations

import logging

import torch
from typing_extensions import override

from comfy.ldm.wan.model_multitalk import project_audio_features
from comfy_api.latest import ComfyExtension, io
from comfy_extras import nodes_wan


def _encode(audio_encoder_output) -> torch.Tensor:
    layers = audio_encoder_output["encoded_audio_all_layers"]
    encoded = torch.stack(layers, dim=0).squeeze(1)[1:]  # [num_layers, T, 512]
    return nodes_wan.linear_interpolation(encoded, input_fps=50, output_fps=25).movedim(0, 1)  # [T, layers, 512]


class SovereignInfiniteTalkParallel(nodes_wan.WanInfiniteTalkToVideo):
    @classmethod
    def define_schema(cls):
        schema = nodes_wan.WanInfiniteTalkToVideo.define_schema()
        schema.node_id = "SovereignInfiniteTalkParallel"
        schema.display_name = "Sovereign InfiniteTalk (parallel voices)"
        return schema

    @classmethod
    def execute(cls, mode, model, model_patch, positive, negative, vae, width, height, length, audio_encoder_output_1,
                motion_frame_count, start_image=None, previous_frames=None, audio_scale=None,
                clip_vision_output=None, audio_encoder_output_2=None, mask_1=None, mask_2=None) -> io.NodeOutput:
        out = super().execute(mode, model, model_patch, positive, negative, vae, width, height, length,
                              audio_encoder_output_1, motion_frame_count, start_image=start_image,
                              previous_frames=previous_frames, audio_scale=audio_scale,
                              clip_vision_output=clip_vision_output, audio_encoder_output_2=audio_encoder_output_2,
                              mask_1=mask_1, mask_2=mask_2)
        second = mode.get("audio_encoder_output_2") if mode.get("mode") == "two_speakers" else audio_encoder_output_2
        if second is None:
            return out  # one speaker: nothing to re-align
        model_patched = out.args[0]
        tracks = [_encode(audio_encoder_output_1), _encode(second)]
        n = max(t.shape[0] for t in tracks)
        tracks = [t if t.shape[0] == n else torch.cat([t, t[:1].repeat(n - t.shape[0], *([1] * (t.dim() - 1)))])
                  for t in tracks]
        start = previous_frames.shape[0] - motion_frame_count if previous_frames is not None else 0
        embeds = project_audio_features(model_patch.model.audio_proj, tracks, start, start + length)
        model_patched.model_options["transformer_options"]["audio_embeds"] = embeds.to(model_patched.model_dtype())
        logging.info(f"Sovereign InfiniteTalk: parallel voices, audio frames {start} - {start + length}")
        return out


class SovereignExtension(ComfyExtension):
    @override
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return [SovereignInfiniteTalkParallel]


async def comfy_entrypoint() -> SovereignExtension:
    return SovereignExtension()
