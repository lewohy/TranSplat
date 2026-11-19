"""Teaser data for the paper: floor brightness across the shadow of a wall, exact vs. SH-16 vs. light separation.

Scene: an infinite wall of height 1 standing on the floor along the y axis (plane x = 0), lit by the same
lighting as the study (uniform sky a = 0.2 plus a 2 degree sun whose irradiance at normal incidence is 3).
For floor points (x, 0, 0) behind the wall the visibility is evaluated exactly (0/1, the oracle) and after
projecting it onto SH l <= 3 (16 coefficients, what TranSplat stores per Gaussian). Lighting and cosine are
exact in both, so the difference comes only from compressing the visibility.
"ours" is light separation: the sky keeps the SH-16 visibility, and the sun is shadowed with 16 directions inside
its disc (SUN_SAMPLES, as in the study's hybrid). Each direction is tested exactly, i.e. an ideal shadow map with
no resolution error.

    .venv/bin/python report/paper-figures/make_teaser_data.py   ->  report/paper-figures/teaser.json
"""

import json
from pathlib import Path

import numpy as np
from scipy.special import sph_harm

OUT = Path(__file__).with_name("teaser.json")
WALL_H = 1.0
SUN_ELEV = 40.0  # degrees above the floor, shining toward +x over the wall
SUN_DIAM = 2.0  # degrees
SKY, SUN = 0.2, 3.0  # sky radiance, sun irradiance at normal incidence (study defaults)
L_MAX = 3
SUN_SAMPLES = 16  # light separation: shadow-map directions inside the sun disc


def real_sh(d, l_max):
    theta = np.arccos(np.clip(d[..., 2], -1, 1))
    phi = np.arctan2(d[..., 1], d[..., 0])
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


def visible(x, d):
    """0/1 visibility from floor point (x, 0, 0): the floor hides the lower hemisphere, the wall a wedge."""
    up = d[..., 2] > 0
    toward = d[..., 0] < 0
    with np.errstate(divide="ignore", invalid="ignore"):
        z_at_wall = x * d[..., 2] / -d[..., 0]
    return (up & ~(toward & (z_at_wall < WALL_H))).astype(float)


def sun_dirs(n=256):
    e = np.radians(SUN_ELEV)
    axis = np.array([np.cos(e), 0.0, np.sin(e)])  # direction toward the sun (it shines toward +x)
    axis[0] *= -1
    r = np.radians(SUN_DIAM / 2)
    i = np.arange(n)
    ct = 1 - (i + 0.5) / n * (1 - np.cos(r))
    st = np.sqrt(1 - ct**2)
    ph = np.pi * (3 - 5**0.5) * i
    t = np.cross([0.0, 1.0, 0.0], axis)
    t /= np.linalg.norm(t)
    b = np.cross(axis, t)
    return st[:, None] * np.cos(ph)[:, None] * t + st[:, None] * np.sin(ph)[:, None] * b + ct[:, None] * axis


def main():
    nt, npp = 360, 720
    T = (np.arange(nt) + 0.5) * np.pi / nt
    P = (np.arange(npp) + 0.5) * 2 * np.pi / npp
    T, P = np.meshgrid(T, P, indexing="ij")
    d = np.stack([np.sin(T) * np.cos(P), np.sin(T) * np.sin(P), np.cos(T)], -1)
    w = np.sin(T) * (np.pi / nt) * (2 * np.pi / npp)
    cos = np.clip(d[..., 2], 0, None)
    Y = real_sh(d, L_MAX)
    s = sun_dirs()
    Ys = real_sh(s, L_MAX)
    sun_cos = s[:, 2].mean()
    s16 = sun_dirs(SUN_SAMPLES)

    xs = np.linspace(0.05, 3.0, 296)
    exact, sh16, ours = [], [], []
    for x in xs:
        v = visible(x, d)
        c = np.einsum("tpk,tp->k", Y, v * w)
        v16 = Y @ c
        exact.append(SKY * (v * cos * w).sum() + SUN * sun_cos * visible(x, s).mean())
        sh16.append(SKY * (v16 * cos * w).sum() + SUN * sun_cos * (Ys @ c).mean())
        ours.append(SKY * (v16 * cos * w).sum() + SUN * s16[:, 2].mean() * visible(x, s16).mean())
    lit = exact[-1]
    out = {
        "x": np.round(xs, 3).tolist(),
        "exact": np.round(np.array(exact) / lit, 4).tolist(),
        "sh16": np.round(np.array(sh16) / lit, 4).tolist(),
        "ours": np.round(np.array(ours) / lit, 4).tolist(),
        "edge_x": WALL_H / np.tan(np.radians(SUN_ELEV)),
        "wall_h": WALL_H,
        "sun_elev": SUN_ELEV,
    }
    OUT.write_text(json.dumps(out, separators=(",", ":")))
    e, h, o = np.array(out["exact"]), np.array(out["sh16"]), np.array(out["ours"])
    print("wrote", OUT, "edge", round(out["edge_x"], 3))
    print("exact min/max", e.min(), e.max(), " sh16 min/max", h.min(), h.max())
    print("mean |err|  sh16", round(np.abs(h - e).mean(), 4), " ours", round(np.abs(o - e).mean(), 4))
    for k in (0, 100, 113, 115, 117, 120, 150, 200, 295):
        print(f"x={xs[k]:.2f} exact={e[k]:.3f} sh16={h[k]:.3f} ours={o[k]:.3f}")


if __name__ == "__main__":
    main()
