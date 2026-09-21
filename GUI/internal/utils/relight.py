"""Relight implementation with cached phase-1 visibility precomputation.

This module adapts the implementation from ``relight-new.py`` into a
callable `relight_gaussian_model` function the GUI expects. The first shadow
relight builds and caches the expensive visibility bake plus the SH sampling
tensors; later relights reuse that cached state and only run the fast transfer
step.
"""

import os
import math
import time
import hashlib
from typing import Optional

import numpy as np
import torch
from torch import nn
import torch.nn.functional as F
import cv2


os.environ['OPENCV_IO_ENABLE_OPENEXR'] = '1'

# SH constants (copied from the original relight implementation)
C0 = 0.28209479177387814
C1 = 0.4886025119029199
C2 = [1.0925484305920792, -1.0925484305920792, 0.31539156525252005, -1.0925484305920792, 0.5462742152960396]
C3 = [-0.5900435899266435, 2.890611442640554, -0.4570457994644658, 0.3731763325901154, -0.4570457994644658, 1.445305721320277, -0.5900435899266435]


VISIBILITY_RES = 1024
class MockGaussianModel:
    def __init__(self, gaussians_dict):
        self.g = gaussians_dict
        self.max_sh_degree = gaussians_dict['max_sh_degree']
        self.active_sh_degree = gaussians_dict['max_sh_degree']

    @property
    def get_xyz(self):
        return self.g['xyz']

    @property
    def get_features(self):
        return torch.cat([self.g['features_dc'], self.g['features_rest']], dim=1)

    @property
    def get_opacity(self):
        return torch.sigmoid(self.g['opacity'])

    @property
    def get_scaling(self):
        scale = torch.exp(self.g['scaling'])
        if scale.shape[1] > 2:
            scale = scale[:, :2]
        return scale.contiguous()

    @property
    def get_rotation(self):
        return F.normalize(self.g['rotation'], dim=1)


class MockPipeline:
    convert_SHs_python = False
    compute_cov3D_python = False
    debug = False
    depth_ratio = 0.0


def getProjectionMatrix(znear, zfar, fovX, fovY):
    tanHalfFovY, tanHalfFovX = math.tan((fovY / 2)), math.tan((fovX / 2))
    top, right = tanHalfFovY * znear, tanHalfFovX * znear
    bottom, left = -top, -right
    P = torch.zeros(4, 4)
    P[0, 0] = 2.0 * znear / (right - left)
    P[1, 1] = 2.0 * znear / (top - bottom)
    P[0, 2] = (right + left) / (right - left)
    P[1, 2] = (top + bottom) / (top - bottom)
    P[2, 2] = zfar / (zfar - znear)
    P[2, 3] = -(zfar * znear) / (zfar - znear)
    P[3, 2] = 1.0
    return P


class MiniCam:
    def __init__(self, W, H, fovX, fovY, znear, zfar, W2C, full_proj, origin):
        self.image_width, self.image_height = W, H
        self.FoVx, self.FoVy = fovX, fovY
        self.znear, self.zfar = znear, zfar
        self.world_view_transform, self.full_proj_transform = W2C, full_proj
        self.camera_center = origin


def create_telephoto_camera(scene_center, direction, radius, W, H, device):
    D = radius * 5.0
    origin = scene_center + direction * D
    forward = F.normalize(scene_center - origin, dim=0)
    up = torch.tensor([0.0, 1.0, 0.0], device=device)
    if abs(torch.dot(forward, up)) > 0.99: up = torch.tensor([1.0, 0.0, 0.0], device=device)
    right = F.normalize(torch.cross(up, forward), dim=0)
    true_up = F.normalize(torch.cross(forward, right), dim=0)
    R = torch.stack([right, -true_up, forward], dim=1)
    t = -origin @ R
    W2C = torch.eye(4, device=device)
    W2C[:3, :3], W2C[3, :3] = R, t
    fovY = 2.0 * math.asin(radius / D) * 1.2
    fovX = fovY
    znear, zfar = D - radius * 1.5, D + radius * 1.5
    P = getProjectionMatrix(znear, zfar, fovX, fovY).transpose(0, 1).to(device)
    return MiniCam(W, H, fovX, fovY, znear, zfar, W2C, W2C @ P, origin), W2C, W2C @ P


def quaternion2rotmat(q):
    r, x, y, z = q.split(1, -1)
    return torch.stack([
        1 - 2 * (y * y + z * z), 2 * (x * y - r * z), 2 * (x * z + r * y),
        2 * (x * y + r * z), 1 - 2 * (x * x + z * z), 2 * (y * z - r * x),
        2 * (x * z - r * y), 2 * (y * z + r * x), 1 - 2 * (x * x + y * y)
    ], -1).reshape([len(q), 3, 3])

def _relight_cache_key(num_samples, l_max, shadow_res, device):
    device_index = device.index if device.index is not None else -1
    return (int(num_samples), int(l_max), int(shadow_res), str(device.type), device_index)


def _mask_cache_token(mask):
    if mask is None:
        return None
    mask_bytes = mask.detach().to(device="cpu", dtype=torch.uint8).contiguous().numpy().tobytes()
    return hashlib.sha1(mask_bytes).hexdigest()


def _normalize_cache_entry(cache_entry):
    if cache_entry is None:
        return {}
    if isinstance(cache_entry, dict):
        return cache_entry
    return {}

def _ensure_relight_cache(gaussian_model, num_samples, l_max, shadow_res, device):
    cache_key = _relight_cache_key(num_samples, l_max, shadow_res, device)
    cache_root = _normalize_cache_entry(getattr(gaussian_model, "_relight_cache", None))
    cached_entry = cache_root.get(cache_key)
    if cached_entry is not None:
        return cached_entry

    directions, sqrt_weights, A, A_weighted, AT_A_weighted, AT_A, gaunt_tensor = precompute_sh_sampling(
        num_samples, l_max, device
    )

    cached_entry = {
        "directions": directions,
        "sqrt_weights": sqrt_weights,
        "A": A,
        "A_weighted": A_weighted,
        "AT_A_weighted": AT_A_weighted,
        "AT_A": AT_A,
        "AT_A_inv": torch.linalg.inv(AT_A),
        "gaunt_tensor": gaunt_tensor,
        "visibility": {},
        "env_sh": {},
        "offset_sh": {},
    }

    cache_root = dict(cache_root)
    cache_root[cache_key] = cached_entry
    gaussian_model._relight_cache = cache_root
    return cached_entry


def _select_gaussian_tensors(gaussian_model, mask):
    xyz_full = gaussian_model.get_xyz
    features_dc_full = gaussian_model._features_dc
    features_rest_full = gaussian_model._features_rest
    opacity_full = gaussian_model._opacity
    scaling_full = gaussian_model._scaling
    rotation_full = gaussian_model._rotation
    normal_full = gaussian_model._normal if hasattr(gaussian_model, "_normal") else None

    if mask is None:
        return (
            xyz_full,
            features_dc_full,
            features_rest_full,
            opacity_full,
            scaling_full,
            rotation_full,
            normal_full,
        )

    normal = normal_full[mask] if normal_full is not None else None
    return (
        xyz_full[mask],
        features_dc_full[mask],
        features_rest_full[mask],
        opacity_full[mask],
        scaling_full[mask],
        rotation_full[mask],
        normal,
    )


def _make_object_gaussians(gaussian_model, mask):
    xyz, features_dc, features_rest, opacity, scaling, rotation, normal = (
        _select_gaussian_tensors(gaussian_model, mask)
    )
    return {
        "xyz": xyz,
        "features_dc": features_dc,
        "features_rest": features_rest,
        "opacity": opacity,
        "scaling": scaling,
        "rotation": rotation,
        "normal": normal,
        "max_sh_degree": gaussian_model.max_sh_degree,
    }


def _env_file_cache_key(path, resize_to=None):
    stat = os.stat(path)
    resize_key = None if resize_to is None else tuple(int(v) for v in resize_to)
    return (os.path.abspath(path), stat.st_mtime_ns, stat.st_size, resize_key)


def _load_env_map_rgb(path):
    env = cv2.imread(path, cv2.IMREAD_ANYDEPTH | cv2.IMREAD_COLOR)
    if env is None:
        raise FileNotFoundError(f"Could not load environment map: {path}")
    return cv2.cvtColor(env, cv2.COLOR_BGR2RGB)


def _compute_env_sh_cached(
    relight_cache,
    env_path,
    directions,
    sqrt_weights,
    A_weighted,
    AT_A_weighted,
    device,
    resize_to=None,
):
    key = _env_file_cache_key(env_path, resize_to=resize_to)
    env_sh_cache = relight_cache.setdefault("env_sh", {})
    cached = env_sh_cache.get(key)
    if cached is not None:
        return cached

    env_map = _load_env_map_rgb(env_path)
    if resize_to is not None and env_map.shape[:2] != tuple(resize_to):
        env_map = cv2.resize(
            env_map,
            (int(resize_to[1]), int(resize_to[0])),
            interpolation=cv2.INTER_LINEAR,
        )

    env_map_gpu = torch.from_numpy(env_map.astype(np.float32)).to(device)
    sh_coeffs = compute_global_sh_coeffs(
        env_map_gpu, directions, sqrt_weights, A_weighted, AT_A_weighted
    )
    env_sh_cache[key] = (sh_coeffs, env_map.shape[:2])
    return env_sh_cache[key]


def _compute_offset_sh_cached(
    relight_cache,
    shape_hw,
    directions,
    sqrt_weights,
    A_weighted,
    AT_A_weighted,
    device,
):
    shape_key = tuple(int(v) for v in shape_hw)
    offset_cache = relight_cache.setdefault("offset_sh", {})
    cached = offset_cache.get(shape_key)
    if cached is not None:
        return cached

    offset_gpu = torch.full(
        (shape_key[0], shape_key[1], 3),
        0.5,
        dtype=torch.float32,
        device=device,
    )
    sh_offset = compute_global_sh_coeffs(
        offset_gpu, directions, sqrt_weights, A_weighted, AT_A_weighted
    )
    offset_cache[shape_key] = sh_offset
    return sh_offset


@torch.no_grad()
def precompute_visibility_cache(
    gaussian_model,
    mask: Optional[torch.BoolTensor] = None,
    num_samples=1200,
    visibility_res=VISIBILITY_RES,
):
    device = gaussian_model.get_xyz.device
    l_max = gaussian_model.max_sh_degree
    relight_cache = _ensure_relight_cache(
        gaussian_model, num_samples, l_max, visibility_res, device
    )
    mask_token = _mask_cache_token(mask)
    visibility_cache = relight_cache["visibility"]
    if mask_token in visibility_cache:
        return visibility_cache[mask_token]

    object_gaussians = _make_object_gaussians(gaussian_model, mask)
    print(
        f"[INFO] precomputing relight visibility for {object_gaussians['xyz'].shape[0]} gaussians "
        f"({num_samples} samples, {visibility_res}x{visibility_res})"
    )
    start_time = time.time()
    visibility_cache[mask_token] = phase_1_bake_visibility_sh(
        object_gaussians,
        relight_cache["directions"],
        relight_cache["A_weighted"],
        relight_cache["AT_A_weighted"],
        relight_cache["sqrt_weights"],
        device,
        res=visibility_res,
    )
    print(f"[INFO] relight visibility precompute completed in {time.time() - start_time:.2f}s")
    return visibility_cache[mask_token]


@torch.no_grad()
def phase_1_bake_visibility_sh(gaussians, directions, A_weighted, AT_A_weighted, sqrt_weights, device, res=512):
    """Bake per-Gaussian visibility into SH once, then reuse it for later relights."""
    try:
        from gaussian_renderer import render
    except ImportError:
        raise ImportError("Could not import 'render' from 'gaussian_renderer'. Run from 2DGS root.")

    xyz = gaussians["xyz"].detach()
    scene_center = xyz.mean(dim=0)
    scene_radius = torch.max(torch.norm(xyz - scene_center, dim=1)).item() * 1.8

    mock_gaussians = MockGaussianModel(gaussians)
    pipe = MockPipeline()
    bg_color = torch.zeros(3, dtype=torch.float32, device=device)
    visibility_color = torch.ones((xyz.shape[0], 3), dtype=torch.float32, device=device)
    max_scales, _ = torch.max(mock_gaussians.get_scaling.detach(), dim=1)
    per_gaussian_bias = max_scales * 3.0

    esm_alpha = 8.0 / scene_radius

    poisson_disk = torch.tensor([
        [-0.94201624, -0.39906216], [ 0.94558609, -0.76890725],
        [-0.09418410, -0.92938870], [ 0.34495938,  0.29387760],
        [-0.91588581,  0.45771432], [-0.81544232, -0.87912464],
        [-0.38277543,  0.27676845], [ 0.97484398,  0.75648379],
    ], device=device, dtype=torch.float32)
    filter_radius = 1.5

    N = xyz.shape[0]
    S = directions.shape[0]
    K = A_weighted.shape[1]
    AT_b = torch.zeros((K, N), dtype=torch.float32, device=device)

    fov_const = 2.0 * math.asin(1.0 / 5.0) * 1.2
    f_const = 1.0 / math.tan(fov_const / 2.0)
    half_res = (res - 1) * 0.5

    for i in range(S):
        dir_vec = directions[i].clone()
        # dir_vec[0] = -dir_vec[0]

        cam, W2C, _ = create_telephoto_camera(scene_center, dir_vec, scene_radius, res, res, device)

        with torch.no_grad():
            render_pkg = render(cam, mock_gaussians, pipe, bg_color, override_color=visibility_color)
            if "surf_depth" in render_pkg:
                depth_map = render_pkg["surf_depth"][0]
            elif "depth" in render_pkg:
                depth_map = render_pkg["depth"][0]
            else:
                raise ValueError("Rasterizer didn't return depth (expected 'surf_depth' or 'depth')")

        xyz_view = torch.matmul(xyz, W2C[:3, :3]) + W2C[3, :3]
        depth_gaussian = xyz_view[:, 2]

        ndc_x = (xyz_view[:, 0] * f_const) / depth_gaussian
        ndc_y = (xyz_view[:, 1] * f_const) / depth_gaussian
        base_u = (ndc_x + 1.0) * half_res + 0.5
        base_v = (ndc_y + 1.0) * half_res + 0.5

        pcf_vis = torch.zeros(N, device=device)
        for off in poisson_disk:
            u_idx = torch.clamp((base_u + off[0] * filter_radius).long(), 0, res - 1)
            v_idx = torch.clamp((base_v + off[1] * filter_radius).long(), 0, res - 1)
            sd = depth_map[v_idx, u_idx]
            valid = (sd > 0).float()
            penetration = (depth_gaussian - sd - per_gaussian_bias).clamp(min=0.0)
            esm_vis = torch.exp(-esm_alpha * penetration)
            pcf_vis += valid * esm_vis + (1.0 - valid)
        pcf_vis /= len(poisson_disk)

        v_s_weighted = pcf_vis * sqrt_weights[i]
        AT_b += torch.outer(A_weighted[i], v_s_weighted)

    return torch.linalg.solve(AT_A_weighted, AT_b).T

def evaluate_sh_bases_torch(directions, l_max, device):
    x, y, z = directions[:, 0], directions[:, 1], directions[:, 2]
    bases = [torch.full((directions.shape[0],), C0, device=device, dtype=directions.dtype)]
    if l_max > 0:
        bases.extend([-C1 * y, C1 * z, -C1 * x])
        if l_max > 1:
            xx, yy, zz, xy, yz, xz = x * x, y * y, z * z, x * y, y * z, x * z
            bases.extend([C2[0] * xy, C2[1] * yz, C2[2] * (2.0 * zz - xx - yy), C2[3] * xz, C2[4] * (xx - yy)])
            if l_max > 2:
                bases.extend([C3[0] * y * (3 * xx - yy), C3[1] * xy * z, C3[2] * y * (4 * zz - xx - yy), C3[3] * z * (2 * zz - 3 * xx - 3 * yy), C3[4] * x * (4 * zz - xx - yy), C3[5] * z * (xx - yy), C3[6] * x * (xx - 3 * yy)])
    return torch.stack(bases, dim=1)


def precompute_sh_sampling(num_samples, l_max, device):
    indices = torch.arange(num_samples, device=device, dtype=torch.float64)
    theta = torch.acos(1 - 2 * (indices + 0.5) / num_samples)
    phi = torch.pi * (1 + 5 ** 0.5) * indices

    directions = torch.stack([torch.sin(theta) * torch.cos(phi), torch.sin(theta) * torch.sin(phi), torch.cos(theta)], dim=1).float()

    weights = torch.sin(theta).float()
    sqrt_weights = torch.sqrt(weights)

    A = evaluate_sh_bases_torch(directions, l_max, device)
    A_weighted = A * sqrt_weights.unsqueeze(1)
    AT_A_weighted = A_weighted.T @ A_weighted
    AT_A = A.T @ A
    dw_factor = (4.0 * torch.pi) / weights.sum()
    solid_angle_weights = weights * dw_factor
    gaunt_tensor = torch.einsum('si,sj,sk,s->ijk', A, A, A, solid_angle_weights)

    return directions, sqrt_weights, A, A_weighted, AT_A_weighted, AT_A, gaunt_tensor


def sample_env_map_torch(env_map, directions):
    H, W = env_map.shape[:2]
    x, y, z = directions[:, 0], directions[:, 1], directions[:, 2]
    theta = torch.acos(z.clamp(-1, 1))
    phi = torch.where(torch.atan2(y, x) < 0, torch.atan2(y, x) + 2 * torch.pi, torch.atan2(y, x))
    u = (phi / (2 * torch.pi) * W).long() % W
    v = torch.clamp((theta / torch.pi * (H - 1)).long(), 0, H - 1)
    return env_map[v, u, :]

def compute_global_sh_coeffs(env_map, directions, sqrt_weights, A_weighted, AT_A_weighted):
    colors_weighted = sample_env_map_torch(env_map, directions) * sqrt_weights.view(-1, 1)
    return torch.linalg.solve(AT_A_weighted, A_weighted.T @ colors_weighted)

def srgb_to_linear_torch(c_srgb):
    return torch.where(c_srgb <= 0.04045, c_srgb / 12.92, torch.pow((c_srgb + 0.055) / 1.055, 2.4))

def linear_to_srgb_torch(c_linear):
    return torch.where(c_linear <= 0.0031308, c_linear * 12.92, 1.055 * torch.pow(c_linear.clamp(min=1e-10), 1.0 / 2.4) - 0.055)



@torch.no_grad()
def compute_brdf_attenuation_al(features_rest, L_source, l_max):
    """
    Computes A_l = ||B_lm|| / ||L_lm|| per band.
    This extracts an effective, approximate BRDF attenuation profile from the source lighting.
    Note: the stored GS coefficients entangle illumination and material, so A_l is a heuristic
    surrogate rather than an exact BRDF inversion.
    """
    N = features_rest.shape[0]
    A_l = torch.zeros(N, l_max, 3, device=features_rest.device)
    eps = 1e-5

    for l in range(1, l_max + 1):
        obj_start = l**2 - 1
        obj_end = (l + 1)**2 - 1
        E_obj = features_rest[:, obj_start:obj_end, :].norm(dim=1)

        l_start = l**2
        l_end = (l + 1)**2
        E_src = L_source[l_start:l_end, :].norm(dim=0).unsqueeze(0)

        A_l[:, l - 1, :] = E_obj / (E_src + eps)

    return A_l


@torch.no_grad()
def apply_al_specular_transfer_gpu(A_l, normals, sh_offset, A, AT_A_inv, directions, L_shad_target, l_max, device, batch_size=5000):
    """
    Evaluates target lighting at reflected directions and applies the data-driven BRDF attenuation A_l.
    """
    N = normals.shape[0]
    num_coeffs = (l_max + 1) ** 2
    adjusted_rest = torch.zeros(N, num_coeffs - 1, 3, device=device, dtype=torch.float32)
    M = torch.matmul(AT_A_inv, A.T)

    for start in range(0, N, batch_size):
        end = min(start + batch_size, N)
        B = end - start
        n_batch = normals[start:end]
        L_tgt_batch = L_shad_target[start:end]

        n_dot_d = torch.matmul(n_batch, directions.T)
        omega_r = directions.unsqueeze(0) - 2.0 * n_dot_d.unsqueeze(-1) * n_batch.unsqueeze(1)
        omega_r_sh = omega_r.clone()
        # omega_r_sh[..., 0] = -omega_r_sh[..., 0]

        Y_L = evaluate_sh_bases_torch(omega_r_sh.reshape(-1, 3), l_max, device).reshape(
            B, directions.shape[0], num_coeffs
        )
        L_tgt_eval = torch.bmm(Y_L, L_tgt_batch).clamp(min=0.0)

        L_tgt_srgb = linear_to_srgb_torch(L_tgt_eval)
        L_prime = torch.matmul(M.unsqueeze(0), L_tgt_srgb) - sh_offset

        for l in range(1, l_max + 1):
            adjusted_rest[start:end, l**2 - 1:(l + 1)**2 - 1, :] = (
                L_prime[:, l**2:(l + 1)**2, :] * A_l[start:end, l - 1, :].unsqueeze(1)
            )

    return adjusted_rest


@torch.no_grad()
def phase_2_decoupled_relight(object_gaussians, all_normals, V_lm, L_lm_source, L_lm_target,
                              sh_coeffs_offset, A, AT_A_inv, gaunt_tensor, directions,
                              l_max, device, floor_alpha=0.05, tau_max=3.0):
    """
    Performs real-time relighting utilizing decoupled Diffuse and Specular paths.
    - Diffuse (DC): Modulated via Gaunt Tensor for self-shadows.
    - Specular (Rest): SH convolution using a data-driven BRDF attenuation profile.
    """
    features_dc = object_gaussians['features_dc']
    features_rest = object_gaussians['features_rest']

    L_shad_source = torch.einsum('ijk,ic,nj->nkc', gaunt_tensor, L_lm_source, V_lm)
    L_shad_target = torch.einsum('ijk,ic,nj->nkc', gaunt_tensor, L_lm_target, V_lm)

    A_l_diff = torch.tensor([
        np.pi, 2 * np.pi / 3, 2 * np.pi / 3, 2 * np.pi / 3,
        np.pi / 4, np.pi / 4, np.pi / 4, np.pi / 4, np.pi / 4,
        0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
    ], device=device, dtype=torch.float32)

    normals_for_sh = all_normals.clone()
    # normals_for_sh[:, 0] = -normals_for_sh[:, 0]

    Y_hat = evaluate_sh_bases_torch(normals_for_sh, l_max, device) * A_l_diff.view(1, -1)
    E_source_clean = torch.clamp(torch.einsum('nk,nkc->nc', Y_hat, L_shad_source), min=0.0)
    E_target_clean = torch.clamp(torch.einsum('nk,nkc->nc', Y_hat, L_shad_target), min=0.0)

    E_unocc = torch.clamp(torch.einsum('nk,kc->nc', Y_hat, L_lm_source), min=0.0)
    floor = floor_alpha * E_unocc + 1e-5
    tau_diffuse = torch.clamp(E_target_clean / (E_source_clean + floor), min=0.0, max=tau_max)

    dc_vals = features_dc[:, 0, :]
    dc_srgb = (C0 * dc_vals + 0.5).clamp(min=0.0)
    dc_linear = srgb_to_linear_torch(dc_srgb)
    dc_new_linear = (dc_linear * tau_diffuse).clamp(min=0.0)
    dc_new_srgb = linear_to_srgb_torch(dc_new_linear)
    new_features_dc = ((dc_new_srgb - 0.5) / C0).unsqueeze(1)

    A_l_spec = compute_brdf_attenuation_al(features_rest, L_lm_source, l_max)

    rest_reflect = apply_al_specular_transfer_gpu(
        A_l=A_l_spec,
        normals=all_normals,
        sh_offset=sh_coeffs_offset,
        A=A,
        AT_A_inv=AT_A_inv,
        directions=directions,
        L_shad_target=L_shad_target,
        l_max=l_max,
        device=device,
    )

    object_gaussians['features_dc'] = new_features_dc
    object_gaussians['features_rest'] = rest_reflect

def rotate_normals_torch(normals, rotation_matrix, device):
    return (torch.from_numpy(rotation_matrix).float().to(device) @ normals.T).T

def rotate_env_map(env_map, rotation_matrix):
    H, W, _ = env_map.shape
    u_coords = np.linspace(0, W, W, endpoint=False)
    v_coords = np.linspace(0, H, H, endpoint=False)
    u_grid, v_grid = np.meshgrid(u_coords, v_coords)
    
    phi = (u_grid / W) * 2 * np.pi
    theta = (v_grid / H) * np.pi
    
    x = np.sin(theta) * np.cos(phi)
    y = np.sin(theta) * np.sin(phi)
    z = np.cos(theta)
    coords = np.stack([x, y, z], axis=-1)
    
    rotated_coords = (rotation_matrix.T @ coords.reshape(-1, 3).T).T.reshape(H, W, 3)
    rx = rotated_coords[..., 0]
    ry = rotated_coords[..., 1]
    rz = rotated_coords[..., 2]
    
    theta_rot = np.arccos(np.clip(rz, -1.0, 1.0))
    phi_rot = np.arctan2(ry, rx)
    phi_rot = np.where(phi_rot < 0, phi_rot + 2 * np.pi, phi_rot)
    
    u_rot = (phi_rot / (2 * np.pi) * W) % W
    v_rot = (theta_rot / np.pi * H)
    
    u_map = u_rot.astype(np.float32)
    v_map = np.clip(v_rot.astype(np.float32), 0, H - 1)
    
    return cv2.remap(env_map, u_map, v_map, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP)

def relight_gaussian_model(gaussian_model,
                            env_map_target_path,
                            env_map_source_path=None,
                            num_samples=1200,
                            visibility_res=VISIBILITY_RES,
                            rotation_matrix=np.eye(3),
                            mask: Optional[torch.BoolTensor] = None):
    """Modify ``gaussian_model`` so that its SH features are relit.

    Parameters
    ----------
    gaussian_model : scene.gaussian_model.GaussianModel
        model whose ``_features_dc``/``_features_rest`` are updated in-place.
    env_map_target_path : str
        path to target HDR environment map.
    env_map_source_path : str or None
        source HDR env map; if ``None`` the target env map is used.
    num_samples : int
        number of directions used for SH sampling.
    rotation_matrix : array-like or None
        optional 3x3 rotation applied to normals and env maps.
    mask : BoolTensor or None
        if provided, only the masked Gaussians are relit.
    """
    device = gaussian_model.get_xyz.device
    if not env_map_target_path:
        raise ValueError("env_map_target_path is required")
    if env_map_source_path is None:
        env_map_source_path = env_map_target_path

    # gather gaussian tensors
    xyz_full          = gaussian_model.get_xyz
    features_dc_full  = gaussian_model._features_dc
    features_rest_full = gaussian_model._features_rest
    l_max             = gaussian_model.max_sh_degree

    relight_cache = _ensure_relight_cache(
        gaussian_model, num_samples, l_max, visibility_res, device
    )

    xyz, features_dc, features_rest, opacity, scaling, rotation, normal = (
        _select_gaussian_tensors(gaussian_model, mask)
    )

    mask_token = _mask_cache_token(mask)

    with torch.no_grad():
        if normal is None or torch.all(normal == 0):
            normal = quaternion2rotmat(F.normalize(rotation, dim=1))[..., 2]

        all_normals = normal.clone()
        all_normals = all_normals / all_normals.norm(dim=1, keepdim=True)

        directions = relight_cache["directions"]
        sqrt_weights = relight_cache["sqrt_weights"]
        A = relight_cache["A"]
        A_weighted = relight_cache["A_weighted"]
        AT_A_weighted = relight_cache["AT_A_weighted"]
        gaunt_tensor = relight_cache["gaunt_tensor"]
        AT_A_inv = relight_cache["AT_A_inv"]

        sh_coeffs_source_global, source_shape = _compute_env_sh_cached(
            relight_cache,
            env_map_source_path,
            directions,
            sqrt_weights,
            A_weighted,
            AT_A_weighted,
            device,
        )

        env_map_target = _load_env_map_rgb(env_map_target_path)
        if env_map_target.shape[:2] != source_shape:
            env_map_target = cv2.resize(
                env_map_target,
                (int(source_shape[1]), int(source_shape[0])),
                interpolation=cv2.INTER_LINEAR,
            )
        env_map_target = rotate_env_map(env_map_target, rotation_matrix.T)

        env_map_target_gpu = torch.from_numpy(env_map_target.astype(np.float32)).to(device)
        sh_coeffs_target_global = compute_global_sh_coeffs(
            env_map_target_gpu, directions, sqrt_weights, A_weighted, AT_A_weighted
        )
        sh_coeffs_offset = _compute_offset_sh_cached(
            relight_cache,
            env_map_target.shape[:2],
            directions,
            sqrt_weights,
            A_weighted,
            AT_A_weighted,
            device,
        )

        object_gaussians = {
            "xyz": xyz,
            "features_dc": features_dc,
            "features_rest": features_rest,
            "opacity": opacity,
            "scaling": scaling,
            "rotation": rotation,
            "normal": normal,
            "max_sh_degree": l_max,
        }
        
        visibility_cache = relight_cache["visibility"]
        if mask_token not in visibility_cache:
            precompute_visibility_cache(
                gaussian_model,
                mask=mask,
                num_samples=num_samples,
                visibility_res=visibility_res,
            )

        V_lm = visibility_cache[mask_token]

        phase_2_decoupled_relight(
            object_gaussians,
            all_normals,
            V_lm,
            sh_coeffs_source_global,
            sh_coeffs_target_global,
            sh_coeffs_offset,
            A,
            AT_A_inv,
            gaunt_tensor,
            directions,
            l_max,
            device,
        )


        adj_dc = object_gaussians["features_dc"]
        adj_rest = object_gaussians["features_rest"]

        # ================================================================== #
        # Write-back: update the model's SH features                          #
        # Use .clone() before indexed assignment to avoid in-place ops on     #
        # leaf nn.Parameter tensors (which raise a grad error).               #
        # ================================================================== #
        if mask is not None:
            full_dc = features_dc_full.detach().clone()
            full_dc[mask] = adj_dc
            full_rest = features_rest_full.detach().clone()
            full_rest[mask] = adj_rest
            gaussian_model._features_dc   = full_dc
            gaussian_model._features_rest = full_rest
        else:
            gaussian_model._features_dc   = adj_dc
            gaussian_model._features_rest = adj_rest

    return gaussian_model
