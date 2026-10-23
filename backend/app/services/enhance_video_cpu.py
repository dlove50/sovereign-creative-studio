"""CPU video finishing: motion-gated detail and stable per-shot colour matching.

These are bounded classical adjustments, not learned detail recovery. The first
shot is the colour reference; creative lighting changes may warrant less strength.
Audio is stream-copied, and variable-rate sources are rejected rather than retimed.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ['OMP_NUM_THREADS'] = '2'
os.environ['OPENBLAS_NUM_THREADS'] = '2'


def detail(frame, previous, amount):
    import cv2
    import numpy as np
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    small = cv2.resize(gray, (max(16, frame.shape[1] // 4), max(16, frame.shape[0] // 4)))
    gate = np.ones(gray.shape, np.float32)
    if previous is not None:
        flow = cv2.calcOpticalFlowFarneback(previous, small, None, .5, 3, 15, 3, 5, 1.2, 0)
        speed = np.linalg.norm(flow, axis=2) * 4
        gate = cv2.resize(1 / (1 + speed * speed), (frame.shape[1], frame.shape[0]))
        gate = cv2.GaussianBlur(gate, (0, 0), 1.5)
    image = frame.astype(np.float32)
    residual = image - cv2.GaussianBlur(image, (0, 0), 1)
    # Bound halos even at the strongest setting.
    return np.clip(image + amount * gate[..., None] * np.clip(residual, -16, 16), 0, 255).astype('uint8'), small


def statistics(frame):
    import cv2
    import numpy as np
    thumb = cv2.resize(frame, (160, 90))
    lab = cv2.cvtColor(thumb.astype(np.float32) / 255, cv2.COLOR_BGR2LAB)
    return lab.mean(axis=(0, 1)), np.maximum(lab.std(axis=(0, 1)), 2), thumb


def match(frame, source, reference, strength):
    import cv2
    import numpy as np
    lab = cv2.cvtColor(frame.astype(np.float32) / 255, cv2.COLOR_BGR2LAB)
    scale = np.clip(reference[1] / source[1], .8, 1.25)
    shift = np.clip(reference[0] - source[0], [-12, -10, -10], [12, 10, 10])
    corrected = (lab - source[0]) * scale + source[0] + shift
    lab = lab * (1 - strength) + corrected * strength
    return np.clip(cv2.cvtColor(lab.astype(np.float32), cv2.COLOR_LAB2BGR) * 255, 0, 255).astype('uint8')


def process(operation: str, params: dict, source: Path, destination: Path):
    import cv2
    import numpy as np
    cv2.setNumThreads(2)
    strength = float(params.get('amount' if operation == 'motion_sharpen' else 'strength', .5))
    if operation not in {'motion_sharpen', 'shot_match'} or not 0 <= strength <= 1:
        raise ValueError('Unsupported operation or strength outside 0..1.')
    probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
        '-show_entries', 'stream=width,height,avg_frame_rate:frame=best_effort_timestamp_time', '-of', 'json', str(source)]))
    stream = probe['streams'][0]
    numerator, denominator = map(int, stream['avg_frame_rate'].split('/'))
    fps = numerator / denominator
    timestamps = np.array([float(f['best_effort_timestamp_time']) for f in probe.get('frames', [])])
    if not len(timestamps) or fps <= 0 or (len(timestamps) > 1 and np.max(np.abs(np.diff(timestamps) - 1 / fps)) > .002):
        raise ValueError('CPU finishing requires constant-rate video; original retained.')
    cap = cv2.VideoCapture(str(source))
    shots = []
    if operation == 'shot_match':
        previous = None
        for index in range(len(timestamps)):
            ok, frame = cap.read()
            if not ok:
                raise ValueError('Incomplete source video.')
            mean, std, thumb = statistics(frame)
            cut = previous is None or np.mean(np.abs(thumb.astype(float) - previous.astype(float))) > 20
            if cut:
                shots.append({'start': index, 'means': [], 'stds': []})
            shots[-1]['means'].append(mean)
            shots[-1]['stds'].append(std)
            previous = thumb
        for shot in shots:
            shot['stats'] = (np.median(shot.pop('means'), axis=0), np.median(shot.pop('stds'), axis=0))
        cap.release()
        cap = cv2.VideoCapture(str(source))
    try:
        with tempfile.TemporaryDirectory(prefix='sovereign_video_cpu_') as tmp:
            silent = Path(tmp) / 'video.mp4'
            encoder = subprocess.Popen(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'bgr24',
                '-s', f"{stream['width']}x{stream['height']}", '-r', stream['avg_frame_rate'], '-i', '-',
                '-an', '-c:v', 'libx264', '-threads', '2', '-crf', '17', '-pix_fmt', 'yuv420p', str(silent)], stdin=subprocess.PIPE)
            previous = None
            shot_index = 0
            try:
                for index in range(len(timestamps)):
                    ok, frame = cap.read()
                    if not ok:
                        raise ValueError('Incomplete source video.')
                    if operation == 'motion_sharpen':
                        frame, previous = detail(frame, previous, strength)
                    else:
                        if shot_index + 1 < len(shots) and index >= shots[shot_index + 1]['start']:
                            shot_index += 1
                        if shot_index:
                            frame = match(frame, shots[shot_index]['stats'], shots[0]['stats'], strength)
                    encoder.stdin.write(frame.tobytes())
                    if index % max(1, round(fps)) == 0:
                        print(f'PROGRESS {(index + 1) / len(timestamps):.4f}', flush=True)
                encoder.stdin.close()
                if encoder.wait(timeout=180):
                    raise ValueError('Video encoder failed.')
            finally:
                if encoder.poll() is None:
                    encoder.kill()
                    encoder.wait()
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(silent), '-i', str(source),
                '-map', '0:v:0', '-map', '1:a?', '-c', 'copy', '-map_metadata', '1', '-movflags', '+faststart',
                str(destination)], check=True, timeout=180)
    finally:
        cap.release()
    print(json.dumps({'operation': operation, 'frames': len(timestamps), 'fps': fps,
                      'shots': [s['start'] for s in shots], 'strength': strength}), flush=True)


if __name__ == '__main__':
    process(sys.argv[1], json.loads(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]))
