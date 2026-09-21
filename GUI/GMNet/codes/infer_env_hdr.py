import argparse
import os
import os.path as osp
from collections import OrderedDict

import cv2
import numpy as np
import torch

import models.networks as networks


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
        "checkpoint": "../checkpoints/G_synthetic.pth",
        "scale": 1,
        "peak": 8.0,
    },
    "realworld": {
        "checkpoint": "../checkpoints/G_realworld.pth",
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
    if osp.isdir(input_path):
        paths = []
        for dirpath, _, filenames in os.walk(input_path):
            for filename in sorted(filenames):
                if osp.splitext(filename)[1].lower() in exts:
                    paths.append(osp.join(dirpath, filename))
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


def main():
    parser = argparse.ArgumentParser(
        description="Convert LDR/SDR images to HDR using GMNet.",
    )
    parser.add_argument("--input", default="../data/env_map", help="Input LDR/SDR image or directory.")
    parser.add_argument("--out", default="../results/env_map_hdr", help="Output directory for .hdr and .tif files.")
    parser.add_argument("--preset", choices=sorted(PRESETS), default="synthetic", help="Use the matching checkpoint, scale, and peak from GMNet training.")
    parser.add_argument("--checkpoint", default=None, help="Override preset checkpoint path.")
    parser.add_argument("--scale", type=float, default=None, help="Override preset scale. Usually keep this paired with the checkpoint.")
    parser.add_argument("--peak", type=float, default=None, help="HDR peak / SDR white ratio used to unnormalize pred_qgm; not metadata Qmax.")
    parser.add_argument("--qmax", type=float, default=None, help="Optional absolute gain exponent. If set, use pred_gm * qmax; otherwise use pred_qgm with GMNet's estimated global Qmax.")
    parser.add_argument("--normalize-by-peak", action="store_true", help="Divide output by peak to reproduce codes/test.py scale. Leave off for normal LDR2HDR/env-map export.")
    parser.add_argument("--gpu", type=int, default=0, help="Use -1 for CPU.")
    parser.add_argument("--no-tif", action="store_true", help="Only save Radiance .hdr files.")
    args = parser.parse_args()

    preset = PRESETS[args.preset]
    checkpoint = args.checkpoint or preset["checkpoint"]
    scale = args.scale if args.scale is not None else preset["scale"]
    peak = args.peak if args.peak is not None else preset["peak"]

    device = torch.device("cuda:{}".format(args.gpu) if args.gpu >= 0 and torch.cuda.is_available() else "cpu")
    os.makedirs(args.out, exist_ok=True)

    opt = build_opt(args)
    net = networks.define_G(opt).to(device)
    load_network(net, checkpoint, device)

    paths = list_images(args.input)
    if not paths:
        raise RuntimeError("No input images found: {}".format(args.input))

    qmax_msg = "network-estimated" if args.qmax is None else str(args.qmax)
    print("Device: {} | preset: {} | scale: {} | peak: {} | qmax: {}".format(device, args.preset, scale, peak, qmax_msg))
    for img_path in paths:
        out_path = infer_one(
            net,
            img_path,
            args.out,
            scale,
            peak,
            device,
            not args.no_tif,
            args.qmax,
            args.normalize_by_peak,
        )
        print("{} -> {}".format(img_path, out_path))


if __name__ == "__main__":
    main()

# python infer_env_hdr.py --input ../data/env_map --out ../results/env_map_hdr --preset synthetic --qmax 3.0
