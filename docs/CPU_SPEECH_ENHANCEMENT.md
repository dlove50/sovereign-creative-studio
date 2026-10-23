# CPU speech reverb reduction

Universal Enhance's `dereverb` operation uses NARA-WPE 0.0.11 in a separate CPU-only Python environment. It is weighted linear prediction, not a neural model. It targets reverberant speech; music, sustained singing and already dry recordings may be coloured and require listening comparison. Strength mixes the processed signal with the original (default 0.65). Original media remains a separate version.

Upstream: https://github.com/fgnt/nara_wpe (MIT). Package versions are pinned in `backend/requirements-enhance-audio.txt`.

Linux setup from the backend directory:

```
uv venv .venv-audio-enhance --python 3.13
uv pip install --python .venv-audio-enhance/bin/python -r requirements-enhance-audio.txt
```

Windows uses `.venv-audio-enhance/Scripts/python.exe`. Set `SOVEREIGN_DEREVERB_PYTHON` to override the interpreter. Restart the backend after installation. FFmpeg must be on PATH. The catalog probes the environment and explains missing dependencies.

The CPU worker preserves sample rate, mono/stereo channel count and sample count; writes 24-bit WAV; and processes overlapping eight-second blocks with two BLAS threads. Supported inputs are mono/stereo, at most 96 kHz and 20 minutes. No GPU or model weights are used. This does not remove all room reflections or guarantee perceptual quality.

Validation: a deterministic noisy-room test measured reduced late-tail energy and checked finite output/duration and original preservation. An actual API job chained WPE with EQ and downloaded its output and unchanged source. Natural speech/singing listening QA remains pending. The live backend is intentionally not restarted while a performance render runs; activate changes at the next idle deployment window.
