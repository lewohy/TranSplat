"""AO with the four oracle fixes applied one at a time (cumulative), on one random point set.

Same settings as a shadow_frequency_study run (results.json meta). Points are drawn at random from
the opaque Gaussians inside the robust radius, i.e. before fix 3; fix 3 is a mask on the same set.
  0 before   phase-1 bounds (mean center, 1.8 x max distance), raw 2DGS normals, 3 x max_scale bias
  1 + bounds robust center and radius (99.5% quantile x 1.1)
  2 + normal sign by training-camera vote
  3 + only points seen by >= 2 views and on the rendered surface
  4 + normal offset bias (the study's oracle)

    python scripts/shadow_ao_steps.py --study-dir .../shadow_frequency_study
"""

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

sys.path.insert(0, str(Path(__file__).resolve().parent))
import shadow_frequency_study as sfs  # noqa: E402

rt = sfs.rt


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--study-dir", type=Path, required=True)
    parser.add_argument("--num-points", type=int, help="Default: the study's num_eval_points")
    parser.add_argument("--cube-res", type=int, help="Default: the study's cube_res")
    args = parser.parse_args()

    meta = json.loads((args.study_dir / "results.json").read_text())["meta"]
    device = "cuda"
    torch.set_grad_enabled(False)
    torch.manual_seed(meta["seed"])

    g = rt.load_ply(str(meta["ply"]))
    xyz = g["xyz"].detach()
    opaque = torch.sigmoid(g["opacity"].detach()[:, 0]) > meta["min_opacity"]
    center, r_q, radius, dist = sfs.robust_bounds(xyz, opaque, meta["radius_quantile"], meta["radius_margin"])
    center0 = xyz.mean(0)
    radius0 = float(torch.norm(xyz - center0, dim=1).max()) * 1.8
    culled = dict(g)
    culled["opacity"] = g["opacity"].detach().clone()
    culled["opacity"][dist > radius] = -30.0

    rot_n = F.normalize(rt.quaternion2rotmat(F.normalize(g["rotation"].detach(), dim=1))[..., 2], dim=1)
    candidates = torch.nonzero(opaque & (dist < r_q))[:, 0]
    n = args.num_points or meta["num_eval_points"]
    idx = candidates[torch.randperm(candidates.numel(), device=device)[:n]].sort().values

    cams = sfs.load_cameras(meta["cameras"], device)
    n_views, vote, resid = sfs.training_views(culled, cams, idx, rot_n, meta["view_tol"])
    surface = (n_views >= meta["min_views"]) & (resid < meta["surface_tol"])
    voted = rot_n[idx] * torch.where(vote < 0, -1.0, 1.0)[:, None]
    raw_sh, voted_sh = sfs.to_sh_frame(rot_n[idx]), sfs.to_sh_frame(voted)

    D, w = sfs.cube_directions(args.cube_res or meta["cube_res"], device)
    margs = argparse.Namespace(**{k: meta[k] for k in ("oracle_depth", "bias_const", "bias_slope", "normal_offset")})
    res = meta["shadow_res"]
    # ShadowMapper takes normals in the SH frame and converts them back for the normal offset.
    m0 = sfs.ShadowMapper(g, idx, raw_sh, center0, radius0, res, margs)
    _, ao0 = m0.bake(D, w, ["scale"], [], {"s0": ("scale", raw_sh)}, "AO: phase-1 bounds")
    del m0
    m1 = sfs.ShadowMapper(culled, idx, voted_sh, center, radius, res, margs)
    _, ao1 = m1.bake(D, w, ["scale", "normal"], [], {
        "s1": ("scale", raw_sh), "s2": ("scale", voted_sh), "s4": ("normal", voted_sh)}, "AO: robust bounds")

    all_pts = torch.ones_like(surface)
    steps = [
        ("before", ao0["s0"], all_pts),
        ("+1 bounds", ao1["s1"], all_pts),
        ("+2 normal sign", ao1["s2"], all_pts),
        ("+3 surface points", ao1["s2"], surface),
        ("+4 normal offset", ao1["s4"], surface),
    ]
    rows = []
    for name, ao, mask in steps:
        q = sfs.quantiles(ao[mask])
        rows.append(dict(step=name, n=int(mask.sum()), **q))
    out = dict(
        radius_phase1=radius0, radius=radius, n_points=n, frac_surface=float(surface.float().mean()),
        frac_flipped=float((vote < 0).float().mean()), steps=rows,
    )
    (args.study_dir / "ao_steps.json").write_text(json.dumps(out, indent=2))
    keys = [k for k in rows[0] if k not in ("step", "n")]
    lines = [
        "# AO with the oracle fixes applied one at a time",
        "",
        f"{n} random opaque points inside the robust radius (before fix 3); fix 3 keeps {int(surface.sum())} of them.",
        f"bounds: phase 1 radius {radius0:.3f}, robust {radius:.3f}; normals flipped by the vote: {out['frac_flipped']:.3f}",
        "",
        "| step | points | " + " | ".join(keys) + " |",
        "|---|---|" + "---|" * len(keys),
    ]
    lines += [f"| {r['step']} | {r['n']} | " + " | ".join(sfs.fmt(r[k]) for k in keys) + " |" for r in rows]
    (args.study_dir / "ao_steps.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
