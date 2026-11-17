"""Teaser data for the paper: one point's visibility along a great circle, 0/1 vs SH reconstructions.

Same synthetic occluder as report/experiment-001/fig/make_sphere_vis.py (a blob with a wavy boundary),
but with a hard edge like the oracle. The SH projection uses the whole sphere.

    .venv/bin/python report/paper-figures/make_teaser_data.py   ->  report/paper-figures/teaser.json
"""

import json
import sys
from pathlib import Path

import numpy as np
from scipy.special import sph_harm

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "experiment-001" / "fig"))
import make_sphere_vis as msv  # noqa: E402

OUT = Path(__file__).with_name("teaser.json")
EDGE = 0.5  # degrees, close to a hard 0/1 boundary
L_MAX = (3, 9)  # SH 16 and 100 coefficients


def visibility(d):
    msv.EDGE = EDGE
    return msv.visibility(d)


def real_sh(d, l_max):
    theta = np.arccos(np.clip(d[..., 2], -1, 1))  # polar
    phi = np.arctan2(d[..., 1], d[..., 0])  # azimuth
    out = []
    for l in range(l_max + 1):
        for m in range(-l, l + 1):
            y = sph_harm(abs(m), l, phi, theta)
            if m < 0:
                out.append(np.sqrt(2) * (-1) ** m * y.imag)
            elif m == 0:
                out.append(y.real)
            else:
                out.append(np.sqrt(2) * (-1) ** m * y.real)
    return np.stack(out, -1)


def main():
    nt, npp = 720, 1440
    t = (np.arange(nt) + 0.5) * 180.0 / nt
    p = (np.arange(npp) + 0.5) * 360.0 / npp
    T, P = np.meshgrid(t, p, indexing="ij")
    d = msv.dirs(T, P)
    w = np.sin(np.radians(T)) * np.radians(180.0 / nt) * np.radians(360.0 / npp)
    Y = real_sh(d, max(L_MAX))
    coeffs = np.einsum("tpk,tp->k", Y, visibility(d) * w)

    ang = np.arange(0.0, 360.0, 0.5)
    tr, pc = np.radians(ang), np.radians(msv.C_PHI)
    cut_d = np.stack([np.sin(tr) * np.cos(pc), np.sin(tr) * np.sin(pc), np.cos(tr)], -1)
    Yc = real_sh(cut_d, max(L_MAX))
    out = {"t": ang.tolist(), "vis": np.round(visibility(cut_d), 3).tolist()}
    for l in L_MAX:
        k = (l + 1) ** 2
        out[f"sh{k}"] = np.round(Yc[:, :k] @ coeffs[:k], 3).tolist()
    vis = np.array(out["vis"])
    out["edge_t"] = float(ang[np.where((vis[:-1] < 0.5) & (vis[1:] >= 0.5))[0][0]])
    out["light_t"] = out["edge_t"] + 4.0  # a 2 degree light just outside the occluder
    OUT.write_text(json.dumps(out, separators=(",", ":")))
    i = int(np.argmin(abs(ang - out["light_t"])))
    print("wrote", OUT, {k: out[k][i] for k in ("vis", "sh16", "sh100")})


if __name__ == "__main__":
    main()
