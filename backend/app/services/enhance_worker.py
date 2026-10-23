"""AI enhancement models for Universal Enhance, run in the isolated GPU Python (the stems venv).

    python enhance_worker.py <op> <params-json> <input> <output>

op: upscale_ai (Real-ESRGAN x2/x4), face_restore (GFPGAN v1.4 + RetinaFace), interpolate_ai (RIFE v4.26).
Images and videos are both accepted (videos are processed frame by frame; audio is copied through).
Prints "PROGRESS <0..1>" lines and a final JSON line. The Sovereign backend never imports this module.

RIFE network (IFNet_HDv3) and warp: Practical-RIFE by hzwer, MIT licence
(https://github.com/hzwer/Practical-RIFE), reproduced below for inference only.
"""
from __future__ import annotations

import json
from fractions import Fraction
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

MODELS = Path(os.environ.get("SOVEREIGN_ENHANCE_MODELS", "/mnt/storage/AI-Models/enhance"))
UPSCALERS = Path(os.environ.get("SOVEREIGN_UPSCALE_MODELS", "/mnt/storage/AI-Models/comfyui/upscale_models"))
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


def progress(x: float) -> None:
    print(f"PROGRESS {min(1.0, max(0.0, x)):.3f}", flush=True)


def ffmpeg() -> str:
    found = shutil.which("ffmpeg")
    if not found:
        raise SystemExit("ffmpeg was not found.")
    return found


# --- Real-ESRGAN (spandrel) -------------------------------------------------------------------

def load_upscaler(scale: int):
    from spandrel import ModelLoader

    path = UPSCALERS / ("RealESRGAN_x2plus.pth" if scale == 2 else "RealESRGAN_x4plus.safetensors")
    model = ModelLoader(device=DEVICE).load_from_file(str(path)).eval()
    return model


@torch.no_grad()
def upscale(model, rgb: np.ndarray, tile: int = 512, pad: int = 16) -> np.ndarray:
    """uint8 HxWx3 -> upscaled uint8, tiled so 4K output fits in VRAM."""
    s = model.scale
    x = torch.from_numpy(rgb).to(DEVICE).permute(2, 0, 1)[None].float() / 255.0
    _, _, h, w = x.shape
    out = torch.zeros((1, 3, h * s, w * s), device=DEVICE)
    for y0 in range(0, h, tile):
        for x0 in range(0, w, tile):
            ya, xa = max(0, y0 - pad), max(0, x0 - pad)
            yb, xb = min(h, y0 + tile + pad), min(w, x0 + tile + pad)
            piece = model(x[:, :, ya:yb, xa:xb])
            ty, tx = (y0 - ya) * s, (x0 - xa) * s
            th, tw = (min(h, y0 + tile) - y0) * s, (min(w, x0 + tile) - x0) * s
            out[:, :, y0 * s:y0 * s + th, x0 * s:x0 * s + tw] = piece[:, :, ty:ty + th, tx:tx + tw]
    return (out[0].clamp(0, 1).permute(1, 2, 0) * 255).round().byte().cpu().numpy()


# --- GFPGAN face restoration ------------------------------------------------------------------

class FaceRestorer:
    def __init__(self, fidelity: float):
        from facexlib.utils.face_restoration_helper import FaceRestoreHelper
        from spandrel import ModelLoader

        self.gfpgan = ModelLoader(device=DEVICE).load_from_file(str(MODELS / "gfpgan" / "GFPGANv1.4.pth")).eval()
        self.helper = FaceRestoreHelper(1, face_size=512, crop_ratio=(1, 1), det_model="retinaface_resnet50",
                                        save_ext="png", use_parse=False, device=DEVICE,
                                        model_rootpath=str(MODELS / "facexlib"))
        self.fidelity = fidelity  # 1 = keep the original face texture, 0 = fully restored

    @torch.no_grad()
    def __call__(self, rgb: np.ndarray) -> tuple[np.ndarray, int]:
        if self.fidelity >= 1.0:
            # Maximum identity fidelity is an explicit request to keep the face.
            # Avoid alignment/paste-back resampling as well as model synthesis.
            return rgb.copy(), 0
        bgr = np.ascontiguousarray(rgb[:, :, ::-1])
        self.helper.clean_all()
        self.helper.read_image(bgr)
        self.helper.get_face_landmarks_5(only_center_face=False, resize=640, eye_dist_threshold=5)
        self.helper.align_warp_face()
        if not self.helper.cropped_faces:
            return rgb, 0
        for crop in self.helper.cropped_faces:
            t = torch.from_numpy(crop[:, :, ::-1].copy()).to(DEVICE).permute(2, 0, 1)[None].float() / 255.0
            restored = self.gfpgan(t)[0].clamp(0, 1)
            # Identity fidelity: blend the restoration with the aligned original face.
            restored = (1 - self.fidelity) * restored + self.fidelity * t[0]
            face = (restored.permute(1, 2, 0) * 255).round().byte().cpu().numpy()[:, :, ::-1]
            self.helper.add_restored_face(np.ascontiguousarray(face))
        self.helper.get_inverse_affine(None)
        out = self.helper.paste_faces_to_input_image()
        return np.ascontiguousarray(out[:, :, ::-1]), len(self.helper.cropped_faces)


# --- RIFE v4.26 (IFNet_HDv3, MIT, hzwer/Practical-RIFE) -----------------------------------------

_grid: dict = {}


def warp(inp, flow):
    key = (str(flow.device), str(flow.size()))
    if key not in _grid:
        hor = torch.linspace(-1.0, 1.0, flow.shape[3], device=flow.device).view(1, 1, 1, flow.shape[3]).expand(flow.shape[0], -1, flow.shape[2], -1)
        ver = torch.linspace(-1.0, 1.0, flow.shape[2], device=flow.device).view(1, 1, flow.shape[2], 1).expand(flow.shape[0], -1, -1, flow.shape[3])
        _grid[key] = torch.cat([hor, ver], 1)
    flow = torch.cat([flow[:, 0:1] / ((inp.shape[3] - 1.0) / 2.0), flow[:, 1:2] / ((inp.shape[2] - 1.0) / 2.0)], 1)
    g = (_grid[key] + flow).permute(0, 2, 3, 1)
    return F.grid_sample(inp, g, mode="bilinear", padding_mode="border", align_corners=True)


def conv(i, o, k=3, s=1, p=1, d=1):
    return nn.Sequential(nn.Conv2d(i, o, k, s, p, dilation=d, bias=True), nn.LeakyReLU(0.2, True))


class Head(nn.Module):
    def __init__(self):
        super().__init__()
        self.cnn0, self.cnn1 = nn.Conv2d(3, 16, 3, 2, 1), nn.Conv2d(16, 16, 3, 1, 1)
        self.cnn2, self.cnn3 = nn.Conv2d(16, 16, 3, 1, 1), nn.ConvTranspose2d(16, 4, 4, 2, 1)
        self.relu = nn.LeakyReLU(0.2, True)

    def forward(self, x):
        return self.cnn3(self.relu(self.cnn2(self.relu(self.cnn1(self.relu(self.cnn0(x)))))))


class ResConv(nn.Module):
    def __init__(self, c, dilation=1):
        super().__init__()
        self.conv = nn.Conv2d(c, c, 3, 1, dilation, dilation=dilation, groups=1)
        self.beta = nn.Parameter(torch.ones((1, c, 1, 1)), requires_grad=True)
        self.relu = nn.LeakyReLU(0.2, True)

    def forward(self, x):
        return self.relu(self.conv(x) * self.beta + x)


class IFBlock(nn.Module):
    def __init__(self, in_planes, c=64):
        super().__init__()
        self.conv0 = nn.Sequential(conv(in_planes, c // 2, 3, 2, 1), conv(c // 2, c, 3, 2, 1))
        self.convblock = nn.Sequential(*[ResConv(c) for _ in range(8)])
        self.lastconv = nn.Sequential(nn.ConvTranspose2d(c, 4 * 13, 4, 2, 1), nn.PixelShuffle(2))

    def forward(self, x, flow=None, scale=1):
        x = F.interpolate(x, scale_factor=1.0 / scale, mode="bilinear", align_corners=False)
        if flow is not None:
            flow = F.interpolate(flow, scale_factor=1.0 / scale, mode="bilinear", align_corners=False) / scale
            x = torch.cat((x, flow), 1)
        feat = self.convblock(self.conv0(x))
        tmp = F.interpolate(self.lastconv(feat), scale_factor=scale, mode="bilinear", align_corners=False)
        return tmp[:, :4] * scale, tmp[:, 4:5], tmp[:, 5:]


class IFNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.block0 = IFBlock(7 + 8, c=192)
        self.block1 = IFBlock(8 + 4 + 8 + 8, c=128)
        self.block2 = IFBlock(8 + 4 + 8 + 8, c=96)
        self.block3 = IFBlock(8 + 4 + 8 + 8, c=64)
        self.block4 = IFBlock(8 + 4 + 8 + 8, c=32)
        self.encode = Head()

    def forward(self, img0, img1, timestep=0.5, scale_list=(16, 8, 4, 2, 1)):
        t = (img0[:, :1].clone() * 0 + 1) * timestep
        f0, f1 = self.encode(img0), self.encode(img1)
        flow = mask = feat = None
        w0, w1 = img0, img1
        for i, block in enumerate([self.block0, self.block1, self.block2, self.block3, self.block4]):
            if flow is None:
                flow, mask, feat = block(torch.cat((img0, img1, f0, f1, t), 1), None, scale=scale_list[i])
            else:
                wf0, wf1 = warp(f0, flow[:, :2]), warp(f1, flow[:, 2:4])
                fd, mask, feat = block(torch.cat((w0, w1, wf0, wf1, t, mask, feat), 1), flow, scale=scale_list[i])
                flow = flow + fd
            w0, w1 = warp(img0, flow[:, :2]), warp(img1, flow[:, 2:4])
        mask = torch.sigmoid(mask)
        return w0 * mask + w1 * (1 - mask)


def load_rife() -> IFNet:
    net = IFNet()
    state = torch.load(MODELS / "rife" / "RIFEv4.26_0921" / "flownet.pkl", map_location="cpu", weights_only=True)
    state = {k.replace("module.", ""): v for k, v in state.items()}
    net.load_state_dict(state, strict=False)
    return net.to(DEVICE).eval()


@torch.no_grad()
def interpolate(net: IFNet, a: np.ndarray, b: np.ndarray, times: list[float]) -> list[np.ndarray]:
    """Frames at the requested fractional times between a and b."""
    h, w, _ = a.shape
    ph, pw = ((h - 1) // 128 + 1) * 128, ((w - 1) // 128 + 1) * 128
    ta = F.pad(torch.from_numpy(a).to(DEVICE).permute(2, 0, 1)[None].float() / 255.0, (0, pw - w, 0, ph - h))
    tb = F.pad(torch.from_numpy(b).to(DEVICE).permute(2, 0, 1)[None].float() / 255.0, (0, pw - w, 0, ph - h))
    frames = []
    for fraction in times:
        if fraction >= 1 - 1e-8:
            frames.append(b)
            continue
        mid = net(ta, tb, timestep=fraction)[0, :, :h, :w]
        frames.append((mid.clamp(0, 1).permute(1, 2, 0) * 255).round().byte().cpu().numpy())
    return frames


# --- Media IO ---------------------------------------------------------------------------------

def probe(path: Path) -> dict:
    probe_bin = shutil.which("ffprobe")
    out = subprocess.run([probe_bin, "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries",
                          "stream=width,height,r_frame_rate,nb_read_packets", "-of", "json", str(path)],
                         capture_output=True, text=True, check=True)
    s = json.loads(out.stdout)["streams"][0]
    num, den = s["r_frame_rate"].split("/")
    return {"w": int(s["width"]), "h": int(s["height"]), "fps": float(num) / float(den),
            "rate": s["r_frame_rate"], "frames": int(s.get("nb_read_packets") or 0)}


def read_image(path: Path) -> np.ndarray:
    from PIL import Image, ImageOps

    with Image.open(path) as im:
        return np.asarray(ImageOps.exif_transpose(im).convert("RGB")).copy()


def write_image(path: Path, rgb: np.ndarray) -> None:
    from PIL import Image

    img = Image.fromarray(rgb)
    img.save(path, quality=95) if path.suffix.lower() in (".jpg", ".jpeg") else img.save(path)


def process_video(src: Path, dst: Path, frame_fn, out_scale: int = 1, out_rate: str | None = None,
                  per_pair=None) -> int:
    info = probe(src)
    w, h = info["w"], info["h"]
    reader = subprocess.Popen([ffmpeg(), "-v", "error", "-i", str(src), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                              stdout=subprocess.PIPE)
    ow, oh = w * out_scale, h * out_scale
    rate = out_rate or info["rate"]
    writer = subprocess.Popen([ffmpeg(), "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{ow}x{oh}",
                               "-r", rate, "-i", "-", "-i", str(src), "-map", "0:v", "-map", "1:a?", "-c:v", "libx264",
                               "-crf", "16", "-preset", "medium", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "256k",
                               "-shortest", str(dst)], stdin=subprocess.PIPE)
    size, n, prev = w * h * 3, 0, None
    written, target_fps = 0, float(Fraction(rate))
    total = max(1, info["frames"])
    while True:
        raw = reader.stdout.read(size)
        if len(raw) < size:
            break
        frame = np.frombuffer(raw, np.uint8).reshape(h, w, 3)
        if per_pair is not None:
            if prev is None:
                writer.stdin.write(frame.tobytes())
                written += 1
            else:
                # Schedule exact output timestamps, including noninteger ratios
                # such as25->60fps, rather than rounding the requested rate.
                fractions = []
                while written / target_fps <= n / info["fps"] + 1e-9:
                    fractions.append((written / target_fps - (n - 1) / info["fps"]) * info["fps"])
                    written += 1
                for mid in per_pair(prev, frame, fractions):
                    writer.stdin.write(mid.tobytes())
            prev = frame
        else:
            writer.stdin.write(frame_fn(frame).tobytes())
            written += 1
        n += 1
        if n % 5 == 0:
            progress(n / total)
    if per_pair is not None and prev is not None:
        # The final source frame owns a full display interval as well.
        while written < round(n * target_fps / info["fps"]):
            writer.stdin.write(prev.tobytes())
            written += 1
    writer.stdin.close()
    reader.wait()
    if writer.wait() != 0:
        raise SystemExit("Encoding the enhanced video failed.")
    return written


def main() -> None:
    op, params, src, dst = sys.argv[1], json.loads(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4])
    is_image = src.suffix.lower() in IMAGE_EXT
    report: dict = {"op": op, "device": str(DEVICE)}
    if op == "upscale_ai":
        model = load_upscaler(int(params.get("scale", 2)))
        report["model"] = f"RealESRGAN x{model.scale}"
        if is_image:
            write_image(dst, upscale(model, read_image(src)))
        else:
            report["frames"] = process_video(src, dst, lambda f: upscale(model, f), out_scale=model.scale)
    elif op == "face_restore":
        restorer = FaceRestorer(float(params.get("fidelity", 0.7)))
        report["model"] = "GFPGAN v1.4 + RetinaFace"
        if is_image:
            out, faces = restorer(read_image(src))
            report["faces"] = faces
            write_image(dst, out)
        else:
            report["frames"] = process_video(src, dst, lambda f: restorer(f)[0])
    elif op == "interpolate_ai":
        if is_image:
            raise SystemExit("Frame interpolation needs a video.")
        net = load_rife()
        info = probe(src)
        target_fps = float(params.get("fps", 60))
        report.update(model="RIFE v4.26", fps=target_fps, multiplier=target_fps / info["fps"])
        report["frames"] = process_video(src, dst, None, out_rate=f"{target_fps:.6f}",
                                         per_pair=lambda a, b, times: interpolate(net, a, b, times))
    else:
        raise SystemExit(f"Unknown op {op}")
    progress(1.0)
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
