# Gen by Cursor
"""
Interactive Viser viewer for 2D Gaussian Splatting (TranSplat).
Features:
  - Real-time 2DGS/3DGS rendering with fast OpenCV base64 encoding
  - Precomputed in-memory visibility cache for instant relighting (<0.1s)
  - Decoupled diffuse (Gaunt tensor) + specular (data-driven BRDF attenuation) relighting
  - Multi-model composition with auto-centering and rigid-body transforms
  - Local environment map capture (6 cube faces + GMNet inverse tone mapping)
  - Camera trajectory animation and WebRTC preview
"""

import os
import sys
import time
import json
import base64
import threading
from pathlib import Path
from typing import Tuple, Literal, List, Optional
from argparse import ArgumentParser
import warnings

import torch
import numpy as np
from PIL import Image
import viser
import viser.transforms as vtf

warnings.filterwarnings("ignore")

# Setup module search paths
GUI_DIR = Path(__file__).resolve().parent
REPO_ROOT = GUI_DIR.parent

if str(GUI_DIR) not in sys.path:
    sys.path.insert(0, str(GUI_DIR))
if str(GUI_DIR / "GMNet") not in sys.path:
    sys.path.insert(1, str(GUI_DIR / "GMNet"))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(2, str(REPO_ROOT))


def _install_fast_viser_image_encoder():
    try:
        import cv2
    except Exception as exc:
        print(f"[WARN] fast viewer image encoder unavailable: {exc}")
        return

    try:
        import importlib
        import pathlib
        import viser as viser_package
    except Exception as exc:
        print(f"[WARN] fast viewer image encoder unavailable: {exc}")
        return

    def _to_uint8_image(image: np.ndarray) -> np.ndarray:
        image = np.asarray(image)
        if image.dtype == np.uint8:
            return np.ascontiguousarray(image)
        if np.issubdtype(image.dtype, np.floating):
            image = np.clip(image, 0.0, 1.0) * 255.0
        else:
            image = np.clip(image, 0, 255)
        return np.ascontiguousarray(image.astype(np.uint8))

    def _encode_image_base64_fast(image, format, jpeg_quality=None):
        image = _to_uint8_image(image)
        if format == "jpeg":
            media_type = "image/jpeg"
            quality = 75 if jpeg_quality is None else int(jpeg_quality)
            image_rgb = image[..., :3]
            image_bgr = np.ascontiguousarray(image_rgb[..., ::-1])
            ok, encoded = cv2.imencode(
                ".jpg",
                image_bgr,
                [int(cv2.IMWRITE_JPEG_QUALITY), quality],
            )
        elif format == "png":
            media_type = "image/png"
            if image.ndim == 3 and image.shape[-1] == 3:
                image_cv = np.ascontiguousarray(image[..., ::-1])
            elif image.ndim == 3 and image.shape[-1] == 4:
                image_cv = cv2.cvtColor(image, cv2.COLOR_RGBA2BGRA)
            else:
                image_cv = image
            ok, encoded = cv2.imencode(".png", image_cv)
        else:
            raise ValueError(f"Unsupported image format: {format}")

        if not ok:
            raise RuntimeError(f"OpenCV failed to encode {format} image")
        return media_type, base64.b64encode(encoded).decode("ascii")

    patched = False
    viser_root = pathlib.Path(viser_package.__file__).parent
    for path in viser_root.rglob("*.py"):
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        if "_encode_image_base64" not in text:
            continue
        rel = path.relative_to(viser_root).with_suffix("")
        module_name = ".".join(("viser", *rel.parts))
        try:
            module = importlib.import_module(module_name)
        except Exception:
            continue
        if hasattr(module, "_encode_image_base64"):
            module._encode_image_base64 = _encode_image_base64_fast
            patched = True

    if not patched:
        return


_install_fast_viser_image_encoder()


from internal.viewer import ViewerRenderer, ClientThread
from internal.viewer import GaussianModelforViewer as GaussianModel
from internal.viewer.ui import TransformPanel, EditPanel, EnvMapPanel
from internal.utils import gaussian_utils, relight


class Viewer:
    def __init__(
        self,
        args,
        model_paths: List[str],
        model_transforms: List[List[float]] = None,
        source_path: str = "",
        host: str = "0.0.0.0",
        port: int = 8080,
        background_color: Tuple = (0.5, 0.5, 0.5),
        env_map_path: str = "",
        image_format: Literal["jpeg", "png"] = "jpeg",
        reorient: Literal["auto", "enable", "disable"] = "auto",
        sh_degree: int = 3,
        show_cameras: bool = True,
        cameras_json: str = None,
        up: list = None,
        default_camera_position: List = None,
        default_camera_look_at: List = None,
        crop_box_size: float = 16.0,
        auto_center: bool = False,
        relight_precompute: bool = True,
        relight_num_samples: int = 1200,
        relight_visibility_res: int = 1024,
        fast_preview: bool = False,
        fast_preview_host: str = None,
        fast_preview_port: int = None,
        fast_preview_max_res: int = 1024,
        fast_preview_fps: int = 60,
    ):
        self.render_type_name = {
            "RGB": "render",
            "Edge": "edge",
            "Alpha": "rend_alpha",
            "Normal": "rend_normal",
            "View-Normal": "view_normal",
            "Depth": "surf_depth",
            "Depth-Distort": "rend_dist",
            "Depth-to-Normal": "surf_normal",
            "Depth-to-Curvature": "curvature",
            "None": "render",
        }
        self.args = args

        self.model_paths = (
            model_paths if isinstance(model_paths, (list, tuple)) else [model_paths]
        )
        self.model_transforms = model_transforms or []
        while len(self.model_transforms) < len(self.model_paths):
            self.model_transforms.append(None)

        self.source_path = source_path
        base_path = self.model_paths[0] if len(self.model_paths) > 0 else ""
        self.cameras_json = (
            os.path.join(base_path, "cameras.json")
            if cameras_json is None
            else cameras_json
        )

        self.model_names = [os.path.basename(p) for p in self.model_paths]
        self.selected_model_idx = 0

        self.host = host
        self.port = port
        self.background_color = torch.tensor(
            background_color, dtype=torch.float32, device="cuda"
        )
        self.env_map_path = env_map_path
        self.image_format = image_format
        self.sh_degree = sh_degree

        self.show_cameras = show_cameras
        self.crop_box_size = crop_box_size
        self.auto_center = auto_center
        self.relight_precompute = relight_precompute
        self.relight_num_samples = relight_num_samples
        self.relight_visibility_res = relight_visibility_res
        self.fast_preview = fast_preview
        self.fast_preview_host = fast_preview_host or host
        self.fast_preview_port = fast_preview_port or (port + 1)
        self.fast_preview_max_res = fast_preview_max_res
        self.fast_preview_fps = fast_preview_fps
        self.fast_preview_server = None
        self.fast_preview_url = None

        self.device = torch.device("cuda")
        self.render_lock = threading.Lock()
        self.total_device_memory = (
            torch.cuda.get_device_properties(self.device).total_memory / 1024**2
        )

        self.up_direction = np.asarray([0.0, 0.0, 1.0])
        self.camera_center = np.asarray([0.0, 0.0, 0.0])
        self.default_camera_position = default_camera_position
        self.default_camera_look_at = default_camera_look_at

        # init model & scene
        self._init_models()
        self._precompute_initial_relight_visibility()
        self._init_scene_camera_transform(self.cameras_json, reorient, up)
        self._init_camera_poses(self.cameras_json)
        self.clients = {}

    def _init_models(self):
        combined = None
        self.model_ranges = []
        cursor = 0
        loaded_models = []

        for path, transform in zip(self.model_paths, self.model_transforms):
            if not os.path.exists(path):
                print(f"[Alert] there is no pointcloud in: {path}")
                raise FileNotFoundError
            print(f"[INFO] loading ply from: {path}")
            gm = GaussianModel(sh_degree=self.sh_degree)
            gm.load_ply(path)

            if transform is not None:
                mat = torch.tensor(
                    transform, dtype=torch.float32, device=gm._xyz.device
                ).reshape(4, 4)
                gm._xyz, gm._rotation = (
                    gaussian_utils.GaussianTransformUtils.rotate_by_matrix(
                        gm._xyz, gm._rotation, mat[:3, :3].to(gm._xyz.device)
                    )
                )
                gm._xyz = gaussian_utils.GaussianTransformUtils.translation(
                    gm._xyz, mat[0, 3].item(), mat[1, 3].item(), mat[2, 3].item()
                )
                print(f"[INFO] applied transform to model {path}")

            loaded_models.append(gm)

        if not loaded_models:
            raise RuntimeError("No gaussian models were loaded")

        if self.auto_center and len(loaded_models) > 1:
            target_gm = loaded_models[-1]
            target_center = target_gm._xyz.mean(dim=0)
            for i in range(len(loaded_models) - 1):
                if self.model_transforms[i] is None:
                    insert_gm = loaded_models[i]
                    insert_center = insert_gm._xyz.mean(dim=0)
                    t = target_center - insert_center
                    insert_gm._xyz = gaussian_utils.GaussianTransformUtils.translation(
                        insert_gm._xyz, t[0].item(), t[1].item(), t[2].item()
                    )
                    print(f"[INFO] Auto-centered {self.model_paths[i]} to {self.model_paths[-1]} with translation {t.detach().cpu().numpy()}")

        max_sh_degree = max(getattr(gm, "max_sh_degree", 0) for gm in loaded_models)
        target_rest_dim = (max_sh_degree + 1) ** 2 - 1
        max_scaling_dim = max(gm._scaling.shape[1] for gm in loaded_models)

        if max_scaling_dim not in (2, 3):
            raise ValueError(
                f"Unsupported gaussian scaling layout with {max_scaling_dim} dimensions; expected 2DGS (2) or 3DGS (3)."
            )

        for gm in loaded_models:
            if gm._features_rest.shape[1] != target_rest_dim:
                padded_rest = torch.zeros(
                    (gm._features_rest.shape[0], target_rest_dim, gm._features_rest.shape[2]),
                    dtype=gm._features_rest.dtype,
                    device=gm._features_rest.device,
                )
                if gm._features_rest.shape[1] > 0:
                    padded_rest[:, : gm._features_rest.shape[1], :] = gm._features_rest
                gm._features_rest = torch.nn.Parameter(
                    padded_rest, requires_grad=gm._features_rest.requires_grad
                )
            gm.max_sh_degree = max_sh_degree
            gm.active_sh_degree = max_sh_degree

            if gm._scaling.shape[1] != max_scaling_dim:
                if gm._scaling.shape[1] == 2 and max_scaling_dim == 3:
                    padded_scaling = torch.cat(
                        [
                            gm._scaling,
                            torch.minimum(gm._scaling[:, :1], gm._scaling[:, 1:2])
                            + torch.log(
                                torch.tensor(
                                    0.01,
                                    dtype=gm._scaling.dtype,
                                    device=gm._scaling.device,
                                )
                            ),
                        ],
                        dim=1,
                    )
                else:
                    raise ValueError(
                        f"Cannot merge gaussian models with incompatible scaling dimensions: "
                        f"{gm._scaling.shape[1]} -> {max_scaling_dim}."
                    )
                gm._scaling = torch.nn.Parameter(
                    padded_scaling, requires_grad=gm._scaling.requires_grad
                )

        for gm in loaded_models:
            n = gm._xyz.shape[0]
            self.model_ranges.append((cursor, cursor + n))
            cursor += n
            gm._model_ids = torch.full(
                (n,),
                len(self.model_ranges) - 1,
                dtype=torch.long,
                device=gm._xyz.device,
            )

            if combined is None:
                combined = gm
            else:
                combined._xyz = torch.cat([combined._xyz, gm._xyz], dim=0)
                combined._scaling = torch.cat([combined._scaling, gm._scaling], dim=0)
                combined._rotation = torch.cat(
                    [combined._rotation, gm._rotation], dim=0
                )
                combined._opacity = torch.cat([combined._opacity, gm._opacity], dim=0)
                combined._features_dc = torch.cat(
                    [combined._features_dc, gm._features_dc], dim=0
                )
                combined._features_rest = torch.cat(
                    [combined._features_rest, gm._features_rest], dim=0
                )
                combined._model_ids = torch.cat(
                    [combined._model_ids, gm._model_ids], dim=0
                )
                if hasattr(gm, "_normal"):
                    if not hasattr(combined, "_normal"):
                        combined._normal = gm._normal.clone()
                    else:
                        combined._normal = torch.cat(
                            [combined._normal, gm._normal], dim=0
                        )

        combined.max_sh_degree = max_sh_degree
        combined.active_sh_degree = max_sh_degree

        self.gaussian_model = combined
        print(
            f"[INFO] total number of points across all models: {self.gaussian_model._xyz.shape[0]}"
        )

        if len(self.model_ranges) > 1:
            counts = [end - start for start, end in self.model_ranges]
            self.selected_model_idx = int(np.argmin(counts))
            print(
                f"[INFO] default relight target model: {self.selected_model_idx} "
                f"({self.model_names[self.selected_model_idx]}, {counts[self.selected_model_idx]} points)"
            )

        self.viewer_renderer = ViewerRenderer(
            self.gaussian_model, self.background_color
        )

    def _precompute_initial_relight_visibility(self):
        if not self.relight_precompute:
            return

        mask = None
        if hasattr(self, "model_ranges") and len(self.model_ranges) > 1:
            mask = self.get_model_mask(getattr(self, "selected_model_idx", 0))

        try:
            relight.precompute_visibility_cache(
                self.gaussian_model,
                mask=mask,
                num_samples=self.relight_num_samples,
                visibility_res=self.relight_visibility_res,
            )
        except Exception as exc:
            print(f"[WARN] relight visibility precompute failed: {exc}")

    def get_model_mask(self, idx: int):
        """Return a boolean mask selecting points belonging to the *idx*‑th path."""
        if not hasattr(self, "model_ranges"):
            return None
        start, end = self.model_ranges[idx]
        mask = torch.zeros(
            self.gaussian_model._xyz.shape[0],
            dtype=torch.bool,
            device=self.gaussian_model._xyz.device,
        )
        mask[start:end] = True
        return mask

    def _init_scene_camera_transform(self, cameras_json_path, mode, up):
        transform = torch.eye(4, dtype=torch.float)
        self.camera_transform = transform
        if mode == "disable" or not os.path.exists(cameras_json_path):
            print(f"[INFO] No custom scene camera transform")
            return

        print(f"[INFO] Load cameras from: {cameras_json_path}")
        with open(cameras_json_path, "r") as f:
            cameras = json.load(f)
        up_vector = torch.zeros(3)
        for cam in cameras:
            up_vector += torch.tensor(cam["rotation"])[:3, 1]
        up_vector = -up_vector / torch.linalg.norm(up_vector)
        print(f"[INFO] up vector = {up_vector}")
        self.up_direction = up_vector.numpy()

        if up is not None:
            transform = torch.eye(4, dtype=torch.float)
            up_vector = torch.tensor(up)
            up_vector = -up_vector / torch.linalg.norm(up_vector)
            self.up_direction = up_vector.numpy()

        self.camera_transform = transform

    def _init_camera_poses(self, cameras_json_path):
        if not os.path.exists(cameras_json_path):
            return []
        with open(cameras_json_path, "r") as f:
            camera_poses = json.load(f)
        if camera_poses:
            self.camera_center = np.mean(
                np.asarray([i["position"] for i in camera_poses]), axis=0
            )
        self.camera_poses = camera_poses

    def get_gpu_memory_usage(self):
        total_memory = torch.cuda.memory_allocated() + torch.cuda.memory_reserved()
        return f"{total_memory / 1024 ** 2:.1f} / {self.total_device_memory:.1f} MB"

    def add_cameras_to_scene(self, viser_server):
        if len(self.camera_poses) == 0:
            return

        self.camera_handles = []
        camera_pose_transform = np.linalg.inv(self.camera_transform.cpu().numpy())
        for camera in self.camera_poses:
            name = camera["img_name"]
            c2w = np.eye(4)
            c2w[:3, :3] = np.asarray(camera["rotation"])
            c2w[:3, 3] = np.asarray(camera["position"])
            c2w[:3, 1:3] *= -1
            c2w = np.matmul(camera_pose_transform, c2w)

            R = vtf.SO3.from_matrix(c2w[:3, :3])
            R = R @ vtf.SO3.from_x_radians(np.pi)

            cx = camera["width"] // 2
            cy = camera["height"] // 2
            fx = camera["fx"]

            camera_handle = viser_server.add_camera_frustum(
                name="cameras/{}".format(name),
                fov=float(2 * np.arctan(cx / fx)),
                scale=0.05,
                aspect=float(cx / cy),
                wxyz=R.wxyz,
                position=c2w[:3, 3],
                color=(255, 255, 0),
            )

            @camera_handle.on_click
            def _(
                event: viser.SceneNodePointerEvent[viser.CameraFrustumHandle],
            ) -> None:
                with event.client.atomic():
                    event.client.camera.position = event.target.position
                    event.client.camera.wxyz = event.target.wxyz

            self.camera_handles.append(camera_handle)

        self.show_cameras_frustrum = viser_server.gui.add_button("Show Train Cameras")
        self.camera_visible = True

        @self.show_cameras_frustrum.on_click
        def toggle_camera_visibility(_):
            with viser_server.atomic():
                self.camera_visible = not self.camera_visible
                for i in self.camera_handles:
                    i.visible = self.camera_visible

    def start(self):
        server = viser.ViserServer(host=self.host, port=self.port)
        server.configure_theme(control_width="large")
        self._start_fast_preview_server()
        logo_image = self._load_gui_logo()
        if logo_image is not None:
            server.gui.add_image(logo_image)
        tabs = server.gui.add_tab_group()

        self._setup_general_features_folder(server, tabs)
        server.on_client_connect(self._handle_new_client)
        server.on_client_disconnect(self._handle_client_disconnect)

        while True:
            time.sleep(999)

    def _start_fast_preview_server(self):
        if not self.fast_preview:
            return
        try:
            from internal.viewer.webrtc_server import FastPreviewServer
        except Exception as exc:
            print(f"[WARN] WebRTC fast preview unavailable: {exc}")
            return

        try:
            self.fast_preview_server = FastPreviewServer(
                self,
                host=self.fast_preview_host,
                port=self.fast_preview_port,
                max_res=self.fast_preview_max_res,
                fps=self.fast_preview_fps,
            )
            self.fast_preview_server.start()
            self.fast_preview_url = self.fast_preview_server.display_url
        except Exception as exc:
            self.fast_preview_server = None
            self.fast_preview_url = None
            print(f"[WARN] failed to start WebRTC fast preview: {exc}")

    def _load_gui_logo(self, max_width: int = 320) -> Optional[np.ndarray]:
        logo_candidates = [
            REPO_ROOT / "assets" / "TranSplat Logo.png",
            REPO_ROOT / "assets" / "logo.png",
            GUI_DIR / "TranSplat Logo.png",
            GUI_DIR / "internal" / "viewer" / "TranSplat_Logo.png",
            Path("/home/rr150/2dgs/TranSplat Logo.png"),
        ]
        logo_path = None
        for p in logo_candidates:
            if p.exists():
                logo_path = str(p)
                break
        if not logo_path:
            return None

        try:
            with Image.open(logo_path) as image:
                image = image.convert("RGBA")
                alpha = image.split()[-1]
                bbox = alpha.getbbox()
                if bbox:
                    image = image.crop(bbox)
                image = image.convert("RGB")
                if image.width > max_width:
                    height = max(1, round(image.height * max_width / image.width))
                    resampling = getattr(Image, "Resampling", Image).LANCZOS
                    image = image.resize((max_width, height), resampling)
                return np.asarray(image)
        except Exception as e:
            print(f"[WARN] Could not load GUI logo: {e}")
            return None

    def _setup_general_features_folder(self, server: viser.ViserServer, tabs):
        gui = server.gui
        with gui.add_folder("Status", expand_by_default=False):
            self.gpu_mem = gui.add_text(
                "Memory Usage", initial_value=self.get_gpu_memory_usage()
            )
            self.fps = gui.add_text("fps", initial_value="0.0 frame/sec")
            self.frame_time = gui.add_text("Frame Time", initial_value="n/a")
            if self.fast_preview_url is not None:
                gui.add_markdown(
                    f"WebRTC preview: [{self.fast_preview_url}]({self.fast_preview_url})"
                )
        with gui.add_folder("Image Options", expand_by_default=False):
            self.max_res_when_static = gui.add_slider(
                "Max Res",
                min=128,
                max=3840,
                step=128,
                initial_value=1024,
            )
            self.max_res_when_static.on_update(self._handle_option_updated)
            self.max_res_when_moving = gui.add_slider(
                "(when Move)",
                min=128,
                max=1920,
                step=128,
                initial_value=1024,
            )
            self.jpeg_quality_when_static = gui.add_slider(
                "JPEG Quality",
                min=0,
                max=100,
                step=1,
                initial_value=80,
            )
            self.jpeg_quality_when_static.on_update(self._handle_option_updated)

            self.jpeg_quality_when_moving = gui.add_slider(
                "(when Move)",
                min=0,
                max=100,
                step=1,
                initial_value=60,
            )

            self.enable_env_background = gui.add_checkbox(
                "Use HDR Env Background",
                initial_value=bool(self.env_map_path),
            )
            @self.enable_env_background.on_update
            def _(_):
                self._handle_option_updated(_) if os.path.exists(self.env_map_path) else None   

            self.fast_preview_only = gui.add_checkbox(
                "Use WebRTC Preview",
                initial_value=self.fast_preview_url is not None,
            )

        self.edit_panel = EditPanel(
            server,
            self,
            only_relight=True,
        )

        with gui.add_folder("Transform", expand_by_default=False):
            self.transform_panel = TransformPanel(server, self)

        with gui.add_folder("Env Map", expand_by_default=True):
            self.envmap_panel = EnvMapPanel(server, self)

        if self.show_cameras:
            self.add_cameras_to_scene(server)

        go_to_scene_center = server.gui.add_button(
            "Go to scene center",
        )

        @go_to_scene_center.on_click
        def _(event: viser.GuiEvent) -> None:
            assert event.client is not None
            event.client.camera.position = self.camera_center + np.asarray(
                [2.5, 0.0, 0.0]
            )
            event.client.camera.look_at = self.camera_center

    def rerender_for_all_client(self):
        for client_id in self.clients:
            try:
                self.clients[client_id].state = "low"
                self.clients[client_id].render_trigger.set()
            except:
                pass

    def _handle_option_updated(self, _):
        return self.rerender_for_all_client()

    def _handle_new_client(self, client: viser.ClientHandle) -> None:
        client_thread = ClientThread(self, self.viewer_renderer, client)
        client_thread.start()
        self.clients[client.client_id] = client_thread

    def _handle_client_disconnect(self, client: viser.ClientHandle):
        try:
            self.clients[client.client_id].stop()
            del self.clients[client.client_id]
        except Exception as err:
            print(err)


# Gen by Cursor
def main():
    parser = ArgumentParser(description="TranSplat Interactive Viser Viewer")
    parser.add_argument(
        "model_paths", type=str, nargs="+", help="Path(s) to 2DGS .ply model(s)"
    )
    parser.add_argument(
        "--model-transform",
        "-t",
        type=float,
        nargs=16,
        action="append",
        help="Optional 4x4 row-major transform matrix for each model (16 floats). ``-t`` may be specified multiple times.",
    )
    parser.add_argument("--source_path", "-s", type=str, default="")
    parser.add_argument("--host", "-a", type=str, default="0.0.0.0")
    parser.add_argument("--port", "-p", type=int, default=8080)
    parser.add_argument(
        "--background_color",
        "-b",
        type=str,
        nargs="+",
        default=["gray"],
        help="e.g.: white, gray, black, [0 0 0], [0.5 0.5 0.5], [1 1 1]",
    )
    parser.add_argument(
        "--env_map_path",
        "--env-map",
        "--env-map-path",
        type=str,
        default="",
        help="Path to HDR environment map used for background/relight",
    )
    parser.add_argument(
        "--image_format", "--image-format", "-f", type=str, default="jpeg"
    )
    parser.add_argument(
        "--reorient",
        "-r",
        type=str,
        default="auto",
        help="whether reorient the scene, available values: auto, enable, disable",
    )
    parser.add_argument("--sh_degree", "--sh-degree", "--sh", type=int, default=3)
    parser.add_argument("--show_cameras", "--show-cameras", action="store_true")
    parser.add_argument("--cameras-json", "--cameras_json", type=str, default=None)
    parser.add_argument("--up", nargs=3, required=False, type=float, default=None)
    parser.add_argument(
        "--default_camera_position",
        "--dcp",
        nargs=3,
        required=False,
        type=float,
        default=None,
    )
    parser.add_argument(
        "--default_camera_look_at",
        "--dcla",
        nargs=3,
        required=False,
        type=float,
        default=None,
    )

    parser.add_argument("--crop_box_size", type=float, default=16.0)
    parser.add_argument("--auto_center", action="store_true", help="Automatically center insert objects to the target scene")
    parser.add_argument(
        "--no-relight-precompute",
        dest="relight_precompute",
        action="store_false",
        help="Skip startup relight visibility baking.",
    )
    parser.set_defaults(relight_precompute=True)
    parser.add_argument(
        "--relight-num-samples",
        type=int,
        default=1200,
        help="Number of SH sample directions for relight visibility/env projection.",
    )
    parser.add_argument(
        "--relight-visibility-res",
        type=int,
        default=1024,
        help="Resolution of shadow maps used by relight visibility baking.",
    )
    parser.add_argument(
        "--fast-preview",
        "--fast_preview",
        dest="fast_preview",
        action="store_true",
        help="Start an experimental WebRTC preview stream on a separate port.",
    )
    parser.add_argument(
        "--fast-preview-host",
        "--fast_preview_host",
        dest="fast_preview_host",
        type=str,
        default=None,
        help="Host for the WebRTC preview server. Defaults to the viewer host.",
    )
    parser.add_argument(
        "--fast-preview-port",
        "--fast_preview_port",
        dest="fast_preview_port",
        type=int,
        default=None,
        help="Port for the WebRTC preview server. Defaults to viewer port + 1.",
    )
    parser.add_argument(
        "--fast-preview-max-res",
        "--fast_preview_max_res",
        dest="fast_preview_max_res",
        type=int,
        default=1024,
        help="Max rendered image dimension for the WebRTC preview stream.",
    )
    parser.add_argument(
        "--fast-preview-fps",
        "--fast_preview_fps",
        dest="fast_preview_fps",
        type=int,
        default=60,
        help="Target WebRTC preview frame rate.",
    )
    parser.add_argument("--float32_matmul_precision", "--fp", type=str, default=None)
    args, unknown_args = parser.parse_known_args()

    args.model_transforms = getattr(args, "model_transform", None) or []
    while len(args.model_transforms) < len(args.model_paths):
        args.model_transforms.append(None)
    if len(args.model_transforms) > len(args.model_paths):
        args.model_transforms = args.model_transforms[: len(args.model_paths)]

    if args.float32_matmul_precision is not None:
        torch.set_float32_matmul_precision(args.float32_matmul_precision)
    del args.float32_matmul_precision

    if len(args.background_color) == 1 and isinstance(args.background_color[0], str):
        if args.background_color[0] == "white":
            args.background_color = [1.0, 1.0, 1.0]
        elif args.background_color[0] == "black":
            args.background_color = [0.0, 0.0, 0.0]
        else:
            args.background_color = [0.5, 0.5, 0.5]
    else:
        args.background_color = tuple([float(i) for i in args.background_color])

    viewer_init_args = {
        key: getattr(args, key)
        for key in vars(args)
        if key != "model_transform"
    }
    viewer = Viewer(args, **viewer_init_args)
    viewer.start()


if __name__ == "__main__":
    main()
