from aiohttp import web_urldispatcher
import torch
import numpy as np 

import internal.utils.gaussian_utils as gaussian_utils
from scene import GaussianModel
from plyfile import PlyData
from torch import nn


class GaussianModelforViewer(GaussianModel):
    def __init__(self, sh_degree : int):
        super().__init__(sh_degree)
        self._opacity_origin = None
        self.scaling_modifier = 1.
        self.depth_ratio = 0.

    def select(self, mask: torch.tensor):
        if self._opacity_origin is None:
            self._opacity_origin = torch.clone(self._opacity)  # make a backup
        else:
            self._opacity = torch.clone(self._opacity_origin)

        # self._opacity[mask] = 0. inplace error!
        new_opacity = self._opacity.clone()
        new_opacity[mask] = 0. 
        self._opacity = new_opacity

    def delete_gaussians(self, mask: torch.tensor):
        gaussians_to_be_preserved = torch.bitwise_not(mask).to(self._xyz.device)
        self._xyz = self._xyz[gaussians_to_be_preserved]
        self._scaling = self._scaling[gaussians_to_be_preserved]
        self._rotation = self._rotation[gaussians_to_be_preserved]

        if self._opacity_origin is not None:
            self._opacity = self._opacity_origin
            self._opacity_origin = None
        self._opacity = self._opacity[gaussians_to_be_preserved]

        self._features_dc = self._features_dc[gaussians_to_be_preserved]
        self._features_rest = self._features_rest[gaussians_to_be_preserved]
        self.backup()

    def backup(self):
        # large memory consumption
        # store *copies* of the current parameters so that later
        # assignments to ``_features_dc``/etc. (e.g. relighting) do not
        # invalidate the backup.

        self.org_xyz = self._xyz.clone()
        self.org_scaling = self._scaling.clone()
        self.org_rotation = self._rotation.clone()
        self.org_features_dc = self._features_dc.clone()
        self.org_features_rest = self._features_rest.clone()
        # Track latest UI transform for each model index.
        self._model_transform_states = {}

        if hasattr(self, "_model_ids") and self._model_ids is not None:
            self._model_ids = self._model_ids.to(self._xyz.device)
            model_ids = torch.unique(self._model_ids).tolist()
            self._model_centers = {}
            for mid in model_ids:
                m = self._model_ids == int(mid)
                if torch.any(m):
                    self._model_centers[int(mid)] = self.org_xyz[m].mean(dim=0)

    def _ensure_backup_and_states(self):
        if not hasattr(self, "org_xyz"):
            self.backup()
        if not hasattr(self, "_model_transform_states"):
            self._model_transform_states = {}

    def _identity_state_for_idx(self, idx: int):
        device = self.org_xyz.device
        dtype = self.org_xyz.dtype
        if hasattr(self, "_model_centers") and idx in self._model_centers:
            center = self._model_centers[idx]
        else:
            center = self.org_xyz.mean(dim=0)
        return {
            "scale": 1.0,
            "wxyz": torch.tensor([1.0, 0.0, 0.0, 0.0], device=device, dtype=dtype),
            "position": center,
        }

    def _iter_model_indices(self):
        if hasattr(self, "_model_ids") and self._model_ids is not None:
            return [int(i) for i in torch.unique(self._model_ids).tolist()]
        return [0]

    def _mask_for_idx(self, idx: int):
        if hasattr(self, "_model_ids") and self._model_ids is not None:
            return self._model_ids == idx
        return torch.ones(self.org_xyz.shape[0], dtype=torch.bool, device=self.org_xyz.device)

    def apply_all_model_transforms(self):
        self._ensure_backup_and_states()
        xyz_out = self.org_xyz.clone()
        scaling_out = self.org_scaling.clone()
        rotation_out = self.org_rotation.clone()
        features_out = torch.cat((self.org_features_dc, self.org_features_rest), dim=1).clone()

        for idx in self._iter_model_indices():
            m = self._mask_for_idx(idx)
            if not torch.any(m):
                continue

            state = self._model_transform_states.get(idx)
            if state is None:
                state = self._identity_state_for_idx(idx)

            center = self._model_centers[idx] if hasattr(self, "_model_centers") and idx in self._model_centers else self.org_xyz[m].mean(dim=0)

            xyz = self.org_xyz[m] - center[None, :]
            scales = self.org_scaling[m]
            rots = self.org_rotation[m]
            feats = torch.cat((self.org_features_dc[m], self.org_features_rest[m]), dim=1)

            factor = max(float(state["scale"]), 1e-6)
            scale_delta = float(np.log(factor))

            xyz = xyz * factor
            scales = scales + scale_delta
            xyz, rots, feats_rot = gaussian_utils.GaussianTransformUtils.rotate_by_wxyz_quaternions(
                xyz=xyz,
                rotations=rots,
                features=feats,
                quaternions=state["wxyz"],
            )
            xyz = xyz + state["position"][None, :]

            xyz_out[m] = xyz
            scaling_out[m] = scales
            rotation_out[m] = rots
            features_out[m] = feats_rot

        self._xyz = xyz_out
        self._scaling = scaling_out
        self._rotation = rotation_out
        self._features_dc = features_out[:, 0, None, :]
        self._features_rest = features_out[:, 1:]

    def transform_with_vectors(self,
                                idx: int,
                                scale: float,
                                r_wxyz: np.ndarray,
                                t_xyz: np.ndarray,):
        self._ensure_backup_and_states()
        device = self.org_xyz.device
        dtype = self.org_xyz.dtype
        self._model_transform_states[int(idx)] = {
            "scale": float(scale),
            "wxyz": torch.tensor(r_wxyz, device=device, dtype=dtype),
            "position": torch.tensor(t_xyz, device=device, dtype=dtype),
        }
        self.apply_all_model_transforms()

    def load_ply(self, plydata_or_path, normal_b=True):
        if isinstance(plydata_or_path, str):
            plydata = PlyData.read(plydata_or_path)
        else:
            plydata = plydata_or_path

        xyz = np.stack((np.asarray(plydata.elements[0]["x"]),
                        np.asarray(plydata.elements[0]["y"]),
                        np.asarray(plydata.elements[0]["z"])),  axis=1)
        if normal_b:
            normal = np.stack(
                (
                    np.asarray(plydata.elements[0]["nx"]),
                    np.asarray(plydata.elements[0]["ny"]),
                    np.asarray(plydata.elements[0]["nz"]),
                ),
                axis=1,
            )
        opacities = np.asarray(plydata.elements[0]["opacity"])[..., np.newaxis]

        features_dc = np.zeros((xyz.shape[0], 3, 1))
        features_dc[:, 0, 0] = np.asarray(plydata.elements[0]["f_dc_0"])
        features_dc[:, 1, 0] = np.asarray(plydata.elements[0]["f_dc_1"])
        features_dc[:, 2, 0] = np.asarray(plydata.elements[0]["f_dc_2"])

        extra_f_names = [p.name for p in plydata.elements[0].properties if p.name.startswith("f_rest_")]
        extra_f_names = sorted(extra_f_names, key = lambda x: int(x.split('_')[-1]))
        num_rest_features = len(extra_f_names) // 3
        import math
        max_sh_degree = int(math.sqrt(num_rest_features + 1)) - 1
        
        assert len(extra_f_names)==3*(max_sh_degree + 1) ** 2 - 3
        features_extra = np.zeros((xyz.shape[0], len(extra_f_names)))
        for idx, attr_name in enumerate(extra_f_names):
            features_extra[:, idx] = np.asarray(plydata.elements[0][attr_name])
        features_extra = features_extra.reshape((features_extra.shape[0], 3, (max_sh_degree + 1) ** 2 - 1))

        scale_names = [p.name for p in plydata.elements[0].properties if p.name.startswith("scale_")]
        scale_names = sorted(scale_names, key = lambda x: int(x.split('_')[-1]))
        scales = np.zeros((xyz.shape[0], len(scale_names)))
        for idx, attr_name in enumerate(scale_names):
            scales[:, idx] = np.asarray(plydata.elements[0][attr_name])

        rot_names = [p.name for p in plydata.elements[0].properties if p.name.startswith("rot")]
        rot_names = sorted(rot_names, key = lambda x: int(x.split('_')[-1]))
        rots = np.zeros((xyz.shape[0], len(rot_names)))
        for idx, attr_name in enumerate(rot_names):
            rots[:, idx] = np.asarray(plydata.elements[0][attr_name])

        self._xyz = nn.Parameter(torch.tensor(xyz, dtype=torch.float, device="cuda").requires_grad_(True))
        self._features_dc = nn.Parameter(torch.tensor(features_dc, dtype=torch.float, device="cuda").transpose(1, 2).contiguous().requires_grad_(True))
        self._features_rest = nn.Parameter(torch.tensor(features_extra, dtype=torch.float, device="cuda").transpose(1, 2).contiguous().requires_grad_(True))
        self._opacity = nn.Parameter(torch.tensor(opacities, dtype=torch.float, device="cuda").requires_grad_(True))
        self._scaling = nn.Parameter(torch.tensor(scales, dtype=torch.float, device="cuda").requires_grad_(True))
        self._rotation = nn.Parameter(torch.tensor(rots, dtype=torch.float, device="cuda").requires_grad_(True))
        if normal_b:
            self._normal = nn.Parameter(torch.tensor(normal, dtype=torch.float, device="cuda").requires_grad_(True))
        self.max_sh_degree = max_sh_degree

        # Load PRT visibility coefficients if present; default to fully lit
        prt_names = sorted(
            [p.name for p in plydata.elements[0].properties if p.name.startswith("f_prt_")],
            key=lambda x: int(x.split('_')[-1])
        )
        if len(prt_names) > 0:
            prt = np.zeros((xyz.shape[0], len(prt_names)), dtype=np.float32)
            for i, name in enumerate(prt_names):
                prt[:, i] = np.asarray(plydata.elements[0][name])
            self._prt_visibility = torch.tensor(prt, dtype=torch.float, device="cuda")
        else:
            import math as _math
            default_prt = torch.zeros((xyz.shape[0], 16), dtype=torch.float, device="cuda")
            # DC = sqrt(π): sky-hemisphere normalization — dot(prt_full, env_sh) = sqrt(π) * (1/sqrt(π)) = 1.
            default_prt[:, 0] = _math.sqrt(_math.pi)
            self._prt_visibility = default_prt
                