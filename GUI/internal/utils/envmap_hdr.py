import argparse
import math
import os
from collections import OrderedDict
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np
import torch
from pathlib import Path
import os.path as osp
import sys

root_dir = Path(__file__).resolve().parents[2]
gmnet_codes_dir = root_dir / "GMNet" / "codes"
sys.path.append(str(gmnet_codes_dir))

from models import networks

"""
LDR/SDR -> HDR inference with GMNet.

Important parameters:

- preset:
  Selects the checkpoint and the training-time constants that should stay paired.
  synthetic uses G_synthetic.pth, scale=1, peak=8.
  realworld uses G_realworld.pth, scale=2, peak=5.

- peak:
  In this project, peak is the HDR peak / SDR white-level ratio used when training.
  It is not the external metadata Qmax. It only defines the maximum gain exponent
  range for the normalized QGM branch:

      default_Qmax_range = log2(peak)

  So synthetic peak=8 means the no-metadata QGM branch can represent about
  log2(8)=3 stops of gain; realworld peak=5 means about log2(5)=2.32 stops.

- qmax:
  Optional absolute gain exponent. If you do not know Qmax, leave it unset and use
  pred_qgm, which includes GMNet's own global Qmax estimate. If you do know a
  trustworthy Qmax, pass --qmax and the script will use pred_gm * qmax instead.

- normalize-by-peak:
  Leave this OFF for ordinary LDR2HDR/env-map export. Turning it on reproduces the
  normalized scale used by codes/test.py: HDR = SDR^2.2 * 2^gain / peak.
"""


PRESETS = {
    "synthetic": {
        "checkpoint": root_dir / "GMNet" / "checkpoints" / "G_synthetic.pth",
        "scale": 1,
        "peak": 8.0,
    },
    "realworld": {
        "checkpoint": root_dir / "GMNet" / "checkpoints" / "G_realworld.pth",
        "scale": 2,
        "peak": 5.0,
    },
}


def build_opt(args):
    return {
        "network_G": {
            "which_model_G": "GMNet",
            "in_nc": 3,
            "out_nc": 1,
            "nf": 64,
            "nb": 16,
            "act_type": "relu",
        }
    }


def load_network(net, checkpoint, device):
    state = torch.load(checkpoint, map_location=device)
    clean_state = OrderedDict()
    for key, value in state.items():
        clean_state[key[7:] if key.startswith("module.") else key] = value
    net.load_state_dict(clean_state, strict=False)
    net.eval()


def list_images(input_path):
    exts = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
    if isinstance(input_path, str):
        input_path = Path(input_path)
    if input_path.is_dir():
        paths = []
        for file_path in input_path.iterdir():
            if file_path.is_file() and file_path.suffix.lower() in exts:
                paths.append(file_path.as_posix())
        return sorted(paths)
    return [input_path]


def to_tensor_rgb(img_bgr):
    img_rgb = img_bgr[:, :, [2, 1, 0]]
    tensor = torch.from_numpy(np.ascontiguousarray(img_rgb.transpose(2, 0, 1))).float()
    return tensor.unsqueeze(0)


def infer_one(net, img_path, out_dir, scale, peak, device, save_tif, qmax, normalize_by_peak):
    img = cv2.imread(img_path, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise RuntimeError("Failed to read image: {}".format(img_path))
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    if img.shape[2] > 3:
        img = img[:, :, :3]

    if img.dtype == np.uint8:
        sdr_bgr = img.astype(np.float32) / 255.0
    elif img.dtype == np.uint16:
        sdr_bgr = img.astype(np.float32) / 65535.0
    else:
        sdr_bgr = img.astype(np.float32)

    lq_bgr = cv2.resize(
        sdr_bgr,
        None,
        fx=1.0 / scale,
        fy=1.0 / scale,
        interpolation=cv2.INTER_CUBIC,
    ).clip(0, 1)
    thumb_bgr = cv2.resize(sdr_bgr, (256, 256), interpolation=cv2.INTER_CUBIC).clip(0, 1)

    lq = to_tensor_rgb(lq_bgr).to(device)
    thumb = to_tensor_rgb(thumb_bgr).to(device)

    with torch.no_grad():
        pred_gm, pred_qgm = net((lq, thumb))

    if qmax is None:
        gain_exp = pred_qgm.detach().float().cpu().numpy()[0, 0]
        gain_exp = cv2.resize(gain_exp, (sdr_bgr.shape[1], sdr_bgr.shape[0]), interpolation=cv2.INTER_LINEAR)
        gain_exp = np.clip(gain_exp[:, :, np.newaxis], 0, 1) * np.log2(peak)
    else:
        gain_map = pred_gm.detach().float().cpu().numpy()[0, 0]
        gain_map = cv2.resize(gain_map, (sdr_bgr.shape[1], sdr_bgr.shape[0]), interpolation=cv2.INTER_LINEAR)
        gain_exp = np.clip(gain_map[:, :, np.newaxis], 0, 1) * qmax

    linear_sdr_bgr = np.power(np.clip(sdr_bgr, 0, 1), 2.2)
    hdr_bgr = linear_sdr_bgr * np.power(2, gain_exp)
    if normalize_by_peak:
        hdr_bgr = hdr_bgr / peak
    hdr_bgr = hdr_bgr.astype(np.float32)

    base = osp.splitext(osp.basename(img_path))[0]
    hdr_path = osp.join(out_dir, "{}.hdr".format(base))
    cv2.imwrite(hdr_path, hdr_bgr)
    if save_tif:
        cv2.imwrite(
            osp.join(out_dir, "{}.tif".format(base)),
            hdr_bgr,
            [cv2.IMWRITE_TIFF_COMPRESSION, 1],
        )
    return hdr_path


@dataclass
class EnvMapSceneEstimate:
    qmax: float
    scene_type: str       # human-readable label shown in UI
    confidence: str       # "high" | "medium" | "low"


def estimate_qmax_from_ldr_envmap(
    ldr_path: str,
    default_qmax: float = 8.0,
) -> EnvMapSceneEstimate:
    """Automatically estimate HDR qmax from a captured LDR equirectangular envmap.

    Analyses four signals from the 8-bit PNG rendered by the 3DGS pipeline:
      1. Sky ratio     – upper/lower hemisphere luminance ratio (open sky → >1.5)
      2. B/R ratio     – colour temperature in bright pixels (cool=outdoor, warm=indoor)
      3. Saturation topology – connected-component analysis of near-white pixels:
           * single tight blob in upper hemisphere → direct sun
           * diffuse upper brightness → open sky / overcast
           * blobs concentrated in lower hemisphere → indoor light fixtures
      4. Sky brightness – fraction of upper-hemisphere pixels above 0.80

    Physical qmax reference (stops above SDR white):
      Direct sun outdoor   14–18 EV
      Clear sky / no sun    9–13 EV
      Overcast outdoor      7–10 EV
      Indoor bright         4–7  EV
      Indoor dim            2–5  EV
    """
    img_bgr = cv2.imread(str(ldr_path), cv2.IMREAD_COLOR)
    if img_bgr is None:
        return EnvMapSceneEstimate(default_qmax, "unknown (load failed)", "low")

    img = img_bgr.astype(np.float32) / 255.0   # [H, W, 3] BGR in [0, 1]
    H, W = img.shape[:2]

    # Perceptual luminance (works in gamma-compressed space for classification)
    lum = 0.2126 * img[:, :, 2] + 0.7152 * img[:, :, 1] + 0.0722 * img[:, :, 0]

    # --- Signal 1: sky ratio ---
    upper_mean = lum[: H // 2, :].mean()
    lower_mean = lum[H // 2 :, :].mean() + 1e-4
    sky_ratio = upper_mean / lower_mean

    # --- Signal 2: colour temperature of bright pixels ---
    bright_mask = lum > 0.5
    if bright_mask.any():
        b_bright = img[:, :, 0][bright_mask].mean()   # Blue channel (BGR)
        r_bright = img[:, :, 2][bright_mask].mean() + 1e-4
        br_ratio = b_bright / r_bright   # >0.95 cool/outdoor, <0.85 warm/indoor
    else:
        br_ratio = 1.0

    # --- Signal 3: saturation topology ---
    sat_binary = (lum > 0.97).astype(np.uint8)
    sat_frac = sat_binary.mean()
    n_blobs, labeled, stats, centroids = cv2.connectedComponentsWithStats(sat_binary)
    # n_blobs includes background as label 0; real blobs are 1..n_blobs-1
    n_real_blobs = n_blobs - 1
    if n_real_blobs > 0:
        blob_areas = stats[1:, cv2.CC_STAT_AREA]          # exclude background
        blob_cy    = centroids[1:, 1]                      # y-centroid per blob
        largest_idx  = int(np.argmax(blob_areas))
        largest_area = blob_areas[largest_idx]
        largest_cy   = blob_cy[largest_idx]
        total_sat    = max(float(sat_binary.sum()), 1.0)
        # Point source ratio: how dominant is the single largest blob?
        psr = largest_area / total_sat
        # Is the largest blob in the upper hemisphere?
        largest_in_upper = largest_cy < H / 2
        # Blob compactness: very small angular blob → sun candidate
        blob_pixel_frac = largest_area / (H * W)
    else:
        psr = 0.0
        largest_in_upper = False
        blob_pixel_frac = 0.0

    # Saturation broken down by hemisphere
    sat_upper = sat_binary[: H // 2, :].mean()
    sat_lower = sat_binary[H // 2 :, :].mean()

    # --- Signal 4: sky brightness (fraction of upper hemisphere > 0.80) ---
    sky_bright_upper = (lum[: H // 2, :] > 0.80).mean()

    # ------------------------------------------------------------------ #
    #  Classification rules                                                #
    # ------------------------------------------------------------------ #

    # Direct sun: single dominant blob in sky hemisphere, sky brighter than ground.
    # sky_ratio > 1.0 is required — a courtyard or room with a window has a bright
    # upper-hemisphere blob but the lower hemisphere (walls/ground) is still brighter.
    # bpf < 0.15 allows for bloom; a pure 1024×512 sun disk is ~1 px but 3DGS bloom
    # can widen it to several percent of the image.
    has_sun = (
        n_real_blobs >= 1
        and psr > 0.40                       # one blob accounts for >40 % of sat pixels
        and largest_in_upper                  # in the sky half
        and blob_pixel_frac < 0.15           # not a wall-filling diffuse region
        and sky_ratio > 1.0                  # sky must actually be brighter than ground
        and (sky_ratio > 1.6 or sky_bright_upper > 0.08)
    )

    # Open sky: bright diffuse upper hemisphere without a single dominant blob.
    # br > 0.70 excludes obviously warm indoor scenes (museum, warm-lit rooms).
    # Two sub-cases: diffuse (psr < 0.3, e.g. dappled forest canopy) vs open (psr ≥ 0.3).
    has_open_sky = (
        sky_bright_upper > 0.15
        and sky_ratio > 1.5
        and br_ratio > 0.70
    )
    sky_is_diffuse = has_open_sky and psr < 0.30   # e.g. forest canopy, patchy clouds

    # Moderate outdoor: some sky, not blazing.
    # Warm tint (br < 0.75) is a counter-indicator: likely an indoor skylight.
    is_outdoor_moderate = sky_ratio > 1.55 and sky_bright_upper > 0.05 and br_ratio > 0.75

    # Flat diffuse overcast: nearly uniform luminance, minimal saturation.
    # Covers snow, fog, overcast days where sky_ratio ≈ 1.
    is_overcast_flat = (
        abs(sky_ratio - 1.0) < 0.25         # sky and ground roughly equal
        and sat_frac < 0.005                 # almost nothing is clipped
        and upper_mean > 0.15               # scene is reasonably bright
        and br_ratio > 0.80                 # not warm indoor
    )

    # Indoor with visible artificial lights: bright blobs in lower hemisphere.
    # 1.5× threshold (relaxed from 1.8×) catches stained-glass interiors and bright studios.
    is_indoor_lit = (
        sat_lower > sat_upper * 1.5          # bright objects below the horizon
        and n_real_blobs > 3                  # multiple separate fixtures
        and sat_frac > 0.005
    )

    # Mixed: moderate sky gradient but light sources are indoors (room with window).
    is_mixed_indoor_sky = (
        sky_ratio > 1.35
        and sky_bright_upper > 0.04
        and is_indoor_lit
    )

    # Assign qmax and label
    if has_sun:
        # sun disk detected; qmax 14 instead of 16 to avoid 5+ EV overestimate for
        # lower-elevation suns (sunset). Sunrise (true ~17 EV) is slightly under but
        # GMNet's gain_map will be near-1 there anyway.
        qmax = 14.0
        label = "outdoor / direct sun"
        conf = "high"
    elif has_open_sky and not sky_is_diffuse and br_ratio > 0.92:
        # Open cool sky: night with city glow, clear daytime sky without visible sun.
        qmax = 11.0
        label = "outdoor / clear sky or night"
        conf = "high"
    elif has_open_sky and not sky_is_diffuse:
        # Warm open sky: sunset/golden hour without visible sun disk.
        qmax = 9.5
        label = "outdoor / sky (warm/golden)"
        conf = "medium"
    elif sky_is_diffuse:
        # Dappled sky through canopy / patchy overcast: lower peak than open sky.
        qmax = 7.5
        label = "outdoor / dappled sky (forest/canopy)"
        conf = "medium"
    elif is_outdoor_moderate and not is_indoor_lit:
        qmax = 7.5
        label = "outdoor / overcast or hazy"
        conf = "medium"
    elif is_overcast_flat:
        # Flat overcast (snow, fog): minimal dynamic range above SDR.
        qmax = 5.0
        label = "outdoor / flat overcast (snow/fog)"
        conf = "medium"
    elif is_mixed_indoor_sky:
        # Indoor space with a window.
        qmax = 6.5
        label = "indoor / skylit or windowed"
        conf = "medium"
    elif is_indoor_lit and sat_frac > 0.10:
        # Very high saturation fraction: extremely bright sources (tunnel, industrial).
        qmax = 7.5
        label = "indoor / very bright (tunnel/industrial)"
        conf = "high"
    elif is_indoor_lit and sat_frac > 0.02:
        qmax = 5.5
        label = "indoor / bright artificial"
        conf = "high"
    elif is_indoor_lit:
        qmax = 4.5
        label = "indoor / moderate artificial"
        conf = "high"
    elif sky_bright_upper > 0.10:
        # Sky is visible overhead but not dominant (enclosed courtyard, canyon, atrium).
        qmax = 5.5
        label = "outdoor / enclosed (courtyard/atrium)"
        conf = "medium"
    elif sky_ratio < 1.15:
        qmax = 4.0
        label = "indoor / dim"
        conf = "medium"
    else:
        qmax = default_qmax
        label = "unknown"
        conf = "low"

    return EnvMapSceneEstimate(qmax=round(qmax, 1), scene_type=label, confidence=conf)


def infer_hdr(input_path, out_dir, preset="synthetic", checkpoint=None, scale=None, peak=None, gpu=0, save_tif=False, qmax=None, normalize_by_peak=False):
    preset = PRESETS[preset]
    checkpoint = checkpoint or preset["checkpoint"]
    scale = scale if scale is not None else preset["scale"]
    peak = peak if peak is not None else preset["peak"]

    device = torch.device("cuda:{}".format(gpu) if gpu >= 0 and torch.cuda.is_available() else "cpu")
    os.makedirs(out_dir, exist_ok=True)

    opt = build_opt(argparse.Namespace(preset=preset, checkpoint=checkpoint, scale=scale, peak=peak))
    net = networks.define_G(opt).to(device)
    load_network(net, checkpoint, device)

    paths = list_images(input_path)
    if not paths:
        raise RuntimeError("No input images found: {}".format(input_path))

    # qmax_msg = "network-estimated" if qmax is None else str(qmax)
    # print("Device: {} | preset: {} | scale: {} | peak: {} | qmax: {}".format(device, preset, scale, peak, qmax_msg))
    for img_path in paths:
        infer_one(
            net,
            img_path,
            out_dir,
            scale,
            peak,
            device,
            save_tif,
            qmax,
            normalize_by_peak,
        )
    