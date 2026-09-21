import os
import math
import time
import subprocess
import cv2
import numpy as np
from shutil import rmtree
import torch
from torch import nn

from internal.cameras.cameras import Cameras
from internal.utils.graphics_utils import fov2focal
from internal.viewer.viewer_model import GaussianModelforViewer
from internal.viewer.viewer_renderer import ViewerRenderer

_FACE_NAMES = ["Px", "Nx", "Py", "Ny", "Pz", "Nz"]
# Camera-to-world rotations with axes [right, down, forward] per cubemap face.

_FACE_ROTATIONS = {
    # Camera-to-world rotation matrices. Columns = [right, down, forward] in world space.
    # Convention: Y-down, Z-forward (OpenCV / COLMAP). right x down = forward.
    "Px": np.array([[ 0, 0,  1], [0, 1,  0], [-1, 0, 0]], dtype=np.float32),  # forward = +X
    "Nx": np.array([[ 0, 0, -1], [0, 1,  0], [ 1, 0, 0]], dtype=np.float32),  # forward = -X
    # Py/Ny: looking straight down/up — reference "down" axis follows world -Z / +Z
    "Py": np.array([[ 1, 0,  0], [0, 0,  1], [ 0,-1, 0]], dtype=np.float32),  # forward = +Y (down)
    "Ny": np.array([[ 1, 0,  0], [0, 0, -1], [ 0, 1, 0]], dtype=np.float32),  # forward = -Y (up)
    "Pz": np.array([[ 1, 0,  0], [0, 1,  0], [ 0, 0, 1]], dtype=np.float32),  # forward = +Z
    "Nz": np.array([[-1, 0,  0], [0, 1,  0], [ 0, 0,-1]], dtype=np.float32),  # forward = -Z
}


def _mask_from_ranges(model_ranges, idx, num_points, device):
    if idx < 0 or idx >= len(model_ranges):
        raise ValueError(f"Model index {idx} is out of range (0..{len(model_ranges) - 1}).")
    start, end = model_ranges[idx]
    if start < 0 or end > num_points or start >= end:
        raise ValueError(f"Invalid model range for index {idx}: {start}:{end}.")
    mask = torch.zeros(num_points, dtype=torch.bool, device=device)
    mask[start:end] = True
    return mask


def _subset_gaussians(gaussian_model, mask):
    gm = GaussianModelforViewer(sh_degree=gaussian_model.max_sh_degree)
    gm._xyz = nn.Parameter(gaussian_model._xyz[mask].detach().clone())
    gm._scaling = nn.Parameter(gaussian_model._scaling[mask].detach().clone())
    gm._rotation = nn.Parameter(gaussian_model._rotation[mask].detach().clone())
    gm._opacity = nn.Parameter(gaussian_model._opacity[mask].detach().clone())
    gm._features_dc = nn.Parameter(gaussian_model._features_dc[mask].detach().clone())
    gm._features_rest = nn.Parameter(gaussian_model._features_rest[mask].detach().clone())
    if hasattr(gaussian_model, "_normal"):
        gm._normal = nn.Parameter(gaussian_model._normal[mask].detach().clone())

    gm.max_sh_degree = gaussian_model.max_sh_degree
    gm.active_sh_degree = getattr(gaussian_model, "active_sh_degree", gm.max_sh_degree)
    return gm


def _wxyz_to_rotation_matrix(wxyz):
    wxyz = np.asarray(wxyz, dtype=np.float32)
    w, x, y, z = [float(v) for v in wxyz]
    return np.array(
        [
            [1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - z * w), 2.0 * (x * z + y * w)],
            [2.0 * (x * y + z * w), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - x * w)],
            [2.0 * (x * z - y * w), 2.0 * (y * z + x * w), 1.0 - 2.0 * (x * x + y * y)],
        ],
        dtype=np.float32,
    )


def _get_sampling_center_and_rotation(gaussian_model, object_mask, object_idx):
    """Return (center_world, object_rotation_3x3) for the object.

    The rotation is the 3x3 matrix that maps object-local axes to world axes.
    Face cameras will be pre-multiplied by this so that "Px" always means
    the object's local +X direction, not a fixed world direction.
    """
    object_points = gaussian_model.get_xyz[object_mask]
    object_center = object_points.mean(dim=0).detach().cpu().numpy()

    state = None
    if hasattr(gaussian_model, "_model_transform_states") and gaussian_model._model_transform_states is not None:
        state = gaussian_model._model_transform_states.get(int(object_idx))

    if state is None:
        return object_center, np.eye(3, dtype=np.float32)

    scale = max(float(state.get("scale", 1.0)), 1e-6)
    wxyz = state.get("wxyz")
    if hasattr(wxyz, "detach"):
        wxyz = wxyz.detach().cpu().numpy()
    else:
        wxyz = np.asarray(wxyz, dtype=np.float32)
    rotation = _wxyz_to_rotation_matrix(wxyz)  # object-local → world

    local_up = np.array([0.0, 0.0, 1.0], dtype=np.float32)
    world_up = rotation @ local_up
    world_up_norm = np.linalg.norm(world_up)
    if world_up_norm > 0.0:
        world_up = world_up / world_up_norm
    else:
        world_up = local_up

    # Keep sampling origin offset above the object as it scales/rotates.
    radius = float(torch.linalg.norm(object_points - object_points.mean(dim=0), dim=1).max().detach().cpu().item())
    radius = max(radius * scale, 1e-3)
    center = object_center + world_up * radius
    return center, rotation


def _make_camera(center, rotation, width, height, fov_rad, device):
    if hasattr(center, "detach"):
        center = center.detach().to(device, dtype=torch.float32)
    else:
        center = torch.as_tensor(center, device=device, dtype=torch.float32)
    c2w = torch.eye(4, device=device, dtype=torch.float32)
    c2w[:3, :3] = torch.tensor(rotation, device=device, dtype=torch.float32)
    c2w[:3, 3] = center
    w2c = torch.linalg.inv(c2w)
    R = w2c[:3, :3]
    T = w2c[:3, 3]

    fx = torch.tensor([fov2focal(fov_rad, width)], device=device, dtype=torch.float32)
    fy = torch.tensor([fov2focal(fov_rad, height)], device=device, dtype=torch.float32)
    cx = torch.tensor([width // 2], device=device, dtype=torch.int)
    cy = torch.tensor([height // 2], device=device, dtype=torch.int)
    width_t = torch.tensor([width], device=device, dtype=torch.int)
    height_t = torch.tensor([height], device=device, dtype=torch.int)

    cam = Cameras(
        R=R.unsqueeze(0),
        T=T.unsqueeze(0),
        fx=fx,
        fy=fy,
        cx=cx,
        cy=cy,
        width=width_t,
        height=height_t,
        appearance_id=torch.tensor([0], device=device, dtype=torch.int),
        normalized_appearance_id=torch.tensor([0
], device=device, dtype=torch.float32),
        distortion_params=None,
        camera_type=torch.tensor([0], device=device, dtype=torch.int),
    )[0]
    return cam.to_device(device)


def _render_face(renderer, center, rotation, size, fov_rad):
    device = renderer.background_color.device
    camera = _make_camera(center, rotation, size, size, fov_rad, device)
    with torch.no_grad():
        image = renderer.get_outputs(
            camera,
            env_bg_enabled=False,
            render_type="render",
            active_sh_degree=renderer.gaussian_model.max_sh_degree,
            scaling_modifier=1.0,
            sparsity=1,
            depth_ratio=0.0,
        )
    image = torch.clamp(image, 0.0, 1.0).permute(1, 2, 0).cpu().numpy()
    image = (image * 255.0).round().clip(0, 255).astype(np.uint8)
    return image[..., ::-1]


def render_cubemap(renderer, center, size=450, fov_rad=math.pi / 2,
                   object_rotation=None):
    """Render all 6 cubemap faces from *center*.

    Parameters
    ----------
    object_rotation : (3, 3) ndarray or None
        Rotation matrix mapping object-local axes to world axes.
        When provided, each face camera is pre-rotated so that face labels
        (Px, Ny, …) refer to the object's LOCAL coordinate frame rather than
        fixed world directions.  Rotating the object 90° will therefore
        produce a 90° rotation in the captured env map.
    """
    if object_rotation is None:
        object_rotation = np.eye(3, dtype=np.float32)

    faces = []
    for name in _FACE_NAMES:
        # Pre-multiply: face_cam_local -> world = object_rotation @ face_local_rot
        world_face_rot = object_rotation @ _FACE_ROTATIONS[name]
        faces.append(_render_face(renderer, center, world_face_rot, size, fov_rad))
    return faces

def cubemap_to_equirectangular(faces, width, height):
    faces_arr = np.stack(faces, axis=0)
    face_size = faces_arr.shape[1]

    u_vals = np.arange(width, dtype=np.float32) / width
    v_vals = np.arange(height, dtype=np.float32) / height
    phi, theta = np.meshgrid(u_vals * 2 * math.pi, v_vals * math.pi)

    dir_x = np.sin(theta) * np.cos(phi)
    dir_y = np.sin(theta) * np.sin(phi)
    dir_z = np.cos(theta)

    # Stack as [X, Y, Z] so that argmax axis 0/1/2 selects X/Y/Z dominant faces.
    direction = np.stack([dir_x, dir_y, dir_z], axis=-1)
    abs_dir = np.abs(direction)
    max_axis = np.argmax(abs_dir, axis=-1)

    u = np.zeros((height, width), dtype=np.float32)
    v = np.zeros((height, width), dtype=np.float32)
    face = np.zeros((height, width), dtype=np.int32)

    # --- X dominant: Px (face 0, dx>0) or Nx (face 1, dx<0) ---
    # Px: right=world-Z, down=world+Y, forward=world+X
    # Nx: right=world+Z, down=world+Y, forward=world-X
    # u = -dz/dx (projects along -Z cam axis), v = dy/|dx| (projects along +Y cam axis)
    mask = max_axis == 0
    dir_x0 = direction[..., 0]  # dx
    dir_y0 = direction[..., 1]  # dy
    dir_z0 = direction[..., 2]  # dz
    abs_x0 = abs_dir[..., 0]
    u[mask] = 0.5 * (-dir_z0[mask] / dir_x0[mask] + 1.0)
    v[mask] = 0.5 * ( dir_y0[mask] / abs_x0[mask] + 1.0)  # fixed: was -dir_y0
    face[mask] = np.where(dir_x0[mask] > 0, 0, 1)

    # --- Y dominant: Py (face 2, dy>0) or Ny (face 3, dy<0) ---
    # Py: right=world+X, down=world-Z, forward=world+Y
    # Ny: right=world+X, down=world+Z, forward=world-Y
    # u = dx/|dy|, v = -dz/|dy| for Py, v = +dz/|dy| for Ny
    mask = max_axis == 1
    dir_y1 = direction[..., 1]  # dy
    dir_x1 = direction[..., 0]  # dx
    dir_z1 = direction[..., 2]  # dz
    abs_y1 = abs_dir[..., 1]
    u[mask] = 0.5 * ( dir_x1[mask] / abs_y1[mask] + 1.0)
    v_pos = 0.5 * (-dir_z1[mask] / abs_y1[mask] + 1.0)  # Py (dy>0): fixed sign
    v_neg = 0.5 * ( dir_z1[mask] / abs_y1[mask] + 1.0)  # Ny (dy<0): fixed sign
    pos = dir_y1[mask] > 0
    v[mask] = np.where(pos, v_pos, v_neg)
    face[mask] = np.where(pos, 2, 3)

    # --- Z dominant: Pz (face 4, dz>0) or Nz (face 5, dz<0) ---
    # Pz: right=world+X, down=world+Y, forward=world+Z
    # Nz: right=world-X, down=world+Y, forward=world-Z
    # u = dx/dz (sign-correct for both faces), v = dy/|dz|
    mask = max_axis == 2
    dir_z2 = direction[..., 2]  # dz
    dir_x2 = direction[..., 0]  # dx
    dir_y2 = direction[..., 1]  # dy
    abs_z2 = abs_dir[..., 2]
    u[mask] = 0.5 * (dir_x2[mask] / dir_z2[mask] + 1.0)
    v[mask] = 0.5 * (dir_y2[mask] / abs_z2[mask] + 1.0)  # fixed: was -dir_y2
    face[mask] = np.where(dir_z2[mask] > 0, 4, 5)

    x = np.clip((u * (face_size - 1)).astype(np.int32), 0, face_size - 1)
    y = np.clip((v * (face_size - 1)).astype(np.int32), 0, face_size - 1)

    sampled = faces_arr[face.reshape(-1), y.reshape(-1), x.reshape(-1)]
    return sampled.reshape(height, width, 3).astype(np.float32)

def equirectangular_to_polar(image_path, output_size=512):
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Could not load image from {image_path}")
        
    h_equi, w_equi = img.shape[:2]
    
    x = np.linspace(-1, 1, output_size)
    y = np.linspace(-1, 1, output_size)
    x_grid, y_grid = np.meshgrid(x, y)
    
    r = np.sqrt(x_grid**2 + y_grid**2)
    theta = np.arctan2(y_grid, x_grid)
    
    theta = np.where(theta < 0, theta + 2 * np.pi, theta)
    
    mask = r <= 1.0
    
    u = (theta / (2 * np.pi)) * (w_equi - 1)
    
    v = r * (h_equi - 1)
        
    map_x = u.astype(np.float32)
    map_y = v.astype(np.float32)
    
    polar_img = cv2.remap(img, map_x, map_y, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    
    polar_img[~mask] = 0
    out_path = os.path.join(os.path.dirname(image_path), "out_polar.png")
    cv2.imwrite(out_path, polar_img)
    return out_path

def generate_env_map(
    gaussian_model,
    model_ranges,
    background_color,
    output_dir,
    scene_idx=0,
    object_idx=1,
    cubemap_size=450,
    pano_width=1024,
    pano_height=512,
):  
    if model_ranges is None or len(model_ranges) < 2:
        raise ValueError("Env map sampling requires at least two loaded models.")

    device = gaussian_model.get_xyz.device
    num_points = gaussian_model.get_xyz.shape[0]
    scene_mask = _mask_from_ranges(model_ranges, scene_idx, num_points, device)
    object_mask = _mask_from_ranges(model_ranges, object_idx, num_points, device)
    if not torch.any(scene_mask):
        raise ValueError("Scene model mask is empty.")
    if not torch.any(object_mask):
        raise ValueError("Object model mask is empty.")

    object_center, object_rotation = _get_sampling_center_and_rotation(
        gaussian_model, object_mask, object_idx
    )
    scene_model = _subset_gaussians(gaussian_model, scene_mask)

    if isinstance(background_color, torch.Tensor):
        bg_color = background_color.to(device)
    else:
        bg_color = torch.tensor(background_color, device=device, dtype=torch.float32)
    import stat
    def handle_remove_readonly(func, path, exc):
        try:
            os.chmod(path, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
            func(path)
        except Exception:
            pass

    renderer = ViewerRenderer(scene_model, bg_color)
    if os.path.exists(output_dir):
        try:
            os.chmod(output_dir, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
        except Exception:
            pass
        rmtree(output_dir, onerror=handle_remove_readonly)
    os.makedirs(output_dir, exist_ok=True)
    faces = render_cubemap(
        renderer,
        object_center,
        size=int(cubemap_size),
        fov_rad=math.pi / 2,
        object_rotation=object_rotation,
    )

    for name, face in zip(_FACE_NAMES, faces):
        cv2.imwrite(os.path.join(output_dir, f"{name}.png"), face)

    panorama = cubemap_to_equirectangular(
        faces, width=int(pano_width), height=int(pano_height)
    )
    panorama = np.clip(panorama, 0, 255).astype(np.uint8)
    out_pano_equirect_path = os.path.join(output_dir, "out_equirect.png")
    cv2.imwrite(out_pano_equirect_path, panorama)

    out_pano_polar_path = equirectangular_to_polar(out_pano_equirect_path, output_size=pano_width)
    return out_pano_polar_path
