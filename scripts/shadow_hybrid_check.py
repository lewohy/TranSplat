"""Hybrid check: shadow the disc light at relight time instead of through compressed visibility.

Reuses the eval points and oracle of a shadow_frequency_study run (per_point.npz). The disc term
is recomputed from per-light shadow maps at a given resolution and number of samples inside the
disc; the ambient term is kept from the oracle, so the error is that of the disc shadow alone.
Same metric as the study: nmae_penumbra = mean|E - E_oracle| over penumbra / mean E_oracle over lit.

    python scripts/shadow_hybrid_check.py --ply .../point_cloud.ply --study-dir .../shadow_frequency_study_v3
"""

import argparse
import json
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
    parser.add_argument("--ply", type=Path, required=True)
    parser.add_argument("--study-dir", type=Path, required=True)
    parser.add_argument("--resolutions", nargs="+", type=int, default=[512, 1024, 2048])
    parser.add_argument("--samples", nargs="+", type=int, default=[1, 4, 16, 64])
    args = parser.parse_args()

    meta = json.loads((args.study_dir / "results.json").read_text())["meta"]
    pp = np.load(args.study_dir / "per_point.npz")
    device = "cuda"
    torch.set_grad_enabled(False)

    g = rt.load_ply(str(args.ply))
    xyz = g["xyz"].detach()
    opaque = torch.sigmoid(g["opacity"].detach()[:, 0]) > meta["min_opacity"]
    center, _, radius, dist = sfs.robust_bounds(xyz, opaque, meta["radius_quantile"], meta["radius_margin"])
    if not meta.get("keep_floaters"):
        g = dict(g)
        g["opacity"] = g["opacity"].detach().clone()
        g["opacity"][dist > radius] = -30.0

    eval_idx = torch.from_numpy(pp["eval_idx"]).to(device)
    normals = torch.from_numpy(pp["normals_sh"]).to(device)
    margs = argparse.Namespace(**{k: meta[k] for k in ("oracle_depth", "bias_const", "bias_slope", "normal_offset")})
    mode = meta["bias"]
    mappers = {r: sfs.ShadowMapper(g, eval_idx, normals, center, radius, r, margs) for r in args.resolutions}
    ref_res = meta["shadow_res"]
    if ref_res not in mappers:
        mappers[ref_res] = sfs.ShadowMapper(g, eval_idx, normals, center, radius, ref_res, margs)

    def disc_term(lt, mapper, n):
        dirs, cap_w = sfs.cap_directions(lt.axis, lt.half_angle, n)
        acc = torch.zeros(normals.shape[0], device=device)
        for d in dirs:
            acc += mapper(d, [mode])[mode] * (normals @ d).clamp(min=0.0)
        return lt.radiance * cap_w * acc

    rows = {}
    for name, axis_world in meta["lights_world"].items():
        size = float(name.split("_")[1].removesuffix("deg"))
        lt = sfs.DiscLight(name, sfs.to_sh_frame(torch.tensor(axis_world, device=device)), size,
                           meta["ambient"], meta["sun_irradiance"], meta["cap_samples"])
        E0 = torch.from_numpy(pp[f"{name}__oracle"]).to(device)
        lit_frac = torch.from_numpy(pp[f"{name}__lit_frac"]).to(device)
        facing = (normals @ lt.axis) > 0.1
        pen = facing & (lit_frac > 0.02) & (lit_frac < 0.98)
        lit = facing & (lit_frac >= 0.98)
        if not pen.any() or not lit.any():
            continue
        d0 = disc_term(lt, mappers[ref_res], meta["cap_samples"])
        lit_mean = E0[lit].mean()
        for r, m in mappers.items():
            for n in args.samples:
                d = d0 if (r == ref_res and n == meta["cap_samples"]) else disc_term(lt, m, n)
                rows.setdefault(size, {}).setdefault((r, n), []).append(
                    float((d - d0)[pen].abs().mean() / lit_mean)
                )
        print(name, "done")

    res_list = sorted(mappers)
    lines = [
        "# Hybrid check: disc shadowed at relight time",
        "",
        f"Study: `{args.study_dir}`. Penumbra nMAE of the disc term against the oracle "
        f"({ref_res} px, {meta['cap_samples']} disc samples, `{mode}` bias). Columns: shadow-map resolution x samples inside the disc.",
        "",
    ]
    header = ["disc deg"] + [f"{r}px x{n}" for r in res_list for n in args.samples]
    body = [[f"{s:g}"] + [sfs.fmt(float(np.mean(rows[s][(r, n)]))) for r in res_list for n in args.samples] for s in sorted(rows)]
    lines += sfs.table(header, body)
    out = args.study_dir / "hybrid_check.md"
    out.write_text("\n".join(lines))
    print("\n".join(lines))
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
