"""Build a 75-second five-mode demo from two independently performed vocal sources.

The second input must be a distinct performance, optionally voice-converted;
it must not be a pitch-shifted duplicate of the first. Phrase alignment uses
explicit ASR-reviewed landmarks, with pitch-preserving tempo changes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import wave
from pathlib import Path

import numpy as np

RATE = 44100
DURATION = 75.0
# Source (new melody cover) -> original song landmarks. These are asset-specific,
# not a general aligner; retain both ASR transcripts alongside the demo evidence.
SOURCE = [0, 14.22, 19.42, 25.13, 29.33, 32.69, 34.68, 38.43, 44.27, 47.50, 51.22, 57.54, 61.00, 75.04]
TARGET = [0, 14.64, 18.54, 24.64, 28.54, 32.00, 33.96, 37.64, 43.53, 47.15, 50.77, 57.00, 60.53, 75.00]


def decode(path: Path, *options: str) -> np.ndarray:
    raw = subprocess.run(['ffmpeg', '-v', 'error', *options, '-i', str(path), '-ac', '2', '-ar', str(RATE),
                          '-f', 'f32le', '-'], check=True, capture_output=True).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, 2).copy()


def write(path: Path, data: np.ndarray) -> None:
    with wave.open(str(path), 'wb') as wav:
        wav.setnchannels(2); wav.setsampwidth(2); wav.setframerate(RATE)
        wav.writeframes(np.round(np.clip(data, -1, 1)*32767).astype('<i2').tobytes())


def fit(data: np.ndarray, length: int) -> np.ndarray:
    return np.pad(data[:length], ((0, max(0, length-len(data))), (0, 0)))


def align(path: Path) -> np.ndarray:
    output = np.zeros((round(DURATION*RATE), 2), np.float32)
    weights = np.zeros(len(output), np.float32)
    for i in range(len(SOURCE)-1):
        s0, s1, t0, t1 = SOURCE[i], SOURCE[i+1], TARGET[i], TARGET[i+1]
        tempo = (s1-s0)/(t1-t0)
        left = min(.02, t0); right = min(.02, DURATION-t1)
        start, duration = max(0, s0-left*tempo), (t1-t0+left+right)*tempo
        raw = subprocess.run(['ffmpeg', '-v', 'error', '-ss', str(start), '-t', str(duration), '-i', str(path),
                              '-af', f'rubberband=tempo={tempo}:formant=preserved', '-ac', '2', '-ar', str(RATE),
                              '-f', 'f32le', '-'], check=True, capture_output=True).stdout
        a, b = round((t0-left)*RATE), round((t1+right)*RATE)
        piece = fit(np.frombuffer(raw, np.float32).reshape(-1, 2), b-a)
        gain = np.ones(b-a, np.float32)
        for size, beginning in [(round(left*RATE), True), (round(right*RATE), False)]:
            if size:
                if beginning: gain[:size] = np.linspace(0, 1, size)
                else: gain[-size:] = np.linspace(1, 0, size)
        output[a:b] += piece*gain[:, None]; weights[a:b] += gain
    return output/np.maximum(weights[:, None], 1e-8)


def envelope(length: int, spans: list[tuple[float, float, float]]) -> np.ndarray:
    result = np.zeros(length, np.float32)
    for start, end, level in spans:
        a, b = round(start*RATE), min(length, round(end*RATE))
        gain = np.full(b-a, level, np.float32); fade = min(round(.03*RATE), len(gain)//2)
        if fade:
            ramp = .5-.5*np.cos(np.linspace(0, np.pi, fade))
            gain[:fade] *= ramp; gain[-fade:] *= ramp[::-1]
        result[a:b] = np.maximum(result[a:b], gain)
    return result[:, None]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['female', 'male', 'instrumental', 'out']:
        parser.add_argument('--'+name, required=True, type=Path)
    args = parser.parse_args(); args.out.mkdir(parents=True, exist_ok=True)
    n = round(DURATION*RATE)
    female, male, band = fit(decode(args.female), n), align(args.male), fit(decode(args.instrumental), n)
    if not np.isfinite(female).all() or not np.isfinite(male).all() or not np.isfinite(band).all():
        raise ValueError('Demo sources must contain finite audio samples.')
    if max(abs(female).max(), abs(male).max()) < 1e-5 or min(abs(female).max(), abs(male).max()) < 1e-5:
        raise ValueError('Both independent vocal sources must contain voiced audio.')
    # Match active vocal energy conservatively; preserve headroom in the shared mix.
    active_a = female[round(15*RATE):round(40*RATE)]
    active_b = male[round(28.6*RATE):round(41.5*RATE)]
    balance = float(np.clip(np.sqrt(np.mean(active_a**2))/max(np.sqrt(np.mean(active_b**2)), 1e-8), .5, 3))
    male *= balance
    a_spans = [(14.4, 27.8, 1), (43.2, 54.0, 1), (55.35, 57.75, 1)]
    b_spans = [(27.8, 41.9, 1), (43.2, 50.77, .8), (50.77, 54.0, .4), (57.75, 60.7, 1)]
    a, b = female*envelope(n, a_spans), male*envelope(n, b_spans)
    master = .85*band+a+b
    headroom = min(1., .95/max(float(abs(data).max()) for data in (master, a, b, male)))
    for name, data in [('singer-a-stem.wav', a), ('singer-b-stem.wav', b), ('master-distinct-duet.wav', master),
                       ('aligned-independent-b.wav', male)]:
        write(args.out/name, data*headroom)
    modes = [{'mode': 'shared_stage', 'start': 0, 'end': 14.4},
             {'mode': 'alternating', 'start': 14.4, 'end': 41.9},
             {'mode': 'harmony', 'start': 43.2, 'end': 50.77},
             {'mode': 'lead_background', 'start': 50.77, 'end': 54.0},
             {'mode': 'call_response', 'start': 55.35, 'end': 60.7},
             {'mode': 'shared_stage', 'start': 60.7, 'end': DURATION}]
    manifest = {'duration': DURATION, 'sample_rate': RATE, 'male_balance': balance, 'mix_gain': headroom,
                'peak': float(abs(master*headroom).max()), 'source_landmarks': SOURCE, 'target_landmarks': TARGET,
                'modes': modes, 'a_spans': a_spans, 'b_spans': b_spans,
                'sources': {key: {'path': str(value), 'sha256': hashlib.sha256(value.read_bytes()).hexdigest()}
                            for key,value in [('female',args.female),('male',args.male),('instrumental',args.instrumental)]},
                'method': 'Two independent generated performances; B reference-voice conversion and octave transposition; phrase tempo alignment; original instrumental plus gated vocals.',
                'quality_status': 'Numeric media preparation only; final singing, handoff, silence and lip-sync review is still required.'}
    (args.out/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(json.dumps(manifest))


if __name__ == '__main__':
    main()
