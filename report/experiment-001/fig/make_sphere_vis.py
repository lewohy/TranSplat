"""Sphere shell figure data: per-direction visibility of one point and its SH16 (l<=3) reconstruction.

The occluder is a blob with a wavy (curved) boundary seen from the point; the soft edge stands in
for ESM+PCF. The SH projection uses the whole sphere; only the +x+y+z octant is drawn as a bumped
shell (radius follows the value), the rest as a wireframe. Projection and back-to-front order are
done here, so the typst side only draws 2D polygons.

    python report/experiment-001/fig/make_sphere_vis.py
"""

import json
from pathlib import Path

import numpy as np

OUT = Path(__file__).with_name("sphere_vis.json")

# occluder blob: center direction, base angular radius, wave, soft edge width (degrees)
C_THETA, C_PHI = 48.0, 50.0
BASE, WAVE, LOBES, EDGE = 19.0, 5.0, 3, 3.0
# view direction (from the origin towards the viewer)
AZIM, ELEV = 15.0, 18.0
LIGHT = (0.7, 0.45, 0.6)  # for shading only
BUMP = 0.3  # radius = R * (1 + BUMP * (value - 1))
N_QUAD = 64


def dirs(theta, phi):
    t, p = np.radians(theta), np.radians(phi)
    return np.stack([np.sin(t) * np.cos(p), np.sin(t) * np.sin(p), np.cos(t)], -1)


def visibility(d):
    c = dirs(C_THETA, C_PHI)
    ang = np.degrees(np.arccos(np.clip(d @ c, -1, 1)))
    # angle around the blob center, for a wavy boundary
    e1 = np.cross(c, [0.0, 0.0, 1.0])
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(c, e1)
    psi = np.arctan2(d @ e2, d @ e1)
    rad = BASE + WAVE * np.sin(LOBES * psi)
    return np.clip((ang - rad) / EDGE + 0.5, 0.0, 1.0)


def sh16(d):
    x, y, z = d[..., 0], d[..., 1], d[..., 2]
    return np.stack(
        [
            0.282095 * np.ones_like(x),
            0.488603 * y, 0.488603 * z, 0.488603 * x,
            1.092548 * x * y, 1.092548 * y * z, 0.315392 * (3 * z * z - 1), 1.092548 * x * z,
            0.546274 * (x * x - y * y),
            0.590044 * y * (3 * x * x - y * y), 2.890611 * x * y * z, 0.457046 * y * (5 * z * z - 1),
            0.373176 * z * (5 * z * z - 3), 0.457046 * x * (5 * z * z - 1), 1.445306 * z * (x * x - y * y),
            0.590044 * x * (x * x - 3 * y * y),
        ],
        -1,
    )


def main():
    # SH projection over the whole sphere (midpoint rule in theta/phi)
    nt, npp = 720, 1440
    t = (np.arange(nt) + 0.5) * 180.0 / nt
    p = (np.arange(npp) + 0.5) * 360.0 / npp
    T, P = np.meshgrid(t, p, indexing="ij")
    d = dirs(T, P)
    w = np.sin(np.radians(T)) * np.radians(180.0 / nt) * np.radians(360.0 / npp)
    coeffs = np.einsum("tpk,tp->k", sh16(d), visibility(d) * w)

    view = dirs(90.0 - ELEV, AZIM)
    light = np.array(LIGHT) / np.linalg.norm(LIGHT)
    right = np.cross([0.0, 0.0, 1.0], view)
    right /= np.linalg.norm(right)
    up = np.cross(view, right)

    def proj(pt):
        return [round(float(pt @ right), 4), round(float(pt @ up), 4)]

    edges = np.linspace(0.0, 90.0, N_QUAD + 1)
    panels = {}
    for name, fn in (("judge", visibility), ("sh16", lambda dd: sh16(dd) @ coeffs)):
        quads = []
        for i in range(N_QUAD):
            for j in range(N_QUAD):
                corners = [(edges[i], edges[j]), (edges[i + 1], edges[j]), (edges[i + 1], edges[j + 1]), (edges[i], edges[j + 1])]
                pts3 = []
                for th, ph in corners:
                    dd = dirs(th, ph)
                    pts3.append(dd * (1.0 + BUMP * (float(fn(dd)) - 1.0)))
                mid = dirs((edges[i] + edges[i + 1]) / 2, (edges[j] + edges[j + 1]) / 2)
                val = float(fn(mid))
                n = np.cross(pts3[2] - pts3[0], pts3[3] - pts3[1])
                n = n / (np.linalg.norm(n) + 1e-12)
                if n @ mid < 0:
                    n = -n
                shade = 0.45 + 0.55 * max(0.0, float(n @ light))
                quads.append((float(np.mean(pts3, 0) @ view), [proj(q) for q in pts3], round(val, 3), round(shade, 3)))
        quads.sort(key=lambda q: q[0])
        # slice through the blob center along its meridian (what the 1D graph shows), on the bumped shell
        th = np.linspace(0.0, 90.0, 91)
        sl = [dirs(a, C_PHI) * (1.0 + BUMP * (float(fn(dirs(a, C_PHI))) - 1.0)) for a in th]
        panels[name] = {"quads": [{"p": q[1], "v": q[2], "s": q[3]} for q in quads], "slice": [proj(q) for q in sl]}

    # wireframe of the full unit sphere: latitude and longitude circles, split into back/front segments
    def polyline(pts):
        segs, cur, cur_front = [], [], None
        for q in pts:
            front = bool(q @ view >= 0)
            if cur_front is None or front == cur_front:
                cur.append(q)
            else:
                cur.append(q)
                segs.append({"front": cur_front, "p": [proj(x) for x in cur]})
                cur = [q]
            cur_front = front
        segs.append({"front": cur_front, "p": [proj(x) for x in cur]})
        return segs

    wire = []
    s = np.linspace(0, 360, 181)
    for th in range(15, 180, 15):
        wire += polyline(dirs(np.full_like(s, th), s))
    s = np.linspace(0, 180, 91)
    for ph in range(0, 360, 15):
        wire += polyline(dirs(s, np.full_like(s, ph)))

    # full great circle through the z axis and the blob center: t = 0 at +z, along phi = C_PHI first
    t = np.arange(0.0, 360.0, 1.0)
    tr = np.radians(t)
    pc = np.radians(C_PHI)
    cut_d = np.stack([np.sin(tr) * np.cos(pc), np.sin(tr) * np.sin(pc), np.cos(tr)], -1)
    cut_j = visibility(cut_d)
    cut_s = sh16(cut_d) @ coeffs
    cut = {"t": t.tolist(), "judge": np.round(cut_j, 3).tolist(), "sh16": np.round(cut_s, 3).tolist()}
    # small light just outside the far edge of the blob along the cut
    edge = float(t[np.where((cut_j[:-1] < 0.5) & (cut_j[1:] >= 0.5))[0][0]])
    cut["light_t"] = edge + 4.0
    circle_pts = [cut_d[i] for i in range(len(t))] + [cut_d[0]]
    great = polyline(circle_pts)

    axes = {k: proj(v * 1.35) for k, v in (("x", np.array([1.0, 0, 0])), ("y", np.array([0, 1.0, 0])), ("z", np.array([0, 0, 1.0])))}
    out = {
        "panels": panels,
        "wire": wire,
        "great": great,
        "cut": cut,
        "axes": axes,
        "outline": [proj(np.cos(a) * right + np.sin(a) * up) for a in np.linspace(0, 2 * np.pi, 121)],
        "range": {"judge": [0.0, 1.0], "sh16": [round(min(q["v"] for q in panels["sh16"]["quads"]), 3), round(max(q["v"] for q in panels["sh16"]["quads"]), 3)]},
    }
    OUT.write_text(json.dumps(out, separators=(",", ":")))
    print("wrote", OUT, "sh16 range on octant", out["range"]["sh16"])


if __name__ == "__main__":
    main()
