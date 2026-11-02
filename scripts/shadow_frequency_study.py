#!/usr/bin/env python3
"""Measure where high-frequency self-shadow detail is lost in TranSplat.

Lights a trained model with synthetic environment maps (uniform ambient plus
a disc light of varying angular size) and compares per-Gaussian diffuse
irradiance from several estimators against a dense, non-band-limited oracle:

    E(x) = sum_j w_j * L(w_j) * V(x, w_j) * max(n . w_j, 0)

The sphere is integrated on cube-map texel centers (plus dense samples inside
the disc), visibility is a hard shadow-map test, and only Gaussians seen by the
training cameras are evaluated, with normals oriented towards those cameras.

Each estimator changes one step relative to the oracle, so the error table
attributes the loss to a specific cause:

    oracle            hard visibility, exact L, exact clamped cosine
    oracle_res2x      shadow maps at 2x resolution        -> convergence check
    oracle_dir2x      2x sphere directions and disc samples -> convergence check
    oracle_bias_*     other hard-visibility bias modes    -> bias sensitivity
    filt              ESM + PCF visibility (as in phase 1)          -> filtering
    cos2              clamped cosine truncated to l<=2 (as phase 2) -> cosine band limit
    sh{l}_L           L truncated to SH order l                     -> light band limit
    sh{l}_V           V truncated to SH order l                     -> visibility band limit
    sh{l}_LV          both truncated (current method at l=3)        -> triple product
    pipe{S}           the actual phase 1 + phase 2 diffuse path with S directions,
                      L sampled from the equirect HDR (nearest lookup)
    pipe{S}_exactL    same, but with exactly projected L            -> env sampling
    pipefix{S}        phase 1 math with a floater-robust scene radius and exact L
    pipefix{S}_hard   same, but with the oracle's hard visibility instead of ESM
    C_{V,LV,T}_{rep}  compact representations on the same cube map, exact cosine:
                      V = visibility only, LV = light and visibility,
                      T = transfer V * max(n.w, 0); rep = sh{K} (K = (l+1)^2
                      coefficients), haar{K} (K largest area-weighted Haar
                      coefficients per face pyramid) or cube (no compression)

All sh*/pipe* rows use the l<=2 cosine, so compare them against `cos2` as well
as `oracle`. Directions are expressed in the SH frame used by
radiance_transfer_TranSplat.py (world x flipped).

Run `--self-test` (CPU only) to check the SH/quadrature/Haar math without a model.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import radiance_transfer_TranSplat as rt  # noqa: E402

FOUR_PI = 4.0 * math.pi
# Clamped-cosine SH attenuation used by phase 2 (A_0, A_1, A_2).
A_COS = (math.pi, 2.0 * math.pi / 3.0, math.pi / 4.0)
HARD_MODES = ("scale", "slope", "normal", "normal_wide")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Check SH/quadrature/Haar math on CPU and exit",
    )
    parser.add_argument("--ply", type=Path, help="Trained point_cloud.ply")
    parser.add_argument(
        "--cameras",
        type=Path,
        help="Training cameras.json (defaults to the model dir next to point_cloud/)",
    )
    parser.add_argument(
        "--output-dir", type=Path, help="Defaults to <ply dir>/shadow_frequency_study"
    )
    parser.add_argument(
        "--disc-sizes",
        nargs="+",
        type=float,
        default=[2.0, 5.0, 10.0, 30.0],
        help="Disc light angular diameters in degrees",
    )
    parser.add_argument(
        "--up",
        default="auto",
        help="World up axis as x,y,z, or 'auto' (mean camera up of the training views)",
    )
    parser.add_argument(
        "--light-elev-azim",
        nargs="+",
        default=["60,0", "30,120", "10,240"],
        help="Light directions as elevation,azimuth in degrees relative to --up",
    )
    parser.add_argument(
        "--light-dirs",
        nargs="+",
        help="World-space light directions as x,y,z, overriding --light-elev-azim; "
        "quote a leading minus as ' -0.3,0.3,0.9'",
    )
    parser.add_argument("--ambient", type=float, default=0.2, help="Ambient radiance")
    parser.add_argument(
        "--sun-irradiance",
        type=float,
        default=3.0,
        help="Disc irradiance at normal incidence (kept fixed across disc sizes)",
    )
    parser.add_argument("--sh-orders", nargs="+", type=int, default=[2, 3, 5, 7, 9])
    parser.add_argument(
        "--cube-res",
        type=int,
        default=64,
        help="Cube-map face resolution of the oracle sphere quadrature (power of 2, "
        "one shadow map per texel)",
    )
    parser.add_argument(
        "--cap-samples", type=int, default=64, help="Directions inside each disc light"
    )
    parser.add_argument(
        "--pipe-samples",
        nargs="*",
        type=int,
        default=[1200],
        help="num_samples values for the pipeline rows (empty to skip)",
    )
    parser.add_argument(
        "--shadow-res",
        type=int,
        default=2048,
        help="Oracle shadow-map resolution (a 2 deg penumbra is about one texel at 1024)",
    )
    parser.add_argument(
        "--esm-res",
        type=int,
        default=1024,
        help="Shadow-map resolution of the ESM and phase-1 rows (phase 1 default)",
    )
    parser.add_argument(
        "--oracle-depth",
        choices=("median", "expected"),
        default="median",
        help="Shadow-map depth for hard visibility (ESM rows always use expected, as phase 1)",
    )
    parser.add_argument(
        "--bias",
        choices=HARD_MODES,
        default="normal",
        help="Hard-visibility bias of the oracle: scale = 3 x max scale (phase 1), "
        "slope = texel x (const + slope x tan), normal = slope plus a normal offset of the lookup point, "
        "normal_wide = normal with a 1.5x offset (sensitivity check)",
    )
    parser.add_argument("--bias-const", type=float, default=1.0, help="In shadow-map texels")
    parser.add_argument("--bias-slope", type=float, default=1.0, help="In shadow-map texels")
    parser.add_argument(
        "--normal-offset",
        type=float,
        default=2.0,
        help="In units of the Gaussian's max scale (surfel layers are about that thick)",
    )
    parser.add_argument(
        "--radius-quantile",
        type=float,
        default=0.995,
        help="Scene radius = quantile of opaque-Gaussian distances to their median",
    )
    parser.add_argument("--radius-margin", type=float, default=1.1)
    parser.add_argument(
        "--keep-floaters",
        action="store_true",
        help="Keep Gaussians outside the robust radius in this study's shadow maps "
        "(they sit between the shadow camera and the object and black out whole directions)",
    )
    parser.add_argument(
        "--min-views",
        type=int,
        default=2,
        help="Evaluate only Gaussians visible in at least this many training views",
    )
    parser.add_argument(
        "--view-tol",
        type=float,
        default=3.0,
        help="Depth tolerance in training-view pixels for counting a view (normal-orientation vote)",
    )
    parser.add_argument(
        "--surface-tol",
        type=float,
        default=0.5,
        help="Evaluate only Gaussians within this many pixels of the rendered surface in some view "
        "(deeper ones sit under other surfel layers and read as occluded)",
    )
    parser.add_argument(
        "--no-convergence",
        action="store_true",
        help="Skip the 2x resolution / 2x direction oracle bakes",
    )
    parser.add_argument(
        "--compact-sh-orders",
        nargs="+",
        type=int,
        default=[3, 7, 15],
        help="SH orders for the C_* rows (16 / 64 / 256 coefficients)",
    )
    parser.add_argument(
        "--haar-counts",
        nargs="+",
        type=int,
        default=[8, 16, 32, 64, 128, 256],
        help="Kept Haar coefficients for the C_* rows",
    )
    parser.add_argument(
        "--only-compact",
        action="store_true",
        help="Only the oracle and the C_* rows (for large --cube-res; skips ESM, bias variants, "
        "convergence, SH-truncation and pipeline rows)",
    )
    parser.add_argument(
        "--env-height", type=int, default=512, help="Equirect HDR height (width = 2x)"
    )
    parser.add_argument(
        "--num-eval-points",
        type=int,
        default=20000,
        help="Gaussians to evaluate (0 = all; visibility needs ~4 bytes x points x texels of GPU memory)",
    )
    parser.add_argument("--min-opacity", type=float, default=0.5)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--chunk",
        type=int,
        default=2048,
        help="Eval points per chunk in estimator math",
    )
    parser.add_argument(
        "--save-visibility",
        action="store_true",
        help="Save the oracle's hard cube-map visibility (large)",
    )
    parser.add_argument(
        "--thr-share",
        type=float,
        default=0.5,
        help="Decision: SH truncation share of the fixed-pipeline penumbra error",
    )
    parser.add_argument(
        "--thr-large",
        type=float,
        default=0.1,
        help="Decision: penumbra nMAE (fraction of lit irradiance) counted as large",
    )
    parser.add_argument(
        "--thr-ratio",
        type=float,
        default=2.0,
        help="Decision: SH / Haar penumbra error ratio counted as clearly better",
    )
    args = parser.parse_args()
    if not args.self_test and args.ply is None:
        parser.error("--ply is required unless --self-test")
    if args.cube_res & (args.cube_res - 1):
        parser.error("--cube-res must be a power of 2")
    return args


# ============================================================================
# Directions, quadrature and SH
# ============================================================================
def fibonacci_directions(n: int, device) -> torch.Tensor:
    """Same spiral as rt.precompute_sh_sampling, equal-area (weight 4*pi/n)."""
    i = torch.arange(n, device=device, dtype=torch.float64)
    theta = torch.acos(1 - 2 * (i + 0.5) / n)
    phi = math.pi * (1 + 5**0.5) * i
    return torch.stack(
        [
            torch.sin(theta) * torch.cos(phi),
            torch.sin(theta) * torch.sin(phi),
            torch.cos(theta),
        ],
        dim=1,
    ).float()


# Face 2a + (sign < 0) has major axis a; its texel grid spans the other two axes (rows, cols).
CUBE_AXES = ((2, 1), (2, 0), (1, 0))


def cube_directions(res: int, device):
    """Texel-center directions of a cube map, flattened as [face, row, col], and their solid angles."""
    t = (torch.arange(res, device=device, dtype=torch.float64) + 0.5) / res * 2 - 1
    rows, cols = torch.meshgrid(t, t, indexing="ij")
    faces = []
    for a, (r, c) in enumerate(CUBE_AXES):
        for sign in (1.0, -1.0):
            d = torch.empty(res, res, 3, device=device, dtype=torch.float64)
            d[..., a], d[..., r], d[..., c] = sign, rows, cols
            faces.append(d)
    d = torch.stack(faces)
    w = d.norm(dim=-1) ** -3
    w = w * (FOUR_PI / w.sum())
    return F.normalize(d, dim=-1).reshape(-1, 3).float(), w.reshape(-1).float()


def cube_lookup(dirs: torch.Tensor, res: int) -> torch.Tensor:
    """Flat index of the cube-map texel containing each direction."""
    a = dirs.abs().argmax(1)
    major = dirs.gather(1, a[:, None])[:, 0]
    axes = torch.tensor(CUBE_AXES, device=dirs.device)[a]
    face = 2 * a + (major < 0).long()

    def coord(k):
        t = dirs.gather(1, axes[:, k : k + 1])[:, 0] / major.abs()
        return ((t + 1) * 0.5 * res).long().clamp(0, res - 1)

    return (face * res + coord(0)) * res + coord(1)


def cap_directions(axis: torch.Tensor, half_angle: float, n: int):
    """Equal-area spiral inside a spherical cap. Returns (dirs, per-sample solid angle)."""
    device = axis.device
    i = torch.arange(n, device=device, dtype=torch.float64)
    cos_r = math.cos(half_angle)
    ct = 1 - (i + 0.5) / n * (1 - cos_r)
    st = torch.sqrt((1 - ct * ct).clamp(min=0))
    phi = math.pi * (3 - 5**0.5) * i
    local = torch.stack([st * torch.cos(phi), st * torch.sin(phi), ct], dim=1).float()
    a = F.normalize(axis, dim=0)
    helper = (
        torch.tensor([1.0, 0.0, 0.0], device=device)
        if abs(a[0].item()) < 0.9
        else torch.tensor([0.0, 1.0, 0.0], device=device)
    )
    t = F.normalize(torch.cross(helper, a, dim=0), dim=0)
    b = torch.cross(a, t, dim=0)
    dirs = local[:, :1] * t + local[:, 1:2] * b + local[:, 2:] * a
    return dirs, 2 * math.pi * (1 - cos_r) / n


def real_sh(dirs: torch.Tensor, l_max: int) -> torch.Tensor:
    """Orthonormal real SH up to l_max, index l*l + l + m.

    Signs differ from rt.evaluate_sh_bases_torch, but every estimator here only
    uses projections onto the span of bands <= l, which is basis independent.
    """
    d = dirs.double()
    x, y, z = d[:, 0], d[:, 1], d[:, 2].clamp(-1, 1)
    s = torch.sqrt((1 - z * z).clamp(min=0))
    phi = torch.atan2(y, x)
    P = {(0, 0): torch.ones_like(z)}
    for m in range(1, l_max + 1):
        P[(m, m)] = (2 * m - 1) * s * P[(m - 1, m - 1)]
    for m in range(0, l_max):
        P[(m + 1, m)] = (2 * m + 1) * z * P[(m, m)]
    for m in range(0, l_max + 1):
        for l in range(m + 2, l_max + 1):
            P[(l, m)] = (
                (2 * l - 1) * z * P[(l - 1, m)] - (l + m - 1) * P[(l - 2, m)]
            ) / (l - m)
    out = torch.empty(
        d.shape[0], (l_max + 1) ** 2, dtype=torch.float64, device=d.device
    )
    for l in range(l_max + 1):
        for m in range(0, l + 1):
            k = math.sqrt(
                (2 * l + 1) / FOUR_PI * math.factorial(l - m) / math.factorial(l + m)
            )
            if m == 0:
                out[:, l * l + l] = k * P[(l, 0)]
            else:
                out[:, l * l + l + m] = (
                    math.sqrt(2) * k * torch.cos(m * phi) * P[(l, m)]
                )
                out[:, l * l + l - m] = (
                    math.sqrt(2) * k * torch.sin(m * phi) * P[(l, m)]
                )
    return out.float()


def cos_kernel_l2(t: torch.Tensor) -> torch.Tensor:
    """Clamped cosine truncated to l<=2: sum_l A_l (2l+1)/(4pi) P_l(t)."""
    return (
        (A_COS[0] / FOUR_PI)
        + (A_COS[1] * 3 / FOUR_PI) * t
        + (A_COS[2] * 5 / FOUR_PI) * 0.5 * (3 * t * t - 1)
    )


def to_sh_frame(v: torch.Tensor) -> torch.Tensor:
    out = v.clone()
    out[..., 0] = -out[..., 0]
    return out


# ============================================================================
# Haar wavelets on cube-map faces
# ============================================================================
def haar2d(x: torch.Tensor) -> torch.Tensor:
    """Orthonormal 2D Haar pyramid of the last two (square, power of 2) dims, Mallat layout."""
    x = x.clone()
    n = x.shape[-1]
    while n > 1:
        a, b = x[..., 0:n:2, 0:n:2], x[..., 0:n:2, 1:n:2]
        c, d = x[..., 1:n:2, 0:n:2], x[..., 1:n:2, 1:n:2]
        h = n // 2
        out = torch.empty_like(x[..., :n, :n])
        out[..., :h, :h] = (a + b + c + d) * 0.5
        out[..., :h, h:] = (a - b + c - d) * 0.5
        out[..., h:, :h] = (a + b - c - d) * 0.5
        out[..., h:, h:] = (a - b - c + d) * 0.5
        x[..., :n, :n] = out
        n = h
    return x


def ihaar2d(x: torch.Tensor) -> torch.Tensor:
    x = x.clone()
    n = 2
    while n <= x.shape[-1]:
        h = n // 2
        s, p = x[..., :h, :h], x[..., :h, h:n]
        q, r = x[..., h:n, :h], x[..., h:n, h:n]
        out = torch.empty_like(x[..., :n, :n])
        out[..., 0::2, 0::2] = (s + p + q + r) * 0.5
        out[..., 0::2, 1::2] = (s - p + q - r) * 0.5
        out[..., 1::2, 0::2] = (s + p - q - r) * 0.5
        out[..., 1::2, 1::2] = (s - p - q + r) * 0.5
        x[..., :n, :n] = out
        n *= 2
    return x


def haar_topk(f: torch.Tensor, res: int, k: int) -> torch.Tensor:
    """Nonlinear approximation of flat cube maps [B, 6*res*res] keeping the k largest Haar coefficients."""
    coeffs = haar2d(f.reshape(-1, 6, res, res)).reshape(f.shape[0], -1)
    if k < coeffs.shape[1]:
        idx = coeffs.abs().topk(k, dim=1).indices
        coeffs = torch.zeros_like(coeffs).scatter_(1, idx, coeffs.gather(1, idx))
    return ihaar2d(coeffs.reshape(-1, 6, res, res)).reshape(f.shape[0], -1)


# ============================================================================
# Synthetic lights
# ============================================================================
class DiscLight:
    def __init__(
        self, name, axis_sh, diameter_deg, ambient, sun_irradiance, cap_samples
    ):
        self.name = name
        self.axis = F.normalize(axis_sh, dim=0)
        self.diameter_deg = diameter_deg
        self.half_angle = math.radians(diameter_deg) * 0.5
        self.ambient = ambient
        # pi * sin^2(r) is the cosine-weighted solid angle of the cap at normal incidence.
        self.radiance = sun_irradiance / (math.pi * math.sin(self.half_angle) ** 2)
        self.cap_samples = cap_samples
        self.cap_dirs, self.cap_w = cap_directions(
            self.axis, self.half_angle, cap_samples
        )

    def with_cap_samples(self, n):
        return DiscLight(
            self.name,
            self.axis,
            self.diameter_deg,
            self.ambient,
            self.radiance * math.pi * math.sin(self.half_angle) ** 2,
            n,
        )

    def equirect(self, height: int) -> torch.Tensor:
        """HDR in the layout rt.sample_env_map_torch reads (theta rows, phi columns)."""
        device = self.axis.device
        H, W = height, 2 * height
        theta = (torch.arange(H, device=device) + 0.5) / H * math.pi
        phi = (torch.arange(W, device=device) + 0.5) / W * 2 * math.pi
        th, ph = torch.meshgrid(theta, phi, indexing="ij")
        d = torch.stack(
            [
                torch.sin(th) * torch.cos(ph),
                torch.sin(th) * torch.sin(ph),
                torch.cos(th),
            ],
            dim=-1,
        )
        inside = (d @ self.axis) >= math.cos(self.half_angle)
        img = (
            torch.full((H, W), self.ambient, device=device)
            + inside.float() * self.radiance
        )
        return img.unsqueeze(-1).repeat(1, 1, 3).float()

    def cube_image(self, res: int, supersample: int = 8) -> torch.Tensor:
        """Texel-averaged radiance on a cube map (disc coverage by supersampling)."""
        fine, fw = cube_directions(res * supersample, self.axis.device)
        inside = ((fine @ self.axis) >= math.cos(self.half_angle)).float()
        shape = (6, res, supersample, res, supersample)
        cover = (inside * fw).reshape(shape).sum((2, 4)) / fw.reshape(shape).sum(
            (2, 4)
        )
        cover = cover.reshape(-1)
        # Rescale so the texel coverage integrates to the exact cap solid angle.
        cover *= 2 * math.pi * (1 - math.cos(self.half_angle)) / (cover * cube_directions(res, self.axis.device)[1]).sum()
        return self.ambient + self.radiance * cover

    def project(self, w, Y, Y_cap) -> torch.Tensor:
        """Projection of ambient + disc onto a basis sampled at the quadrature (Y) and cap (Y_cap) dirs."""
        return self.ambient * (w[:, None] * Y).sum(0) + self.radiance * self.cap_w * Y_cap.sum(0)


def light_axes(args, up_world, device):
    """World-space light directions from --light-dirs or elevation/azimuth around up."""
    if args.light_dirs:
        return [
            F.normalize(torch.tensor([float(v) for v in s.split(",")], device=device), dim=0)
            for s in args.light_dirs
        ]
    ref = torch.eye(3, device=device)[int(up_world.abs().argmin())]
    e1 = F.normalize(ref - (ref @ up_world) * up_world, dim=0)
    e2 = torch.cross(up_world, e1, dim=0)
    out = []
    for s in args.light_elev_azim:
        el, az = (math.radians(float(v)) for v in s.split(","))
        out.append(
            math.cos(el) * (math.cos(az) * e1 + math.sin(az) * e2) + math.sin(el) * up_world
        )
    return out


# ============================================================================
# Scene setup: robust bounds and training-view visibility
# ============================================================================
class _Pipe:
    convert_SHs_python = False
    compute_cov3D_python = False
    debug = False

    def __init__(self, depth_ratio):
        self.depth_ratio = depth_ratio


def robust_bounds(xyz, opaque, quantile, margin):
    center = xyz[opaque].median(dim=0).values
    dist = torch.norm(xyz - center, dim=1)
    r_q = torch.quantile(dist[opaque][::max(1, int(opaque.sum()) // 1_000_000)], quantile).item()
    return center, r_q, r_q * margin, dist


def load_cameras(path, device):
    cams = []
    for c in json.loads(Path(path).read_text()):
        R = torch.tensor(c["rotation"], dtype=torch.float32, device=device)
        C = torch.tensor(c["position"], dtype=torch.float32, device=device)
        W, H, fx, fy = c["width"], c["height"], c["fx"], c["fy"]
        w2c = torch.eye(4, device=device)
        w2c[:3, :3], w2c[:3, 3] = R.T, -R.T @ C
        wv = w2c.T.contiguous()
        fovx, fovy = 2 * math.atan(W / (2 * fx)), 2 * math.atan(H / (2 * fy))
        proj = rt.getProjectionMatrix(0.01, 100.0, fovx, fovy).T.to(device)
        cam = rt.MiniCam(W, H, fovx, fovy, 0.01, 100.0, wv, wv @ proj, C)
        cams.append(dict(cam=cam, R=R, C=C, W=W, H=H, fx=fx, fy=fy))
    return cams


@torch.no_grad()
def training_views(gaussians, cams, idx, normals_world, view_tol):
    """Per Gaussian: views that see it, sum of sign(n . to_camera) over them, and the smallest
    |depth - rendered surface depth| over views in pixels."""
    from gaussian_renderer import render

    device = normals_world.device
    model, pipe = rt.MockGaussianModel(gaussians), _Pipe(1.0)
    white = torch.ones((gaussians["xyz"].shape[0], 3), device=device)
    xyz = gaussians["xyz"].detach()[idx]
    n = normals_world[idx]
    n_views = torch.zeros(idx.numel(), device=device)
    vote = torch.zeros(idx.numel(), device=device)
    best = torch.full((idx.numel(),), float("inf"), device=device)
    for c in rt.tqdm(cams, desc="Training-view visibility"):
        pkg = render(c["cam"], model, pipe, torch.zeros(3, device=device), override_color=white)
        sd, alpha = pkg["surf_depth"][0], pkg["rend_alpha"][0]
        pc = (xyz - c["C"]) @ c["R"]
        z = pc[:, 2].clamp(min=1e-6)
        u = torch.round(c["fx"] * pc[:, 0] / z + (c["W"] - 1) * 0.5).long()
        v = torch.round(c["fy"] * pc[:, 1] / z + (c["H"] - 1) * 0.5).long()
        inside = (pc[:, 2] > 0.01) & (u >= 0) & (u < c["W"]) & (v >= 0) & (v < c["H"])
        ui, vi = u.clamp(0, c["W"] - 1), v.clamp(0, c["H"] - 1)
        ok = inside & (alpha[vi, ui] > 0.5)
        resid = torch.where(ok, (z - sd[vi, ui]).abs() * c["fx"] / z, torch.full_like(z, float("inf")))
        seen = resid < view_tol
        n_views += seen.float()
        vote += seen.float() * torch.sign(((c["C"] - xyz) * n).sum(1))
        best = torch.minimum(best, resid)
    return n_views, vote, best


# ============================================================================
# Visibility
# ============================================================================
class ShadowMapper:
    """Shadow-map lookups for eval points: hard visibility with several bias modes, and phase-1 ESM+PCF."""

    POISSON = [
        [-0.94201624, -0.39906216],
        [0.94558609, -0.76890725],
        [-0.09418410, -0.92938870],
        [0.34495938, 0.29387760],
        [-0.91588581, 0.45771432],
        [-0.81544232, -0.87912464],
        [-0.38277543, 0.27676845],
        [0.97484398, 0.75648379],
    ]

    def __init__(self, gaussians, eval_idx, normals_sh, center, radius, res, args, esm_res=None):
        from gaussian_renderer import render

        device = normals_sh.device
        self.render = render
        self.model = rt.MockGaussianModel(gaussians)
        self.hard_pipe = _Pipe(1.0 if args.oracle_depth == "median" else 0.0)
        self.esm_pipe = _Pipe(0.0)
        self.res, self.esm_res, self.device = res, esm_res or res, device
        self.center, self.radius = center, radius
        self.bg = torch.zeros(3, device=device)
        self.white = torch.ones((gaussians["xyz"].shape[0], 3), device=device)
        self.xyz = gaussians["xyz"].detach()[eval_idx]
        self.normals = to_sh_frame(normals_sh)
        self.max_scale = torch.max(self.model.get_scaling.detach()[eval_idx], dim=1).values
        self.scale_bias = self.max_scale * 3.0
        self.esm_alpha = 8.0 / radius
        self.poisson = torch.tensor(self.POISSON, device=device) * 1.5
        self.f_const = 1.0 / math.tan(2.0 * math.asin(1.0 / 5.0) * 1.2 / 2.0)
        self.texel = 2.0 * 5.0 * radius / (self.f_const * res)
        self.k_c, self.k_s, self.k_n = args.bias_const, args.bias_slope, args.normal_offset

    def _depth(self, cam, pipe):
        pkg = self.render(cam, self.model, pipe, self.bg, override_color=self.white)
        return pkg["surf_depth"][0], pkg["rend_alpha"][0]

    def _project(self, x, W2C, res):
        view = x @ W2C[:3, :3] + W2C[3, :3]
        depth = view[:, 2]
        half = (res - 1) * 0.5
        u = (view[:, 0] * self.f_const / depth + 1.0) * half + 0.5
        v = (view[:, 1] * self.f_const / depth + 1.0) * half + 0.5
        return u, v, depth

    @staticmethod
    def _lookup(img, u, v):
        res = img.shape[-1]
        ui = torch.clamp(u.long(), 0, res - 1)
        vi = torch.clamp(v.long(), 0, res - 1)
        return img[vi, ui]

    @torch.no_grad()
    def __call__(self, dir_sh: torch.Tensor, modes):
        light = to_sh_frame(dir_sh)
        cam, W2C, _ = rt.create_telephoto_camera(
            self.center, light, self.radius, self.res, self.res, self.device
        )
        out = {}
        hard = [m for m in modes if m != "esm"]
        if hard:
            depth_map, alpha = self._depth(cam, self.hard_pipe)
            cos = (self.normals @ light).clamp(min=0.1, max=1.0)
            for m in hard:
                x, bias = self.xyz, self.scale_bias
                if m == "slope":
                    tan = torch.sqrt(1 - cos * cos) / cos
                    bias = self.texel * (self.k_c + self.k_s * tan)
                elif m.startswith("normal"):
                    k_n = self.k_n * (1.5 if m == "normal_wide" else 1.0)
                    x = x + self.normals * (k_n * self.max_scale)[:, None]
                    tan = torch.sqrt(1 - cos * cos) / cos
                    bias = self.texel * (self.k_c + self.k_s * tan)
                u, v, depth = self._project(x, W2C, self.res)
                sd, a = self._lookup(depth_map, u, v), self._lookup(alpha, u, v)
                blocked = (sd > 0) & (a > 0.5) & (depth - sd - bias > 0)
                out[m] = 1.0 - blocked.float()
        if "esm" in modes:
            if self.esm_res != self.res:
                cam, W2C, _ = rt.create_telephoto_camera(
                    self.center, light, self.radius, self.esm_res, self.esm_res, self.device
                )
            depth_map, _ = self._depth(cam, self.esm_pipe)
            u, v, depth = self._project(self.xyz, W2C, self.esm_res)
            esm = torch.zeros_like(depth)
            for off in self.poisson:
                sd = self._lookup(depth_map, u + off[0], v + off[1])
                valid = (sd > 0).float()
                pen = (depth - sd - self.scale_bias).clamp(min=0.0)
                esm += valid * torch.exp(-self.esm_alpha * pen) + (1.0 - valid)
            out["esm"] = esm / len(self.poisson)
        return out

    def bake(self, dirs, w, modes, store, ao_normals, desc):
        """Visibility for every direction.

        store: modes kept as [N, S] fp16; ao_normals: {key: (mode, normals_sh)} accumulates
        AO = (1/pi) sum_j w_j V_j max(n . w_j, 0).
        """
        n, s = self.xyz.shape[0], dirs.shape[0]
        kept = {m: torch.empty((n, s), dtype=torch.float16, device=self.device) for m in store}
        ao = {k: torch.zeros(n, device=self.device) for k in ao_normals}
        for j in rt.tqdm(range(s), desc=desc):
            vis = self(dirs[j], modes)
            for m in store:
                kept[m][:, j] = vis[m].half()
            for k, (m, nrm) in ao_normals.items():
                ao[k] += w[j] * vis[m] * (nrm @ dirs[j]).clamp(min=0.0)
        return kept, {k: v / math.pi for k, v in ao.items()}


# ============================================================================
# Estimators
# ============================================================================
@torch.no_grad()
def oracle_like(light, normals, D, w, VF, VC, kernel):
    """sum_j w_j L_j V_j k(n.w_j) with exact L (ambient on the quadrature, disc on cap)."""
    amb = (VF.float() * kernel(normals @ D.T) * w).sum(1) * light.ambient
    disc = (VC.float() * kernel(normals @ light.cap_dirs.T)).sum(1) * (
        light.radiance * light.cap_w
    )
    return amb + disc


def oracle_from_ao(light, normals, ao, VC):
    """Oracle with exact cosine from a precomputed AO (ambient is uniform)."""
    disc = (VC.float() * (normals @ light.cap_dirs.T).clamp(min=0.0)).sum(1)
    return light.ambient * math.pi * ao + light.radiance * light.cap_w * disc


@torch.no_grad()
def sh_truncated(light, normals, D, w, VF, VC, Y, Y_cap, mode):
    """Pipeline-style estimate with L and/or V truncated to the bands of Y, l<=2 cosine."""
    k = cos_kernel_l2(normals @ D.T)
    VF = VF.float()
    if mode in ("L", "LV"):
        L_q = Y @ light.project(w, Y, Y_cap)
    if mode in ("V", "LV"):
        V_lm = (VF * w) @ Y
        V_q = V_lm @ Y.T
    if mode == "L":
        return (L_q * VF * k * w).sum(1)
    if mode == "LV":
        return (L_q * V_q * k * w).sum(1)
    amb = (V_q * k * w).sum(1) * light.ambient
    disc = ((V_lm @ Y_cap.T) * cos_kernel_l2(normals @ light.cap_dirs.T)).sum(1) * (
        light.radiance * light.cap_w
    )
    return amb + disc


class Pipeline:
    """The diffuse path of phase_1_bake_visibility_sh + phase_2_decoupled_relight at l_max=3."""

    L_MAX = 3

    def __init__(self, num_samples, device):
        (self.dirs, self.sqrt_w, _, self.A_w, self.AT_A_w, _, self.gaunt) = (
            rt.precompute_sh_sampling(num_samples, self.L_MAX, device)
        )
        self.device = device
        self.A_l = torch.tensor(
            [A_COS[0]] + [A_COS[1]] * 3 + [A_COS[2]] * 5 + [0.0] * 7, device=device
        )

    @torch.no_grad()
    def bake_original(self, gaussians, res):
        return rt.phase_1_bake_visibility_sh(
            gaussians, self.dirs, self.A_w, self.AT_A_w, self.sqrt_w, self.device, res=res
        )

    def project(self, vis):
        """Phase-1 least squares from per-direction visibility [N, S]."""
        AT_b = self.A_w.T @ (vis.float() * self.sqrt_w).T
        return torch.linalg.solve(self.AT_A_w, AT_b).T

    @torch.no_grad()
    def __call__(self, V_lm, normals_sh, L_lm):
        L_shad = torch.einsum("ijk,ic,nj->nkc", self.gaunt, L_lm, V_lm)
        Y_hat = rt.evaluate_sh_bases_torch(normals_sh, self.L_MAX, self.device) * self.A_l
        return torch.einsum("nk,nkc->nc", Y_hat, L_shad).clamp(min=0.0)[:, 0]

    def light_from_image(self, img):
        return rt.compute_global_sh_coeffs(
            img, self.dirs, self.sqrt_w, self.A_w, self.AT_A_w
        )

    def light_exact(self, light, D, w):
        basis = lambda d: rt.evaluate_sh_bases_torch(d, self.L_MAX, self.device)
        return light.project(w, basis(D), basis(light.cap_dirs)).unsqueeze(1).repeat(1, 3)


@torch.no_grad()
def compact_study(lights, normals, VF, VC, D, w, res, Y_all, sh_orders, haar_counts, chunk):
    """C_* rows: SH vs Haar representations of V, L*V and V*cos on the oracle cube map.

    C_H_* (hybrid): the disc is shadowed exactly (as a per-light shadow map at relight time would),
    only the ambient part goes through the compressed V.

    Returns ({light: {row: E}}, {rep: mean relative L2 error}).
    """
    swn = torch.sqrt(w / w.mean())
    reps = [("cube", "cube", None)]
    reps += [(f"sh{(l + 1) ** 2}", "sh", (l + 1) ** 2) for l in sh_orders]
    reps += [(f"haar{k}", "haar", k) for k in haar_counts]

    def approx(X, kind, p):
        if kind == "cube":
            return X, None
        if kind == "sh":
            coef = (X * w) @ Y_all[:, :p]
            return coef @ Y_all[:, :p].T, coef
        return haar_topk(X * swn, res, p) / swn, None

    def rel_l2(X, Xh):
        return torch.sqrt(((X - Xh) ** 2 * w).sum(1) / (X * X * w).sum(1).clamp(min=1e-12))

    cap = {}
    for lt in lights:
        Lc = lt.cube_image(res)
        L_hat, L_err = {}, {}
        for label, kind, p in reps:
            L_hat[label] = approx(Lc[None], kind, p)[0][0]
            L_err[label] = rel_l2(Lc[None], L_hat[label][None]).item()
        cap[lt.name] = dict(
            idx=cube_lookup(lt.cap_dirs, res),
            Y=real_sh(lt.cap_dirs, int(math.isqrt(Y_all.shape[1])) - 1),
            L_hat=L_hat,
            L_err=L_err,
        )

    E = {lt.name: {} for lt in lights}
    err = {}
    for a in range(0, VF.shape[0], chunk):
        n = normals[a : a + chunk]
        V = VF[a : a + chunk].float()
        k_T = (n @ D.T).clamp(min=0.0)
        for target, X in (("V", V), ("T", V * k_T)):
            for label, kind, p in reps:
                Xh, coef = approx(X, kind, p)
                err.setdefault(f"{target}_{label}", []).append(rel_l2(X, Xh))
                for lt in lights:
                    c = cap[lt.name]
                    Xc = coef @ c["Y"][:, :p].T if kind == "sh" else Xh[:, c["idx"]]
                    if target == "V":
                        k_C = (n @ lt.cap_dirs.T).clamp(min=0.0)
                        e = lt.ambient * (Xh * k_T * w).sum(1) + lt.radiance * lt.cap_w * (
                            Xc * k_C
                        ).sum(1)
                        E[lt.name].setdefault(f"C_V_{label}", []).append(e)
                        e_lv = (c["L_hat"][label] * Xh * k_T * w).sum(1)
                        E[lt.name].setdefault(f"C_LV_{label}", []).append(e_lv)
                        e_h = lt.ambient * (Xh * k_T * w).sum(1) + lt.radiance * lt.cap_w * (
                            VC[lt.name][a : a + chunk].float() * k_C
                        ).sum(1)
                        E[lt.name].setdefault(f"C_H_{label}", []).append(e_h)
                    else:
                        e = lt.ambient * (Xh * w).sum(1) + lt.radiance * lt.cap_w * Xc.sum(1)
                        E[lt.name].setdefault(f"C_T_{label}", []).append(e)
    E = {k: {r: torch.cat(v) for r, v in rows.items()} for k, rows in E.items()}
    approx_err = {k: float(torch.cat(v).mean()) for k, v in err.items()}
    for lt in lights:
        for label, e in cap[lt.name]["L_err"].items():
            approx_err[f"L_{lt.name}_{label}"] = e
    return E, approx_err


# ============================================================================
# Metrics
# ============================================================================
def regions(light, normals, VC):
    facing = (normals @ light.axis) > 0.1
    lit_frac = VC.float().mean(1)
    return {
        "all": torch.ones_like(facing),
        "lit": facing & (lit_frac >= 0.98),
        "penumbra": facing & (lit_frac > 0.02) & (lit_frac < 0.98),
        "umbra": facing & (lit_frac <= 0.02),
    }


def metrics(E, E0, masks):
    out = {}
    lit_mean = E0[masks["lit"]].mean().clamp(min=1e-8) if masks["lit"].any() else None
    for name, m in masks.items():
        n = int(m.sum())
        out[f"n_{name}"] = n
        mae = (E[m] - E0[m]).abs().mean() if n else None
        out[f"rel_mae_{name}"] = (
            float(mae / E0[m].mean().clamp(min=1e-8)) if n else float("nan")
        )
        out[f"nmae_{name}"] = (
            float(mae / lit_mean) if n and lit_mean is not None else float("nan")
        )
    if out["n_lit"] and out["n_umbra"]:
        depth = lambda e: (
            1.0
            - float(e[masks["umbra"]].mean() / e[masks["lit"]].mean().clamp(min=1e-8))
        )
        d0 = depth(E0)
        out["shadow_depth"] = depth(E)
        out["shadow_depth_ratio"] = (
            out["shadow_depth"] / d0 if abs(d0) > 1e-8 else float("nan")
        )
    return out


def quantiles(x):
    q = torch.quantile(x.float(), torch.tensor([0.1, 0.25, 0.5, 0.75, 0.9], device=x.device))
    return {
        **{f"q{p}": float(v) for p, v in zip((10, 25, 50, 75, 90), q)},
        "frac_below_0.05": float((x < 0.05).float().mean()),
    }


# ============================================================================
# Report
# ============================================================================
COLS = [
    "nmae_all",
    "nmae_penumbra",
    "nmae_umbra",
    "rel_mae_all",
    "rel_mae_lit",
    "rel_mae_penumbra",
    "rel_mae_umbra",
    "shadow_depth",
    "shadow_depth_ratio",
]


def fmt(v, digits=3):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "-"
    return f"{v:.{digits}f}"


def table(header, rows):
    out = ["| " + " | ".join(header) + " |", "|---" * len(header) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return out + [""]


def summarize(results, approx_err, diag, lights, args):
    """Decision summary: averages over light directions per disc size."""
    sizes = sorted({lt.diameter_deg for lt in lights})
    by_size = {s: [lt.name for lt in lights if lt.diameter_deg == s] for s in sizes}
    small = [s for s in sizes if s <= 5.0] or sizes[:1]

    def avg(method, metric, size):
        vals = [
            results[n][method][metric]
            for n in by_size[size]
            if method in results[n] and not math.isnan(results[n][method].get(metric, float("nan")))
        ]
        return float(np.mean(vals)) if vals else float("nan")

    pen = "nmae_penumbra"
    S = args.pipe_samples[0] if args.pipe_samples else None
    lines = ["# Shadow frequency study", "", "## Decision summary", ""]
    lines += [
        "All errors are `nmae_penumbra` = mean|E - E_oracle| over penumbra points / mean E_oracle over lit points, "
        "averaged over light directions. Thresholds are provisional (`--thr-*`).",
        "",
    ]

    # A. oracle reliability
    lines += ["### A. Oracle reliability", ""]
    sc = diag["scene"]
    lines += [
        f"- scene radius: robust {sc['radius']:.3f} (q{args.radius_quantile} {sc['radius_q']:.3f} x {args.radius_margin}), "
        f"phase-1 formula {sc['radius_phase1']:.3f}; shadow-map texel {sc['texel']:.4f}, median surfel max scale {sc['median_max_scale']:.4f}",
        f"- eval points: {diag['views']['n_eval']} of {diag['views']['n_candidates']} opaque Gaussians inside the radius; "
        f"seen by >= {args.min_views} views: {diag['views']['frac_seen']:.3f}, of which also within {args.surface_tol} px of the rendered surface: {diag['views']['frac_surface']:.3f}; "
        f"normal flipped by camera vote: {diag['views']['frac_flipped']:.3f}; vote agreement median {diag['views']['agreement_median']:.3f}",
        "",
    ]
    rows = [[k, *(fmt(v[c]) for c in ("q10", "q25", "q50", "q75", "q90", "frac_below_0.05"))] for k, v in diag["ao"].items()]
    lines += ["AO = (1/pi) int V max(n.w,0) on eval points (healthy exterior surfaces: median well above 0.3):", ""]
    lines += table(["visibility / normals", "q10", "q25", "q50", "q75", "q90", "frac<0.05"], rows)
    conv = [m for m in ("oracle_res2x", "oracle_dir2x") if m in results[lights[0].name]]
    conv += sorted(
        (f"oracle_bias_{m}" for m in HARD_MODES if f"oracle_bias_{m}" in results[lights[0].name]),
        key=lambda m: "wide" not in m,
    )
    rows = []
    for s in sizes:
        r0 = results[by_size[s][0]]["_regions"]
        rows.append(
            [f"{s:g}", fmt(r0["frac_penumbra"]), fmt(r0["frac_umbra"])]
            + [fmt(avg(m, pen, s)) for m in conv]
            + [fmt(avg(m, "nmae_all", s)) for m in conv[:2]]
        )
    lines += [
        "Convergence and bias sensitivity: res2x, dir2x and normal_wide should be small next to the errors below "
        "(scale/slope are the acne-prone biases, shown for reference):",
        "",
    ]
    lines += table(
        ["disc deg", "frac penumbra", "frac umbra"]
        + [f"{m} pen" for m in conv]
        + [f"{m} all" for m in conv[:2]],
        rows,
    )

    # B. after easy fixes, is SH truncation the main error?
    verdict = {}
    if S:
        lines += ["### B. After easy fixes, is SH truncation the main error?", ""]
        cols = [f"pipe{S}", f"pipe{S}_exactL", f"pipefix{S}", f"pipefix{S}_hard", "filt", "cos2", "sh3_LV", "sh9_LV"]
        rows, shares = [], {}
        for s in sizes:
            vals = {c: avg(c, pen, s) for c in cols}
            share = vals["sh3_LV"] / vals[f"pipefix{S}"] if vals[f"pipefix{S}"] > 0 else float("nan")
            share_h = vals["sh3_LV"] / vals[f"pipefix{S}_hard"] if vals[f"pipefix{S}_hard"] > 0 else float("nan")
            shares[s] = share
            rows.append([f"{s:g}"] + [fmt(vals[c]) for c in cols] + [fmt(share), fmt(share_h)])
        lines += [
            f"`share` = sh3_LV / pipefix{S} (SH-truncation part of the easy-fixed pipeline error); "
            f"`share_hard` = sh3_LV / pipefix{S}_hard.",
            "",
        ]
        lines += table(["disc deg"] + cols + ["share", "share_hard"], rows)
        verdict["B1: SH truncation >= thr_share of fixed-pipeline penumbra error (small lights)"] = all(
            shares[s] >= args.thr_share for s in small
        )
    orders = [l for l in args.sh_orders if f"sh{l}_LV" in results[lights[0].name]]
    if orders:
        lines += ["### SH order needed", ""]
        rows = [[f"{s:g}"] + [fmt(avg(f"sh{l}_LV", pen, s)) for l in orders] + [fmt(avg("cos2", pen, s))] for s in sizes]
        lines += table(["disc deg"] + [f"sh{l}_LV" for l in orders] + ["cos2 (floor)"], rows)
        lmax = max(orders)
        verdict[f"B2: sh{lmax}_LV penumbra nMAE >= thr_large for small lights"] = all(
            avg(f"sh{lmax}_LV", pen, s) >= args.thr_large for s in small
        )

    # C. wavelet vs SH, compression error alone (against the uncompressed cube map)
    pen_c = "nmae_penumbra_vscube"
    sh_counts = [(l + 1) ** 2 for l in args.compact_sh_orders]
    lines += [
        "### C. Haar wavelet vs SH (compression error alone)",
        "",
        f"Errors are `{pen_c}`: against the uncompressed cube map of the same target, so the cube-map floor "
        "(`cube vs oracle`, discretisation of the direction sphere) is left out. "
        "Haar stores an index per coefficient, so haar{K/2} has the memory of sh{K}. ratio = SH / Haar (> 1: Haar better).",
        "",
    ]
    reps = sorted(
        [(k, f"sh{k}") for k in sh_counts] + [(k, f"haar{k}") for k in args.haar_counts]
    )
    targets = (
        ("V", "visibility compressed, exact L (TranSplat stores V)"),
        ("LV", "light and visibility compressed (triple-product setting)"),
        ("T", "transfer V*max(n.w,0) compressed, exact L (classic PRT, diffuse)"),
    )
    for target, desc in targets:
        rows = []
        for s in sizes:
            row = [f"{s:g}", fmt(avg(f"C_{target}_cube", pen, s))]
            row += [fmt(avg(f"C_{target}_{r}", pen_c, s)) for _, r in reps]
            for k in sh_counts:
                e_sh = avg(f"C_{target}_sh{k}", pen_c, s)
                for kh in (k, k // 2):
                    e_h = avg(f"C_{target}_haar{kh}", pen_c, s)
                    row.append(fmt(e_sh / e_h, 2) if e_h > 0 else "-")
            rows.append(row)
        header = ["disc deg", "cube vs oracle"] + [r for _, r in reps]
        for k in sh_counts:
            header += [f"ratio{k}", f"ratio{k} mem"]
        lines += [f"**{target}**: {desc}", ""]
        lines += table(header, rows)
    rows = [[f"{s:g}"] + [fmt(avg(f"C_H_{r}", pen, s)) for _, r in reps] for s in sizes]
    lines += [
        "**H** (hybrid): the disc is shadowed exactly at relight time (a per-light shadow map), only the ambient "
        "part uses the compressed V. Errors against the oracle; the synthetic ambient is uniform, so this is the "
        "best case of separating sharp lights from the rest:",
        "",
    ]
    lines += table(["disc deg"] + [r for _, r in reps], rows)
    rows = []
    for target in ("V", "T"):
        rows.append(
            [target]
            + [fmt(approx_err.get(f"{target}_sh{k}")) for k in sh_counts]
            + [fmt(approx_err.get(f"{target}_haar{k}")) for k in args.haar_counts]
        )
    lines += ["Mean relative L2 approximation error per point (sphere-weighted):", ""]
    lines += table(["target"] + [f"sh{k}" for k in sh_counts] + [f"haar{k}" for k in args.haar_counts], rows)
    for target in ("V", "LV", "T"):
        for k in sh_counts:
            for kh, tag in ((k, "same K"), (k // 2, "same memory")):
                if kh not in args.haar_counts:
                    continue
                verdict[f"C: {target} haar{kh} >= thr_ratio x better than sh{k} ({tag}, small lights)"] = all(
                    avg(f"C_{target}_sh{k}", pen_c, s) >= args.thr_ratio * avg(f"C_{target}_haar{kh}", pen_c, s)
                    for s in small
                )
    lines += [
        "### Verdict (provisional thresholds: "
        f"share {args.thr_share}, large {args.thr_large}, ratio {args.thr_ratio}; small lights = {', '.join(f'{s:g}' for s in small)} deg)",
        "",
    ]
    lines += table(["criterion", "holds"], [[k, "yes" if v else "no"] for k, v in verdict.items()])
    return lines, verdict


def write_markdown(path, results, meta, summary_lines):
    lines = list(summary_lines)
    lines += [
        "## Details",
        "",
        "nmae_* = mean|E - E_oracle| per region / mean(E_oracle over lit); "
        "rel_mae_* = mean|E - E_oracle| / mean(E_oracle) per region; "
        "shadow_depth = 1 - mean(E_umbra)/mean(E_lit); ratio < 1 means washed-out shadows.",
        "",
    ]
    for cfg, rows in results.items():
        info = rows["_regions"]
        lines += [
            f"### {cfg}",
            "",
            f"points: all={info['n_all']} lit={info['n_lit']} penumbra={info['n_penumbra']} umbra={info['n_umbra']}",
            "",
        ]
        lines += table(
            ["method"] + COLS,
            [
                [method] + [fmt(m.get(c), 4) for c in COLS]
                for method, m in rows.items()
                if not method.startswith("_")
            ],
        )
    lines += ["## Run settings", "", "```", json.dumps(meta, indent=2), "```", ""]
    path.write_text("\n".join(lines))


# ============================================================================
# Main
# ============================================================================
def run(args):
    import cv2

    device = "cuda"
    torch.manual_seed(args.seed)
    out_dir = args.output_dir or args.ply.parent / "shadow_frequency_study"
    (out_dir / "envs").mkdir(parents=True, exist_ok=True)
    diag = {}

    gaussians = rt.load_ply(str(args.ply))
    if torch.all(gaussians["normal"] == 0):
        with torch.no_grad():
            gaussians["normal"] = rt.quaternion2rotmat(
                F.normalize(gaussians["rotation"], dim=1)
            )[..., 2]
    normals_world = F.normalize(gaussians["normal"].detach(), dim=1)
    xyz = gaussians["xyz"].detach()
    opaque = torch.sigmoid(gaussians["opacity"].detach()[:, 0]) > args.min_opacity

    # A1: floater-robust bounds for every shadow map in this study (pipe* rows keep phase 1's own).
    center, r_q, radius, dist = robust_bounds(xyz, opaque, args.radius_quantile, args.radius_margin)
    diag["scene"] = dict(
        center=center.tolist(),
        radius_q=r_q,
        radius=radius,
        radius_phase1=float(torch.norm(xyz - xyz.mean(0), dim=1).max()) * 1.8,
        median_max_scale=float(torch.exp(gaussians["scaling"].detach()).max(1).values[opaque].median()),
    )
    # Shadow maps of this study render without floaters; pipe* rows keep phase 1 as is.
    shadow_g = gaussians
    if not args.keep_floaters:
        shadow_g = dict(gaussians)
        shadow_g["opacity"] = gaussians["opacity"].detach().clone()
        shadow_g["opacity"][dist > radius] = -30.0
    diag["scene"]["n_culled"] = 0 if args.keep_floaters else int((dist > radius).sum())

    # A3: evaluate only Gaussians the training views see, with normals oriented towards them.
    cameras_path = args.cameras or args.ply.parents[2] / "cameras.json"
    cams = load_cameras(cameras_path, device)
    candidates = torch.nonzero(opaque & (dist < r_q))[:, 0]
    n_views, vote, resid = training_views(shadow_g, cams, candidates, normals_world, args.view_tol)
    seen = (n_views >= args.min_views) & (resid < args.surface_tol)
    flip = vote < 0
    normals_world[candidates[flip]] *= -1
    diag["views"] = dict(
        n_candidates=int(candidates.numel()),
        frac_seen=float((n_views >= args.min_views).float().mean()),
        frac_surface=float(seen.float().mean()),
        frac_flipped=float(flip[seen].float().mean()),
        agreement_median=float((vote.abs() / n_views.clamp(min=1))[seen].median()),
    )
    if args.up == "auto":
        up = F.normalize(-torch.stack([c["R"][:, 1] for c in cams]).mean(0), dim=0)
    else:
        up = F.normalize(torch.tensor([float(v) for v in args.up.split(",")], device=device), dim=0)
    diag["scene"]["up"] = up.tolist()

    pool = candidates[seen]
    if args.num_eval_points and pool.numel() > args.num_eval_points:
        pool = pool[torch.randperm(pool.numel(), device=device)[: args.num_eval_points]]
    eval_idx = pool.sort().values
    diag["views"]["n_eval"] = int(eval_idx.numel())
    normals = to_sh_frame(normals_world[eval_idx])
    raw_normals = to_sh_frame(
        F.normalize(
            rt.quaternion2rotmat(F.normalize(gaussians["rotation"].detach()[eval_idx], dim=1))[..., 2],
            dim=1,
        )
    )
    print(
        f"Gaussians: {xyz.shape[0]}  eval points: {eval_idx.numel()}  radius: {radius:.3f} "
        f"(phase 1: {diag['scene']['radius_phase1']:.3f})  up: {[round(v, 3) for v in up.tolist()]}"
    )

    lights = []
    for i, axis_world in enumerate(light_axes(args, up, device)):
        for size in args.disc_sizes:
            lights.append(
                DiscLight(
                    f"dir{i}_{size:g}deg",
                    to_sh_frame(axis_world),
                    size,
                    args.ambient,
                    args.sun_irradiance,
                    args.cap_samples,
                )
            )

    t0 = time.time()
    D, w = cube_directions(args.cube_res, device)
    mapper = ShadowMapper(shadow_g, eval_idx, normals, center, radius, args.shadow_res, args, args.esm_res)
    diag["scene"]["texel"] = mapper.texel
    if args.only_compact:
        all_modes, store = [args.bias], [args.bias]
        ao_keys = {args.bias: (args.bias, normals)}
        args.no_convergence, args.pipe_samples = True, []
    else:
        all_modes, store = list(HARD_MODES) + ["esm"], [args.bias, "esm"]
        ao_keys = {f"{m}": (m, normals) for m in HARD_MODES}
        ao_keys["scale / unoriented normals (old study)"] = ("scale", raw_normals)
    kept, ao = mapper.bake(D, w, all_modes, store, ao_keys, "Oracle visibility (cube map)")
    VF_hard, VF_esm = kept[args.bias], kept.get("esm")
    diag["ao"] = {k: quantiles(v) for k, v in ao.items()}
    VC = {}
    for lt in lights:
        caps, _ = mapper.bake(lt.cap_dirs, None, all_modes, all_modes, {}, f"Oracle visibility ({lt.name})")
        VC[lt.name] = caps

    # A6: convergence of the oracle itself.
    conv = {}
    if not args.no_convergence:
        m2 = ShadowMapper(shadow_g, eval_idx, normals, center, radius, 2 * args.shadow_res, args)
        _, ao2 = m2.bake(D, w, [args.bias], [], {"a": (args.bias, normals)}, "Convergence: 2x shadow res")
        conv["oracle_res2x"] = (
            ao2["a"],
            {lt.name: m2.bake(lt.cap_dirs, None, [args.bias], [args.bias], {}, f"2x res ({lt.name})")[0][args.bias] for lt in lights},
            {lt.name: lt for lt in lights},
        )
        D2, w2 = cube_directions(round(args.cube_res * math.sqrt(2)), device)
        _, ao3 = mapper.bake(D2, w2, [args.bias], [], {"a": (args.bias, normals)}, "Convergence: 2x directions")
        lights2 = {lt.name: lt.with_cap_samples(2 * args.cap_samples) for lt in lights}
        conv["oracle_dir2x"] = (
            ao3["a"],
            {n: mapper.bake(lt.cap_dirs, None, [args.bias], [args.bias], {}, f"2x dirs ({n})")[0][args.bias] for n, lt in lights2.items()},
            lights2,
        )
        del m2

    pipes = {}
    for s_count in args.pipe_samples:
        pipe = Pipeline(s_count, device)
        vis, _ = mapper.bake(pipe.dirs, None, [args.bias, "esm"], [args.bias, "esm"], {}, f"Pipefix visibility ({s_count})")
        pipes[s_count] = dict(
            pipe=pipe,
            orig=pipe.bake_original(gaussians, args.esm_res)[eval_idx],
            fix=pipe.project(vis["esm"]),
            fix_hard=pipe.project(vis[args.bias]),
        )
        del vis
    print(f"Visibility baked in {time.time() - t0:.1f}s")

    sh_orders = [] if args.only_compact else args.sh_orders
    l_needed = max(sh_orders + args.compact_sh_orders)
    Y_all = real_sh(D, l_needed)

    def chunked(fn):
        return torch.cat(
            [
                fn(slice(a, a + args.chunk))
                for a in range(0, eval_idx.numel(), args.chunk)
            ]
        )

    print("Compact representations (C) ...")
    E_compact, approx_err = compact_study(
        lights, normals, VF_hard, {n: v[args.bias] for n, v in VC.items()}, D, w,
        args.cube_res, Y_all, args.compact_sh_orders, args.haar_counts, args.chunk,
    )

    results, per_point = {}, {"eval_idx": eval_idx.cpu().numpy(), "normals_sh": normals.cpu().numpy()}
    clamp = lambda t: t.clamp(min=0.0)
    for lt in lights:
        img = lt.equirect(args.env_height)
        cv2.imwrite(
            str(out_dir / "envs" / f"{lt.name}.hdr"),
            img.cpu().numpy()[..., ::-1].copy(),
        )
        VC_hard, VC_esm = VC[lt.name][args.bias], VC[lt.name].get("esm")

        E = {
            "oracle": chunked(
                lambda s: oracle_like(lt, normals[s], D, w, VF_hard[s], VC_hard[s], clamp)
            ),
        }
        for name, (ao_c, vc_c, lts) in conv.items():
            E[name] = oracle_from_ao(lts[lt.name], normals, ao_c, vc_c[lt.name])
        for m in HARD_MODES:
            if m != args.bias and m in ao:
                E[f"oracle_bias_{m}"] = oracle_from_ao(lt, normals, ao[m], VC[lt.name][m])
        if VF_esm is not None:
            E["filt"] = chunked(
                lambda s: oracle_like(lt, normals[s], D, w, VF_esm[s], VC_esm[s], clamp)
            )
        E["cos2"] = chunked(
            lambda s: oracle_like(lt, normals[s], D, w, VF_hard[s], VC_hard[s], cos_kernel_l2)
        )
        Y_cap_all = real_sh(lt.cap_dirs, l_needed)
        for l in sh_orders:
            K = (l + 1) ** 2
            for mode in ("L", "V", "LV"):
                E[f"sh{l}_{mode}"] = chunked(
                    lambda s: sh_truncated(
                        lt, normals[s], D, w, VF_hard[s], VC_hard[s], Y_all[:, :K], Y_cap_all[:, :K], mode
                    )
                )
        for s_count, p in pipes.items():
            pipe = p["pipe"]
            L_img, L_exact = pipe.light_from_image(img), pipe.light_exact(lt, D, w)
            E[f"pipe{s_count}"] = pipe(p["orig"], normals, L_img)
            E[f"pipe{s_count}_exactL"] = pipe(p["orig"], normals, L_exact)
            E[f"pipefix{s_count}"] = pipe(p["fix"], normals, L_exact)
            E[f"pipefix{s_count}_hard"] = pipe(p["fix_hard"], normals, L_exact)
        E.update(E_compact[lt.name])

        masks = regions(lt, normals, VC_hard)
        n_all = int(masks["all"].sum())
        rows = {"_regions": {f"n_{k}": int(v.sum()) for k, v in masks.items()}}
        rows["_regions"].update({f"frac_{k}": int(v.sum()) / n_all for k, v in masks.items()})
        for name, e in E.items():
            rows[name] = metrics(e, E["oracle"], masks)
            if name.startswith("C_"):
                # Compression error alone: against the uncompressed cube map of the same target.
                ref = E["C_" + name.split("_")[1] + "_cube"]
                m_ref = metrics(e, ref, masks)
                rows[name].update({f"{k}_vscube": v for k, v in m_ref.items() if k.startswith("nmae")})
            per_point[f"{lt.name}__{name}"] = e.cpu().numpy()
        per_point[f"{lt.name}__lit_frac"] = VC_hard.float().mean(1).cpu().numpy()
        results[lt.name] = rows
        print(
            f"[{lt.name}] penumbra nMAE "
            + "  ".join(
                f"{k}={rows[k]['nmae_penumbra']:.3f}"
                for k in ("filt", "sh3_LV", "sh9_LV", "pipefix1200", "C_LV_sh16", "C_LV_haar16")
                if k in rows
            )
        )

    meta = {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(args).items()}
    meta["num_gaussians"] = int(xyz.shape[0])
    meta["lights_world"] = {lt.name: to_sh_frame(lt.axis).tolist() for lt in lights}
    summary, verdict = summarize(results, approx_err, diag, lights, args)
    (out_dir / "results.json").write_text(
        json.dumps(
            {"meta": meta, "diagnostics": diag, "approx_err": approx_err, "verdict": verdict, "results": results},
            indent=2,
        )
    )
    write_markdown(out_dir / "results.md", results, meta, summary)
    np.savez_compressed(out_dir / "per_point.npz", **per_point)
    if args.save_visibility:
        np.savez_compressed(
            out_dir / "visibility.npz",
            cube_dirs_sh=D.cpu().numpy(),
            cube_weights=w.cpu().numpy(),
            V_hard=VF_hard.cpu().numpy(),
            normals_sh=normals.cpu().numpy(),
            xyz=mapper.xyz.cpu().numpy(),
            eval_idx=eval_idx.cpu().numpy(),
        )
    print("\n".join(summary))
    print(f"Wrote {out_dir / 'results.md'}")


def self_test():
    torch.manual_seed(0)
    dev = "cpu"
    fib = fibonacci_directions(20000, dev)
    w = FOUR_PI / fib.shape[0]

    Y = real_sh(fib, 9)
    gram = Y.T @ Y * w
    err = (gram - torch.eye(gram.shape[0])).abs().max().item()
    print(f"real_sh orthonormality (l<=9) max err: {err:.2e}")
    assert err < 1e-2

    # Same span as the pipeline basis at l=3: projecting either one onto the other is lossless.
    Yp = rt.evaluate_sh_bases_torch(fib, 3, dev)
    Y3 = Y[:, :16]
    resid = (Yp - Y3 @ (Y3.T @ Yp * w)).abs().max().item()
    print(f"span(real_sh l<=3) vs evaluate_sh_bases_torch residual: {resid:.2e}")
    assert resid < 1e-2

    # The l<=2 kernel reproduces phase 2's A_l-weighted reconstruction for any lighting.
    n = F.normalize(torch.randn(8, 3), dim=1)
    f = torch.rand(fib.shape[0])
    f_lm = Yp.T @ f * w
    A_l = torch.tensor([A_COS[0]] + [A_COS[1]] * 3 + [A_COS[2]] * 5 + [0.0] * 7)
    e_pipe = (rt.evaluate_sh_bases_torch(n, 3, dev) * A_l) @ f_lm
    e_kern = (cos_kernel_l2(n @ fib.T) * f).sum(1) * w
    kerr = (e_pipe - e_kern).abs().max().item()
    print(f"cos_kernel_l2 vs phase-2 A_l reconstruction max err: {kerr:.2e}")
    assert kerr < 1e-3

    # Disc light: irradiance at normal incidence equals sun_irradiance for every size.
    for size in (2.0, 10.0, 30.0):
        lt = DiscLight("t", torch.tensor([0.2, -0.3, 0.9]), size, 0.0, 3.0, 256)
        inside = (
            ((lt.cap_dirs @ lt.axis) >= math.cos(lt.half_angle) - 1e-6).all().item()
        )
        e = (lt.cap_dirs @ lt.axis).sum().item() * lt.cap_w * lt.radiance
        print(
            f"disc {size:>4g} deg: E_normal={e:.4f} (expect 3.0) samples_in_cap={inside}"
        )
        assert inside and abs(e - 3.0) < 1e-2

    # Cube map: weights integrate the sphere, lookup inverts the texel layout, SH stays orthonormal.
    res = 32
    D, wc = cube_directions(res, dev)
    assert abs(wc.sum().item() - FOUR_PI) < 1e-4
    assert torch.equal(cube_lookup(D, res), torch.arange(D.shape[0]))
    Yc = real_sh(D, 7)
    cerr = ((Yc.T * wc) @ Yc - torch.eye(64)).abs().max().item()
    print(f"cube map: lookup ok, real_sh orthonormality (l<=7) max err: {cerr:.2e}")
    assert cerr < 1e-2

    # Haar: orthonormal and perfectly invertible; keeping all coefficients is lossless.
    x = torch.randn(3, 6, res, res, dtype=torch.float64)
    c = haar2d(x)
    herr = (ihaar2d(c) - x).abs().max().item()
    norm_err = abs(c.pow(2).sum().item() - x.pow(2).sum().item()) / x.pow(2).sum().item()
    full_err = (haar_topk(x.reshape(3, -1), res, 6 * res * res) - x.reshape(3, -1)).abs().max().item()
    print(f"haar: inverse err {herr:.2e}, energy err {norm_err:.2e}, full top-k err {full_err:.2e}")
    assert herr < 1e-10 and norm_err < 1e-10 and full_err < 1e-10
    # A constant map needs only the 6 face-average coefficients.
    one = torch.ones(1, 6 * res * res)
    assert (haar_topk(one, res, 6) - one).abs().max().item() < 1e-5

    # Disc cube image carries the disc's energy.
    lt = DiscLight("t", torch.tensor([0.2, -0.3, 0.9]), 5.0, 0.0, 3.0, 64)
    energy = (lt.cube_image(64) * cube_directions(64, dev)[1]).sum().item()
    expect = lt.radiance * 2 * math.pi * (1 - math.cos(lt.half_angle))
    print(f"disc cube image energy {energy:.4f} (expect {expect:.4f})")
    assert abs(energy / expect - 1) < 1e-2
    print("self-test OK")


if __name__ == "__main__":
    args = parse_args()
    if args.self_test:
        self_test()
    else:
        run(args)
