#!/usr/bin/env python3
"""Measure where high-frequency self-shadow detail is lost in TranSplat.

Lights a trained model with synthetic environment maps (uniform ambient plus
a disc light of varying angular size) and compares per-Gaussian diffuse
irradiance from several estimators against a dense, non-band-limited oracle:

    E(x) = sum_j w_j * L(w_j) * V(x, w_j) * max(n . w_j, 0)

Each estimator changes one step relative to the oracle, so the error table
attributes the loss to a specific cause:

    oracle         hard shadow-map visibility, exact L, exact clamped cosine
    filt           ESM + PCF visibility (as in phase 1)          -> filtering
    cos2           clamped cosine truncated to l<=2 (as phase 2) -> cosine band limit
    sh{l}_L        L truncated to SH order l                     -> light band limit
    sh{l}_V        V truncated to SH order l                     -> visibility band limit
    sh{l}_LV       both truncated (current method at l=3)        -> triple product
    pipe{S}        the actual phase 1 + phase 2 diffuse path with S directions,
                   L sampled from the equirect HDR (nearest lookup)
    pipe{S}_exactL same, but with exactly projected L            -> env sampling

All sh*/pipe* rows use the l<=2 cosine, so compare them against `cos2` as well
as `oracle`. Directions are expressed in the SH frame used by
radiance_transfer_TranSplat.py (world x flipped).

Run `--self-test` (CPU only) to check the SH/quadrature math without a model.
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Check SH/quadrature math on CPU and exit",
    )
    parser.add_argument("--ply", type=Path, help="Trained point_cloud.ply")
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
        "--light-dirs",
        nargs="+",
        default=["0.3,0.3,0.9", "0.9,0.3,0.3", "0.3,0.9,0.3"],
        help="World-space light directions as x,y,z (normalized); quote a leading minus as ' -0.3,0.3,0.9'",
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
        "--oracle-samples",
        type=int,
        default=4096,
        help="Fibonacci directions for ambient/visibility (one shadow map each)",
    )
    parser.add_argument(
        "--cap-samples", type=int, default=64, help="Directions inside each disc light"
    )
    parser.add_argument(
        "--pipe-samples",
        nargs="*",
        type=int,
        default=[1200],
        help="num_samples values for the actual-pipeline rows (empty to skip)",
    )
    parser.add_argument("--shadow-res", type=int, default=1024)
    parser.add_argument(
        "--env-height", type=int, default=512, help="Equirect HDR height (width = 2x)"
    )
    parser.add_argument(
        "--num-eval-points",
        type=int,
        default=20000,
        help="Gaussians to evaluate (0 = all; visibility needs ~4 bytes x points x directions of GPU memory)",
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
        help="Save hard visibility on the Fibonacci directions (input for the wavelet study)",
    )
    args = parser.parse_args()
    if not args.self_test and args.ply is None:
        parser.error("--ply is required unless --self-test")
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
        self.cap_dirs, self.cap_w = cap_directions(
            self.axis, self.half_angle, cap_samples
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

    def project(self, fib_dirs: torch.Tensor, basis) -> torch.Tensor:
        """Exact-ish projection of ambient + disc onto `basis` (callable dirs -> [S, K])."""
        w_fib = FOUR_PI / fib_dirs.shape[0]
        return self.ambient * w_fib * basis(fib_dirs).sum(
            0
        ) + self.radiance * self.cap_w * basis(self.cap_dirs).sum(0)


# ============================================================================
# Visibility
# ============================================================================
class ShadowMapper:
    """Phase-1 shadow-map lookups, returning hard and ESM+PCF visibility for eval points."""

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

    def __init__(self, gaussians, eval_idx, res, device):
        from gaussian_renderer import render

        self.render = render
        self.model = rt.MockGaussianModel(gaussians)
        self.pipe = rt.MockPipeline()
        self.res, self.device = res, device
        xyz = gaussians["xyz"].detach()
        self.center = xyz.mean(dim=0)
        self.radius = torch.max(torch.norm(xyz - self.center, dim=1)).item() * 1.8
        self.bg = torch.zeros(3, device=device)
        self.white = torch.ones((xyz.shape[0], 3), device=device)
        self.xyz = xyz[eval_idx]
        self.bias = (
            torch.max(self.model.get_scaling.detach()[eval_idx], dim=1).values * 3.0
        )
        self.esm_alpha = 8.0 / self.radius
        self.poisson = torch.tensor(self.POISSON, device=device) * 1.5
        self.f_const = 1.0 / math.tan(2.0 * math.asin(1.0 / 5.0) * 1.2 / 2.0)

    @torch.no_grad()
    def __call__(self, dir_sh: torch.Tensor):
        cam, W2C, _ = rt.create_telephoto_camera(
            self.center,
            to_sh_frame(dir_sh),
            self.radius,
            self.res,
            self.res,
            self.device,
        )
        pkg = self.render(
            cam, self.model, self.pipe, self.bg, override_color=self.white
        )
        depth_map = pkg["surf_depth"][0] if "surf_depth" in pkg else pkg["depth"][0]
        view = self.xyz @ W2C[:3, :3] + W2C[3, :3]
        depth = view[:, 2]
        half = (self.res - 1) * 0.5
        u = (view[:, 0] * self.f_const / depth + 1.0) * half + 0.5
        v = (view[:, 1] * self.f_const / depth + 1.0) * half + 0.5

        def lookup(du, dv):
            ui = torch.clamp((u + du).long(), 0, self.res - 1)
            vi = torch.clamp((v + dv).long(), 0, self.res - 1)
            sd = depth_map[vi, ui]
            return sd, (sd > 0).float()

        sd, valid = lookup(0.0, 0.0)
        hard = 1.0 - valid * (depth - sd - self.bias > 0).float()
        esm = torch.zeros_like(depth)
        for off in self.poisson:
            sd, valid = lookup(off[0], off[1])
            pen = (depth - sd - self.bias).clamp(min=0.0)
            esm += valid * torch.exp(-self.esm_alpha * pen) + (1.0 - valid)
        return hard, esm / len(self.poisson)

    def bake(self, dirs: torch.Tensor, desc: str):
        n, s = self.xyz.shape[0], dirs.shape[0]
        hard = torch.empty((n, s), dtype=torch.float16, device=self.device)
        esm = torch.empty((n, s), dtype=torch.float16, device=self.device)
        for j in rt.tqdm(range(s), desc=desc):
            h, e = self(dirs[j])
            hard[:, j], esm[:, j] = h.half(), e.half()
        return hard, esm


# ============================================================================
# Estimators
# ============================================================================
@torch.no_grad()
def oracle_like(light, normals, fib, VF, VC, kernel):
    """sum_j w_j L_j V_j k(n.w_j) with exact L (ambient on fib, disc on cap)."""
    w_fib = FOUR_PI / fib.shape[0]
    amb = (VF.float() * kernel(normals @ fib.T)).sum(1) * (light.ambient * w_fib)
    disc = (VC.float() * kernel(normals @ light.cap_dirs.T)).sum(1) * (
        light.radiance * light.cap_w
    )
    return amb + disc


@torch.no_grad()
def sh_truncated(light, normals, fib, VF, VC, l, mode):
    """Pipeline-style estimate with L and/or V truncated to SH order l, l<=2 cosine."""
    w_fib = FOUR_PI / fib.shape[0]
    YF = real_sh(fib, l)
    k_fib = cos_kernel_l2(normals @ fib.T)
    if mode in ("L", "LV"):
        L_lm = light.project(fib, lambda d: real_sh(d, l))
        L_fib = YF @ L_lm
    if mode in ("V", "LV"):
        V_lm = (VF.float() @ YF) * w_fib
        V_fib = V_lm @ YF.T
    if mode == "L":
        return (L_fib.unsqueeze(0) * VF.float() * k_fib).sum(1) * w_fib
    if mode == "LV":
        return (L_fib.unsqueeze(0) * V_fib * k_fib).sum(1) * w_fib
    V_cap = V_lm @ real_sh(light.cap_dirs, l).T
    amb = (V_fib * k_fib).sum(1) * (light.ambient * w_fib)
    disc = (V_cap * cos_kernel_l2(normals @ light.cap_dirs.T)).sum(1) * (
        light.radiance * light.cap_w
    )
    return amb + disc


class Pipeline:
    """The diffuse path of phase_1_bake_visibility_sh + phase_2_decoupled_relight at l_max=3."""

    L_MAX = 3

    def __init__(self, gaussians, num_samples, res, device):
        (self.dirs, self.sqrt_w, self.A, self.A_w, self.AT_A_w, _, self.gaunt) = (
            rt.precompute_sh_sampling(num_samples, self.L_MAX, device)
        )
        with torch.no_grad():
            self.V_lm = rt.phase_1_bake_visibility_sh(
                gaussians,
                self.dirs,
                self.A_w,
                self.AT_A_w,
                self.sqrt_w,
                device,
                res=res,
            )
        self.device = device

    @torch.no_grad()
    def __call__(self, eval_idx, normals_sh, L_lm):
        A_l = torch.tensor(
            [A_COS[0]] + [A_COS[1]] * 3 + [A_COS[2]] * 5 + [0.0] * 7, device=self.device
        )
        L_shad = torch.einsum("ijk,ic,nj->nkc", self.gaunt, L_lm, self.V_lm[eval_idx])
        Y_hat = rt.evaluate_sh_bases_torch(normals_sh, self.L_MAX, self.device) * A_l
        return torch.einsum("nk,nkc->nc", Y_hat, L_shad).clamp(min=0.0)[:, 0]

    def light_from_image(self, img):
        return rt.compute_global_sh_coeffs(
            img, self.dirs, self.sqrt_w, self.A_w, self.AT_A_w
        )

    def light_exact(self, light, fib):
        basis = lambda d: rt.evaluate_sh_bases_torch(d, self.L_MAX, self.device)
        return light.project(fib, basis).unsqueeze(1).repeat(1, 3)


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
    for name, m in masks.items():
        n = int(m.sum())
        out[f"n_{name}"] = n
        out[f"rel_mae_{name}"] = (
            float((E[m] - E0[m]).abs().mean() / E0[m].mean().clamp(min=1e-8))
            if n
            else float("nan")
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


def write_markdown(path: Path, results: dict, meta: dict):
    cols = [
        "rel_mae_all",
        "rel_mae_lit",
        "rel_mae_penumbra",
        "rel_mae_umbra",
        "shadow_depth",
        "shadow_depth_ratio",
    ]
    lines = [
        "# Shadow frequency study",
        "",
        "```",
        json.dumps(meta, indent=2),
        "```",
        "",
        "rel_mae_* = mean|E - E_oracle| / mean(E_oracle) per region; "
        "shadow_depth = 1 - mean(E_umbra)/mean(E_lit); ratio < 1 means washed-out shadows.",
        "",
    ]
    for cfg, rows in results.items():
        info = rows["_regions"]
        lines += [
            f"## {cfg}",
            "",
            f"points: all={info['n_all']} lit={info['n_lit']} penumbra={info['n_penumbra']} umbra={info['n_umbra']}",
            "",
            "| method | " + " | ".join(cols) + " |",
            "|---" * (len(cols) + 1) + "|",
        ]
        for method, m in rows.items():
            if method.startswith("_"):
                continue
            lines.append(
                f"| {method} | "
                + " | ".join("-" if c not in m else f"{m[c]:.4f}" for c in cols)
                + " |"
            )
        lines.append("")
    path.write_text("\n".join(lines))


# ============================================================================
# Main
# ============================================================================
def run(args):
    import cv2

    device = "cuda" if torch.cuda.is_available() else "cpu"
    torch.manual_seed(args.seed)
    out_dir = args.output_dir or args.ply.parent / "shadow_frequency_study"
    (out_dir / "envs").mkdir(parents=True, exist_ok=True)

    gaussians = rt.load_ply(str(args.ply))
    if torch.all(gaussians["normal"] == 0):
        with torch.no_grad():
            gaussians["normal"] = rt.quaternion2rotmat(
                F.normalize(gaussians["rotation"], dim=1)
            )[..., 2]
    normals_all = to_sh_frame(F.normalize(gaussians["normal"].detach(), dim=1))

    candidates = torch.nonzero(
        torch.sigmoid(gaussians["opacity"].detach()[:, 0]) > args.min_opacity
    )[:, 0]
    if args.num_eval_points and candidates.numel() > args.num_eval_points:
        candidates = candidates[
            torch.randperm(candidates.numel(), device=candidates.device)[
                : args.num_eval_points
            ]
        ]
    eval_idx = candidates.sort().values
    normals = normals_all[eval_idx]
    print(f"Gaussians: {gaussians['xyz'].shape[0]}  eval points: {eval_idx.numel()}")

    fib = fibonacci_directions(args.oracle_samples, device)
    lights = []
    for i, spec in enumerate(args.light_dirs):
        axis_world = torch.tensor([float(v) for v in spec.split(",")], device=device)
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
    mapper = ShadowMapper(gaussians, eval_idx, args.shadow_res, device)
    VF_hard, VF_esm = mapper.bake(fib, "Oracle visibility (Fibonacci)")
    VC = {
        lt.name: mapper.bake(lt.cap_dirs, f"Oracle visibility ({lt.name})")
        for lt in lights
    }
    pipes = {
        s: Pipeline(gaussians, s, args.shadow_res, device) for s in args.pipe_samples
    }
    print(f"Visibility baked in {time.time() - t0:.1f}s")

    def chunked(fn):
        return torch.cat(
            [
                fn(slice(a, a + args.chunk))
                for a in range(0, eval_idx.numel(), args.chunk)
            ]
        )

    results, per_point = {}, {"eval_idx": eval_idx.cpu().numpy()}
    for lt in lights:
        img = lt.equirect(args.env_height)
        cv2.imwrite(
            str(out_dir / "envs" / f"{lt.name}.hdr"),
            img.cpu().numpy()[..., ::-1].copy(),
        )
        VC_hard, VC_esm = VC[lt.name]
        clamp = lambda t: t.clamp(min=0.0)

        E = {
            "oracle": chunked(
                lambda s: oracle_like(
                    lt, normals[s], fib, VF_hard[s], VC_hard[s], clamp
                )
            ),
            "filt": chunked(
                lambda s: oracle_like(lt, normals[s], fib, VF_esm[s], VC_esm[s], clamp)
            ),
            "cos2": chunked(
                lambda s: oracle_like(
                    lt, normals[s], fib, VF_hard[s], VC_hard[s], cos_kernel_l2
                )
            ),
        }
        for l in args.sh_orders:
            for mode in ("L", "V", "LV"):
                E[f"sh{l}_{mode}"] = chunked(
                    lambda s: sh_truncated(
                        lt, normals[s], fib, VF_hard[s], VC_hard[s], l, mode
                    )
                )
        for s_count, pipe in pipes.items():
            E[f"pipe{s_count}"] = pipe(eval_idx, normals, pipe.light_from_image(img))
            E[f"pipe{s_count}_exactL"] = pipe(
                eval_idx, normals, pipe.light_exact(lt, fib)
            )

        masks = regions(lt, normals, VC_hard)
        rows = {"_regions": {f"n_{k}": int(v.sum()) for k, v in masks.items()}}
        for name, e in E.items():
            rows[name] = metrics(e, E["oracle"], masks)
            per_point[f"{lt.name}__{name}"] = e.cpu().numpy()
        per_point[f"{lt.name}__lit_frac"] = VC_hard.float().mean(1).cpu().numpy()
        results[lt.name] = rows
        print(
            f"[{lt.name}] "
            + "  ".join(
                f"{k}={v['rel_mae_penumbra']:.3f}"
                for k, v in rows.items()
                if not k.startswith("_")
                and k in ("filt", "cos2", "sh3_LV", "sh9_LV", "pipe1200")
            )
        )

    meta = {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(args).items()}
    meta["num_gaussians"] = int(gaussians["xyz"].shape[0])
    (out_dir / "results.json").write_text(
        json.dumps({"meta": meta, "results": results}, indent=2)
    )
    write_markdown(out_dir / "results.md", results, meta)
    np.savez_compressed(out_dir / "per_point.npz", **per_point)
    if args.save_visibility:
        np.savez_compressed(
            out_dir / "visibility.npz",
            fib_dirs_sh=fib.cpu().numpy(),
            V_hard=VF_hard.cpu().numpy(),
            normals_sh=normals.cpu().numpy(),
            xyz=mapper.xyz.cpu().numpy(),
            eval_idx=eval_idx.cpu().numpy(),
        )
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
    print("self-test OK")


if __name__ == "__main__":
    args = parse_args()
    if args.self_test:
        self_test()
    else:
        run(args)
