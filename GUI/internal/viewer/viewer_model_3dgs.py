import math
import torch
import numpy as np
from plyfile import PlyData
from torch import nn


class GaussianModel3DGS:
    """Lightweight 3DGS (3-scale) Gaussian model for background rendering.

    This is intentionally read-only — no editing, no relighting.
    Loaded from a standard 3DGS .ply file (scale_0/1/2 present).
    """

    def __init__(self):
        self.max_sh_degree = 0
        self.active_sh_degree = 0
        self._xyz = torch.empty(0)
        self._features_dc = torch.empty(0)
        self._features_rest = torch.empty(0)
        self._scaling = torch.empty(0)
        self._rotation = torch.empty(0)
        self._opacity = torch.empty(0)

    @property
    def get_xyz(self):
        return self._xyz

    @property
    def get_scaling(self):
        return torch.exp(self._scaling)

    @property
    def get_rotation(self):
        return torch.nn.functional.normalize(self._rotation, dim=-1)

    @property
    def get_opacity(self):
        return torch.sigmoid(self._opacity)

    @property
    def get_features(self):
        return torch.cat([self._features_dc, self._features_rest], dim=1)

    def load_ply(self, path: str):
        plydata = PlyData.read(path)
        el = plydata.elements[0]

        xyz = np.stack((
            np.asarray(el["x"]),
            np.asarray(el["y"]),
            np.asarray(el["z"]),
        ), axis=1)

        opacities = np.asarray(el["opacity"])[..., np.newaxis]

        features_dc = np.zeros((xyz.shape[0], 3, 1))
        features_dc[:, 0, 0] = np.asarray(el["f_dc_0"])
        features_dc[:, 1, 0] = np.asarray(el["f_dc_1"])
        features_dc[:, 2, 0] = np.asarray(el["f_dc_2"])

        extra_f_names = sorted(
            [p.name for p in el.properties if p.name.startswith("f_rest_")],
            key=lambda x: int(x.split('_')[-1])
        )
        features_extra = np.zeros((xyz.shape[0], len(extra_f_names)))
        for idx, attr_name in enumerate(extra_f_names):
            features_extra[:, idx] = np.asarray(el[attr_name])
        num_rest = len(extra_f_names) // 3
        max_sh = int(math.sqrt(num_rest + 1)) - 1
        self.max_sh_degree = max_sh
        self.active_sh_degree = max_sh
        features_extra = features_extra.reshape((xyz.shape[0], 3, (max_sh + 1) ** 2 - 1))

        scale_names = sorted(
            [p.name for p in el.properties if p.name.startswith("scale_")],
            key=lambda x: int(x.split('_')[-1])
        )
        scales = np.zeros((xyz.shape[0], len(scale_names)))
        for idx, attr_name in enumerate(scale_names):
            scales[:, idx] = np.asarray(el[attr_name])

        rot_names = sorted(
            [p.name for p in el.properties if p.name.startswith("rot")],
            key=lambda x: int(x.split('_')[-1])
        )
        rots = np.zeros((xyz.shape[0], len(rot_names)))
        for idx, attr_name in enumerate(rot_names):
            rots[:, idx] = np.asarray(el[attr_name])

        self._xyz = torch.tensor(xyz, dtype=torch.float, device="cuda")
        self._features_dc = torch.tensor(features_dc, dtype=torch.float, device="cuda").transpose(1, 2).contiguous()
        self._features_rest = torch.tensor(features_extra, dtype=torch.float, device="cuda").transpose(1, 2).contiguous()
        self._opacity = torch.tensor(opacities, dtype=torch.float, device="cuda")
        self._scaling = torch.tensor(scales, dtype=torch.float, device="cuda")
        self._rotation = torch.tensor(rots, dtype=torch.float, device="cuda")

        # Load PRT visibility coefficients (f_prt_0 ... f_prt_8) if present
        prt_names = sorted(
            [p.name for p in el.properties if p.name.startswith("f_prt_")],
            key=lambda x: int(x.split('_')[-1])
        )
        if len(prt_names) > 0:
            prt = np.zeros((xyz.shape[0], len(prt_names)), dtype=np.float32)
            for i, name in enumerate(prt_names):
                prt[:, i] = np.asarray(el[name])
            self._prt_visibility = torch.tensor(prt, dtype=torch.float, device="cuda")
        else:
            # Default: fully visible (DC band = 2*sqrt(pi), rest 0)
            import math as _math
            default_prt = torch.zeros((xyz.shape[0], 9), dtype=torch.float, device="cuda")
            default_prt[:, 0] = 2.0 * _math.sqrt(_math.pi)
            self._prt_visibility = default_prt

        n_scales = len(scale_names)
        assert n_scales == 3, (
            f"Expected 3 scale values for a 3DGS PLY, got {n_scales}. "
            "Use GaussianModelforViewer for 2DGS (2-scale) PLYs."
        )
        print(f"[3DGS] Loaded {xyz.shape[0]:,} Gaussians  SH degree={max_sh}  PRT bands={self._prt_visibility.shape[1]}")
