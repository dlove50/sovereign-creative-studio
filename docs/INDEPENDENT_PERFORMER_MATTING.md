# Independent performer composition

The renderer generates and caches each performer separately. It then extracts an alpha
layer from each complete pass with U2Net human segmentation and foreground RGB matting,
and places those layers on one empty concert backdrop. Generated backgrounds are not
pasted into rectangular stage slices. The uploaded stage reference may already contain
people, so it is not used as the final backdrop in this mode. Shared-pass rendering is
unchanged.

This removes the old rectangular compositing seams; it does not guarantee perfect hair
edges, relighting, precise gesture control, reference-motion transfer or singing lip sync.
Those need real-video acceptance checks. Head/hand/gaze settings guide the generation model.

## Optional CPU runtime

Create `backend/.venv-matting` and install `backend/requirements-matting.txt`. The backend
launches its worker as a separate process with two CPU inference/BLAS threads and explicitly
uses ONNX Runtime's CPU provider. The main backend and ComfyUI environments are unchanged.
Set `PERFORMANCE_MATTING_PYTHON` to override the Python executable and
`PERFORMANCE_MATTING_MODELS` to override the model folder. The default folder on this host
is `/mnt/storage/AI-Models/matting`.

Install `u2net_human_seg.onnx` from
[rembg's upstream release](https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net_human_seg.onnx).
The upstream rembg session requires MD5 `c09ddc2e0104f800e3e1bb4652583d1f`;
the installed file matched that checksum. The model is approximately 168 MiB. Rendering
checks for its presence before generation and the worker verifies the upstream checksum.

- [U2Net upstream](https://github.com/xuebinqin/U-2-Net),
  [Apache-2.0 license](https://github.com/xuebinqin/U-2-Net/blob/master/LICENSE).
- [rembg](https://github.com/danielgatis/rembg), MIT license, pinned 2.0.67.
- [PyMatting](https://github.com/pymatting/pymatting), MIT license, pinned 1.1.16.
- [ONNX Runtime](https://github.com/microsoft/onnxruntime), MIT license, pinned 1.31.0.

No cloud API is used. Generated RGB passes and lossless FFV1 alpha layers are separate
cache entries. Camera/position edits reuse them; changed performer inputs regenerate only
the affected pass. Alpha cache version `u2net-matting-v2` includes RGB fringe refinement.
Partial outputs are never published as complete cache entries. Lossless video caches can
be large; preserve enough free disk space for the requested duration.

## Verification so far

The renderer and engine tests passed (26 tests), including encoded transparent-pixel
composition, independent input keys, cache reuse and selective regeneration. TypeScript
checks passed. Actual 2-second generated passes were recomposited and inspected: the
rectangular seam was removed, but edge halos and tight source framing remained. RGB
matting improved the inspected single-frame edge. Full refined-video acceptance is pending.
