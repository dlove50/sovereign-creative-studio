"""CPU-only speech dereverberation using NARA-WPE (MIT).

CLI matches the enhancement worker: dereverb params-json input output.
WPE reduces predictable late reverberation; it is not a neural model and can
colour music. Originals are retained by the caller. Bounded overlapping blocks
avoid fitting one predictor over a whole long recording.
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# A background cleanup must not consume every CPU thread during video generation.
os.environ['OPENBLAS_NUM_THREADS'] = '2'
os.environ['OMP_NUM_THREADS'] = '2'


def process(source: Path, destination: Path, strength: float = .65) -> None:
    import numpy as np
    import soundfile as sf
    from nara_wpe.utils import stft, istft
    from nara_wpe.wpe import wpe
    if not 0 <= strength <= 1:
        raise ValueError('Reverb reduction strength must be between 0 and 1.')
    with tempfile.TemporaryDirectory(prefix='sovereign_wpe_') as tmp:
        decoded = Path(tmp) / 'source.wav'
        subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', str(source), '-vn',
                        '-c:a', 'pcm_f32le', str(decoded)], check=True, timeout=180)
        info = sf.info(decoded)
        if info.channels > 2 or info.duration > 1200 or info.samplerate > 96000:
            raise ValueError('Speech reverb reduction supports mono/stereo audio up to 20 minutes and 96 kHz.')
        audio, rate = sf.read(decoded, dtype='float32', always_2d=True)
        if not len(audio) or not np.isfinite(audio).all():
            raise ValueError('Audio must contain finite samples.')
        result = np.zeros_like(audio)
        weights = np.zeros(len(audio), dtype=np.float32)
        block = 8 * rate
        overlap = min(rate // 2, block // 4)
        for start in range(0, len(audio), block - overlap):
            piece = audio[start:start + block]
            cleaned = piece.copy()
            if strength and len(piece) >= 2048 and np.max(np.abs(piece)) > 1e-7:
                for channel in range(piece.shape[1]):
                    spectrum = stft(piece[:, channel], size=1024, shift=256).T[:, None, :].astype('complex64')
                    prediction = wpe(spectrum, taps=16, delay=3, iterations=3, psd_context=1)
                    restored = istft(prediction[:, 0, :].T, size=1024, shift=256)
                    restored = np.pad(restored, (0, max(0, len(piece) - len(restored))))[:len(piece)]
                    if not np.isfinite(restored).all():
                        raise ValueError('Reverb processor produced non-finite audio; original retained.')
                    cleaned[:, channel] = (1 - strength) * piece[:, channel] + strength * restored
            fade = np.ones(len(piece), dtype=np.float32)
            n = min(overlap, len(piece))
            if start:
                fade[:n] *= np.linspace(0, 1, n, dtype=np.float32)
            if start + block < len(audio):
                fade[-n:] *= np.linspace(1, 0, n, dtype=np.float32)
            result[start:start+len(piece)] += cleaned * fade[:, None]
            weights[start:start+len(piece)] += fade
            print(f'PROGRESS {min(1, (start+len(piece))/len(audio)):.3f}', flush=True)
        result /= np.maximum(weights[:, None], 1e-7)
        sf.write(destination, np.clip(result, -1, 1), rate, subtype='PCM_24')
        print(json.dumps({'engine': 'NARA-WPE', 'version': '0.0.11', 'rate': rate,
                          'channels': info.channels, 'frames': len(result), 'strength': strength}))


if __name__ == '__main__':
    if len(sys.argv) != 5 or sys.argv[1] != 'dereverb':
        raise SystemExit('Usage: dereverb_worker.py dereverb params-json input output')
    process(Path(sys.argv[3]), Path(sys.argv[4]), float(json.loads(sys.argv[2]).get('strength', .65)))
