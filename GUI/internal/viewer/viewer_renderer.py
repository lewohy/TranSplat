import torch
import torch.nn.functional as F
import math
import matplotlib.pyplot as plt
import numpy as np
from diff_surfel_rasterization import GaussianRasterizationSettings, GaussianRasterizer
from scene.gaussian_model import GaussianModel
from utils.sh_utils import eval_sh
from utils.point_utils import depth_to_normal

try:
    from diff_gaussian_rasterization import (
        GaussianRasterizationSettings as GaussianRasterizationSettings3D,
        GaussianRasterizer as GaussianRasterizer3D,
    )

    HAS_3DGS = True
except ImportError:
    HAS_3DGS = False


def gradient_map(image):
    sobel_x = (
        torch.tensor([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]])
        .float()
        .unsqueeze(0)
        .unsqueeze(0)
        .cuda()
        / 4
    )
    sobel_y = (
        torch.tensor([[-1, -2, -1], [0, 0, 0], [1, 2, 1]])
        .float()
        .unsqueeze(0)
        .unsqueeze(0)
        .cuda()
        / 4
    )

    grad_x = torch.cat(
        [
            F.conv2d(image[i].unsqueeze(0), sobel_x, padding=1)
            for i in range(image.shape[0])
        ]
    )
    grad_y = torch.cat(
        [
            F.conv2d(image[i].unsqueeze(0), sobel_y, padding=1)
            for i in range(image.shape[0])
        ]
    )

    # gradient magnitude
    magnitude = torch.sqrt(grad_x**2 + grad_y**2).norm(dim=0, keepdim=True)
    return magnitude


class ViewerRenderer:
    def __init__(self, gaussian_model, background_color):
        super().__init__()
        self.gaussian_model = gaussian_model
        self.background_color = background_color
        self.clm_colors = torch.tensor(plt.cm.get_cmap("turbo").colors, device="cuda")
        self._cached_env_path = None
        self._cached_env_tensor = None
        self.update_pc_features()

    def _load_env_map(self, env_map_path: str):
        if not env_map_path:
            return None
        if (
            self._cached_env_path == env_map_path
            and self._cached_env_tensor is not None
        ):
            return self._cached_env_tensor
        try:
            import cv2
        except ImportError:
            return None

        env = cv2.imread(env_map_path, cv2.IMREAD_ANYDEPTH | cv2.IMREAD_COLOR)
        if env is None:
            return None
        env = cv2.cvtColor(env, cv2.COLOR_BGR2RGB).astype(np.float32)
        env_t = torch.from_numpy(env).to(self.background_color.device)
        self._cached_env_path = env_map_path
        self._cached_env_tensor = env_t
        return env_t

    def _sample_env_equirect(
        self, env_map: torch.Tensor, directions: torch.Tensor
    ) -> torch.Tensor:
        h, w = env_map.shape[:2]
        x, y, z = directions[:, :, 0], directions[:, :, 1], directions[:, :, 2]
        theta = torch.acos(z.clamp(-1, 1))
        phi = torch.atan2(y, x)
        phi = torch.where(phi < 0, phi + 2 * torch.pi, phi)
        u = (phi / (2 * torch.pi) * w).long() % w
        v = torch.clamp((theta / torch.pi * (h - 1)).long(), 0, h - 1)
        return env_map[v, u, :]

    def _compose_env_background(
        self,
        rendered_image,
        render_alpha,
        viewpoint_camera,
        env_map_path: str,
    ):
        env_map = self._load_env_map(env_map_path)
        if env_map is None:
            return rendered_image

        h = int(viewpoint_camera.height)
        w = int(viewpoint_camera.width)
        tanfovx = math.tan(viewpoint_camera.fov_x * 0.5)
        tanfovy = math.tan(viewpoint_camera.fov_y * 0.5)

        xs = torch.linspace(-1.0, 1.0, w, device=rendered_image.device)
        ys = torch.linspace(-1.0, 1.0, h, device=rendered_image.device)
        yy, xx = torch.meshgrid(ys, xs)
        dirs_view = torch.stack(
            [xx * tanfovx, yy * tanfovy, torch.ones_like(xx)], dim=-1
        )
        dirs_view = F.normalize(dirs_view, dim=-1)

        dirs_world = torch.matmul(
            dirs_view, viewpoint_camera.world_view_transform[:3, :3].T
        )
        env = self._sample_env_equirect(env_map, dirs_world)

        # simple HDR tonemapping for display in the viewer
        env = 1.0 - torch.exp(-env * 1.0)
        env = env.permute(2, 0, 1)

        # rendered_image currently includes constant bg; replace it with env
        # using alpha: out = render + (env - const_bg) * (1 - alpha)
        alpha = render_alpha.clamp(0.0, 1.0)
        const_bg = self.background_color.view(3, 1, 1)
        composed = rendered_image + (env - const_bg) * (1.0 - alpha)
        return composed

    def update_pc_features(self):
        self.means3D = self.gaussian_model.get_xyz
        self.is_3dgs = self.gaussian_model.get_scaling.shape[1] == 3
        self.all_ids = torch.ones(
            self.means3D.shape[0], dtype=torch.bool, device=self.means3D.device
        )
        screenspace_points = (
            torch.zeros_like(
                self.means3D,
                dtype=self.means3D.dtype,
                requires_grad=True,
                device="cuda",
            )
            + 0
        )
        try:
            screenspace_points.retain_grad()
        except:
            pass
        self.means2D = screenspace_points
        self.opacity = self.gaussian_model.get_opacity
        self.scales = self.gaussian_model.get_scaling
        self.rotations = self.gaussian_model.get_rotation
        self.shs = self.gaussian_model.get_features

    def _select_gaussian_tensors(self, valid_range, sparsity: int):
        if valid_range is None:
            if sparsity == 1:
                return (
                    self.means3D,
                    self.means2D,
                    self.opacity,
                    self.scales,
                    self.rotations,
                    self.shs,
                )
            step = slice(None, None, sparsity)
            return (
                self.means3D[step],
                self.means2D[step],
                self.opacity[step],
                self.scales[step],
                self.rotations[step],
                self.shs[step],
            )

        is_x_in_range = (valid_range[0][0] <= self.means3D[:, 0]) & (
            self.means3D[:, 0] <= valid_range[0][1]
        )
        is_y_in_range = (valid_range[1][0] <= self.means3D[:, 1]) & (
            self.means3D[:, 1] <= valid_range[1][1]
        )
        is_z_in_range = (valid_range[2][0] <= self.means3D[:, 2]) & (
            self.means3D[:, 2] <= valid_range[2][1]
        )
        is_in_box = is_x_in_range & is_y_in_range & is_z_in_range
        return (
            self.means3D[is_in_box][::sparsity],
            self.means2D[is_in_box][::sparsity],
            self.opacity[is_in_box][::sparsity],
            self.scales[is_in_box][::sparsity],
            self.rotations[is_in_box][::sparsity],
            self.shs[is_in_box][::sparsity],
        )

    def _render_viewer_3dgs(
        self,
        viewpoint_camera,
        active_sh_degree,
        bg_color: torch.Tensor,
        env_map_path: str = "",
        valid_range=None,
        sparsity: int = 1,
        show_ptc: bool = False,
        show_disk: bool = False,
        point_size: float = 0.001,
    ):
        if not HAS_3DGS:
            raise ImportError(
                "diff_gaussian_rasterization is required for rendering 3DGS splats"
            )

        # 3DGS rendering uses volumetric rasterization; the surfel-only auxiliary
        # maps are not available in this mode.
        tanfovx = math.tan(viewpoint_camera.fov_x * 0.5)
        tanfovy = math.tan(viewpoint_camera.fov_y * 0.5)

        raster_settings = GaussianRasterizationSettings3D(
            image_height=int(viewpoint_camera.height),
            image_width=int(viewpoint_camera.width),
            tanfovx=tanfovx,
            tanfovy=tanfovy,
            bg=bg_color,
            scale_modifier=1.0,
            viewmatrix=viewpoint_camera.world_view_transform,
            projmatrix=viewpoint_camera.full_proj_transform,
            sh_degree=active_sh_degree,
            campos=viewpoint_camera.camera_center,
            prefiltered=False,
            debug=False,
            prt_visibility=torch.tensor([], device=bg_color.device),
            env_sh=torch.tensor([], device=bg_color.device),
        )
        rasterizer = GaussianRasterizer3D(raster_settings=raster_settings)

        means3D, _, opacity, scales, rotations, features = self._select_gaussian_tensors(
            valid_range, sparsity
        )

        means2D = torch.zeros_like(means3D, dtype=means3D.dtype, requires_grad=False, device=means3D.device)
        shs_view = features.transpose(1, 2).contiguous().view(-1, 3, features.shape[1])
        dir_pp = means3D - viewpoint_camera.camera_center.repeat(means3D.shape[0], 1)
        dir_pp_normalized = dir_pp / dir_pp.norm(dim=1, keepdim=True)
        sh2rgb = eval_sh(active_sh_degree, shs_view, dir_pp_normalized)
        colors_precomp = torch.clamp_min(sh2rgb + 0.5, 0.0)

        rendered_image, _ = rasterizer(
            means3D=means3D,
            means2D=means2D,
            shs=None,
            colors_precomp=colors_precomp,
            opacities=opacity,
            scales=scales,
            rotations=rotations,
            cov3D_precomp=None,
        )

        # Composite env map background when requested.  The 3DGS rasterizer
        # does not output alpha directly, so we derive it via a second render
        # with all-white override colors on a black background.  The output
        # of that render IS the alpha (since sum(1 * a_i * T_i) = 1 - T_final).
        if env_map_path:
            black_bg = torch.zeros(3, device=bg_color.device)
            white_colors = torch.ones_like(colors_precomp)
            alpha_settings = GaussianRasterizationSettings3D(
                image_height=int(viewpoint_camera.height),
                image_width=int(viewpoint_camera.width),
                tanfovx=tanfovx,
                tanfovy=tanfovy,
                bg=black_bg,
                scale_modifier=1.0,
                viewmatrix=viewpoint_camera.world_view_transform,
                projmatrix=viewpoint_camera.full_proj_transform,
                sh_degree=active_sh_degree,
                campos=viewpoint_camera.camera_center,
                prefiltered=False,
                debug=False,
                prt_visibility=torch.tensor([], device=bg_color.device),
                env_sh=torch.tensor([], device=bg_color.device),
            )
            alpha_rasterizer = GaussianRasterizer3D(alpha_settings)
            alpha_image, _ = alpha_rasterizer(
                means3D=means3D,
                means2D=torch.zeros_like(means3D, requires_grad=False),
                shs=None,
                colors_precomp=white_colors,
                opacities=opacity,
                scales=scales,
                rotations=rotations,
                cov3D_precomp=None,
            )
            # alpha_image is (3, H, W) with all channels equal; take one.
            render_alpha = alpha_image[:1]
            rendered_image = self._compose_env_background(
                rendered_image, render_alpha, viewpoint_camera, env_map_path
            )

        return {"render": rendered_image}

    def disk_kernel(self, opacity):
        return torch.exp(-1 / 2 * 100 * torch.clamp(opacity - 0.5, min=0) ** 2)

    def color_map(self, map):
        if not map.min() == map.max():
            map = (map - map.min()) / (map.max() - map.min())
            map = (map * 255).round().long().squeeze()
            map = self.clm_colors[map].permute(2, 0, 1)
            return map
        else:
            map = torch.zeros_like(map, device=map.device).round().long().squeeze()
            map = self.clm_colors[map].permute(2, 0, 1)
            return map

    def render_viewer(
        self,
        viewpoint_camera,
        active_sh_degree,
        scaling_modifier,
        depth_ratio,
        bg_color: torch.Tensor,
        env_map_path: str = "",
        sparsity: int = 1,
        show_ptc: bool = False,
        show_disk: bool = False,
        point_size: float = 0.001,
        valid_range=None,
    ):
        """
        Render the scene.
        Background tensor (bg_color) must be on GPU!
        """
        # Set up rasterization configuration
        if self.is_3dgs:
            return self._render_viewer_3dgs(
                viewpoint_camera,
                active_sh_degree,
                bg_color,
                env_map_path=env_map_path,
                valid_range=valid_range,
                sparsity=sparsity,
                show_ptc=show_ptc,
                show_disk=show_disk,
                point_size=point_size,
            )

        tanfovx = math.tan(viewpoint_camera.fov_x * 0.5)
        tanfovy = math.tan(viewpoint_camera.fov_y * 0.5)

        raster_settings = GaussianRasterizationSettings(
            image_height=int(viewpoint_camera.height),
            image_width=int(viewpoint_camera.width),
            tanfovx=tanfovx,
            tanfovy=tanfovy,
            bg=bg_color,
            scale_modifier=1.0,  # self.gaussian_model.scaling_modifier,
            viewmatrix=viewpoint_camera.world_view_transform,
            projmatrix=viewpoint_camera.full_proj_transform,
            sh_degree=active_sh_degree,  # self.gaussian_model.active_sh_degree,
            campos=viewpoint_camera.camera_center,
            prefiltered=False,
            debug=False,
        )
        rasterizer = GaussianRasterizer(raster_settings=raster_settings)

        means3D, means2D, opacity, scales, rotations, shs = self._select_gaussian_tensors(
            valid_range, sparsity
        )

        rendered_image, radii, allmap = rasterizer(
            means3D=means3D,
            means2D=means2D,
            shs=shs,
            colors_precomp=None,
            opacities=(
                self.disk_kernel(opacity)
                if show_disk
                else opacity
            ),
            scales=scaling_modifier
            * (
                torch.full_like(scales, point_size * 0.1)
                if show_ptc
                else scales
            ),
            rotations=rotations,
            cov3D_precomp=None,
        )

        # get normal map & transform normal from view space to world space
        render_alpha = allmap[1:2]
        if env_map_path:
            rendered_image = self._compose_env_background(
                rendered_image,
                render_alpha,
                viewpoint_camera,
                env_map_path,
            )
        render_normal = allmap[2:5]
        render_normal = (
            render_normal.permute(1, 2, 0)
            @ (viewpoint_camera.world_view_transform[:3, :3].T)
        ).permute(2, 0, 1)

        # get median depth map
        render_depth_median = allmap[5:6]
        render_depth_median = torch.nan_to_num(render_depth_median, 0, 0)
        # get expected depth map
        render_depth_expected = allmap[0:1]
        render_depth_expected = render_depth_expected / render_alpha
        render_depth_expected = torch.nan_to_num(render_depth_expected, 0, 0)

        # get depth distortion map & depth map & depth-to-normal map
        render_dist = allmap[6:7]
        surf_depth = (
            render_depth_expected * (1 - depth_ratio)
            + (depth_ratio) * render_depth_median
        )
        surf_normal = depth_to_normal(viewpoint_camera, surf_depth)
        surf_normal = surf_normal.permute(2, 0, 1)
        surf_normal = surf_normal * (render_alpha).detach()

        # fix normal truncation
        render_normal = torch.nn.functional.normalize(render_normal, dim=0) * 0.5 + 0.5
        surf_normal = surf_normal * 0.5 + 0.5
        view_normal = -torch.nn.functional.normalize(allmap[2:5], dim=0) * 0.5 + 0.5

        rets = {
            "render": rendered_image,
            "rend_alpha": self.color_map(
                render_alpha.unsqueeze(dim=-1)
            ),  # render_alpha.repeat(3, 1, 1),
            "rend_normal": render_normal,
            "view_normal": view_normal,
            "surf_depth": self.color_map(surf_depth.unsqueeze(dim=-1)),
            "surf_normal": surf_normal,
            "rend_dist": self.color_map(render_dist.unsqueeze(dim=-1)),
        }
        return rets

    def get_outputs(
        self,
        camera,
        valid_range: tuple = None,
        split: bool = False,
        slider: float = 0.5,
        env_bg_enabled: bool = False,
        env_bg_path: str = "",
        show_ptc: bool = False,
        show_disk: bool = False,
        point_size: float = 0.01,
        active_sh_degree: int = 3,
        scaling_modifier: float = 1.0,
        sparsity: int = 1,
        depth_ratio: float = 0.0,
        render_type: str = "render",
        render_type1: str = "render",
        render_type2: str = "render",
    ):
        def get_result(results, type):
            if type in results.keys():
                return results[type]
            elif type == "curvature":
                return self.color_map(gradient_map(results["surf_normal"]))
            elif type == "edge":
                return self.color_map(gradient_map(results["render"]))
            else:
                # handle exception as RGB render
                return results["render"]

        results = self.render_viewer(
            camera,
            active_sh_degree,
            scaling_modifier,
            depth_ratio,
            self.background_color,
            env_map_path=(env_bg_path if env_bg_enabled else ""),
            sparsity=sparsity,
            valid_range=valid_range,
            show_ptc=show_ptc,
            show_disk=show_disk,
            point_size=point_size,
        )
        if not split:
            return get_result(results, render_type)
        else:
            result = torch.zeros_like(results["render"])
            _, _, render_h = result.shape
            slider_pos = int(render_h * slider)
            result[:, :, :slider_pos] = get_result(results, render_type1)[
                :, :, :slider_pos
            ]
            result[:, :, slider_pos:] = get_result(results, render_type2)[
                :, :, slider_pos:
            ]
            result[:, :, slider_pos] = torch.ones_like(result[:, :, slider_pos])

            return result
