import os
import numpy as np
import torch
from internal.utils.colmap import rotmat2qvec, qvec2rotmat
from typing import Union
from dataclasses import dataclass
from plyfile import PlyData, PlyElement


@dataclass
class Gaussian:
    """
    Load parameters from ply or ckpt file;
    Convert between ply and ckpt;
    Save to ply or ckpt;
    """

    sh_degrees: int
    xyz: Union[np.ndarray, torch.Tensor]  # [n, 3]
    opacities: Union[np.ndarray, torch.Tensor]  # [n, 1]
    features_dc: Union[np.ndarray, torch.Tensor]  # ndarray[n, 3, 1], or tensor[n, 1, 3]
    features_rest: Union[np.ndarray, torch.Tensor]  # ndarray[n, 3, 15], or tensor[n, 15, 3]; NOTE: this is features_rest actually!
    scales: Union[np.ndarray, torch.Tensor]  # [n, 3]
    rotations: Union[np.ndarray, torch.Tensor]  # [n, 4]
    real_features_extra: Union[np.ndarray, torch.Tensor]

    @staticmethod
    def load_array_from_plyelement(plyelement, name_prefix: str):
        names = [p.name for p in plyelement.properties if p.name.startswith(name_prefix)]
        if len(names) == 0:
            print(f"WARNING: '{name_prefix}' not found in ply, create an empty one")
            return np.empty((plyelement["x"].shape[0], 0))
        names = sorted(names, key=lambda x: int(x.split('_')[-1]))
        v_list = []
        for idx, attr_name in enumerate(names):
            v_list.append(np.asarray(plyelement[attr_name]))

        return np.stack(v_list, axis=1)

    @classmethod
    def load_real_feature_extra_from_plyelement(cls, plyelement):
        return cls.load_array_from_plyelement(plyelement, "f_extra_")

    @classmethod
    def load_from_ply(cls, path: str, sh_degrees: int = -1):
        plydata = PlyData.read(path)

        xyz = np.stack((
            np.asarray(plydata.elements[0]["x"]),
            np.asarray(plydata.elements[0]["y"]),
            np.asarray(plydata.elements[0]["z"]),
        ), axis=1)
        opacities = np.asarray(plydata.elements[0]["opacity"])[..., np.newaxis]

        features_dc = np.zeros((xyz.shape[0], 3, 1))
        features_dc[:, 0, 0] = np.asarray(plydata.elements[0]["f_dc_0"])
        features_dc[:, 1, 0] = np.asarray(plydata.elements[0]["f_dc_1"])
        features_dc[:, 2, 0] = np.asarray(plydata.elements[0]["f_dc_2"])

        # extra_f_names = [p.name for p in plydata.elements[0].properties if p.name.startswith("f_rest_")]
        # extra_f_names = sorted(extra_f_names, key=lambda x: int(x.split('_')[-1]))
        # assert len(extra_f_names) == 3 * (sh_degrees + 1) ** 2 - 3  # TODO: remove such a assertion
        # features_extra = np.zeros((xyz.shape[0], len(extra_f_names)))
        # for idx, attr_name in enumerate(extra_f_names):
        #     features_extra[:, idx] = np.asarray(plydata.elements[0][attr_name])
        # # Reshape (P,F*SH_coeffs) to (P, F, SH_coeffs except DC)
        # features_rest = features_extra.reshape((features_extra.shape[0], 3, (sh_degrees + 1) ** 2 - 1))
        features_rest = cls.load_array_from_plyelement(plydata.elements[0], "f_rest_").reshape((xyz.shape[0], 3, -1))
        if sh_degrees >= 0:
            assert features_rest.shape[-1] == (sh_degrees + 1) ** 2 - 1  # TODO: remove such a assertion
        else:
            # auto determine sh_degrees
            features_rest_dims = features_rest.shape[-1]
            for i in range(4):
                if features_rest_dims == (i + 1) ** 2 - 1:
                    sh_degrees = i
                    break
            assert sh_degrees >= 0, f"invalid sh_degrees={sh_degrees}"

        # scale_names = [p.name for p in plydata.elements[0].properties if p.name.startswith("scale_")]
        # scale_names = sorted(scale_names, key=lambda x: int(x.split('_')[-1]))
        # scales = np.zeros((xyz.shape[0], len(scale_names)))
        # for idx, attr_name in enumerate(scale_names):
        #     scales[:, idx] = np.asarray(plydata.elements[0][attr_name])
        scales = cls.load_array_from_plyelement(plydata.elements[0], "scale_")

        # rot_names = [p.name for p in plydata.elements[0].properties if p.name.startswith("rot")]
        # rot_names = sorted(rot_names, key=lambda x: int(x.split('_')[-1]))
        # rots = np.zeros((xyz.shape[0], len(rot_names)))
        # for idx, attr_name in enumerate(rot_names):
        #     rots[:, idx] = np.asarray(plydata.elements[0][attr_name])
        rots = cls.load_array_from_plyelement(plydata.elements[0], "rot_")

        features_extra = cls.load_real_feature_extra_from_plyelement(plydata.elements[0])

        return cls(
            sh_degrees=sh_degrees,
            xyz=xyz,
            opacities=opacities,
            features_dc=features_dc,
            features_rest=features_rest,
            scales=scales,
            rotations=rots,
            real_features_extra=features_extra,
        )

    @classmethod
    def load_from_state_dict(cls, sh_degrees: int, state_dict: dict, key_prefix: str = "gaussian_model._"):
        init_args = {
            "sh_degrees": sh_degrees,
        }
        for name_in_dict, name_in_dataclass in [
            ("xyz", "xyz"),
            ("features_dc", "features_dc"),
            ("features_rest", "features_rest"),
            ("scaling", "scales"),
            ("rotation", "rotations"),
            ("opacity", "opacities"),
        ]:
            init_args[name_in_dataclass] = state_dict["{}{}".format(key_prefix, name_in_dict)]

        # compat with previous versions
        if f"{key_prefix}features_extra" in state_dict:
            init_args["real_features_extra"] = state_dict[f"{key_prefix}features_extra"]
        else:
            print("'features_extra' not found in state_dict, create an empty one")
            init_args["real_features_extra"] = torch.empty((init_args["xyz"].shape[0], 0), device=init_args["xyz"].device)

        return cls(**init_args)

    def to_parameter_structure(self):
        assert isinstance(self.xyz, np.ndarray) is True
        return Gaussian(
            sh_degrees=self.sh_degrees,
            xyz=torch.tensor(self.xyz, dtype=torch.float),
            opacities=torch.tensor(self.opacities, dtype=torch.float),
            features_dc=torch.tensor(self.features_dc, dtype=torch.float).transpose(1, 2),
            features_rest=torch.tensor(self.features_rest, dtype=torch.float).transpose(1, 2),
            scales=torch.tensor(self.scales, dtype=torch.float),
            rotations=torch.tensor(self.rotations, dtype=torch.float),
            real_features_extra=torch.tensor(self.real_features_extra, dtype=torch.float),
        )

    def to_ply_format(self):
        assert isinstance(self.xyz, torch.Tensor) is True
        return self.__class__(
            sh_degrees=self.sh_degrees,
            xyz=self.xyz.cpu().numpy(),
            opacities=self.opacities.cpu().numpy(),
            features_dc=self.features_dc.transpose(1, 2).cpu().numpy(),
            features_rest=self.features_rest.transpose(1, 2).cpu().numpy(),
            scales=self.scales.cpu().numpy(),
            rotations=self.rotations.cpu().numpy(),
            real_features_extra=self.real_features_extra.cpu().numpy(),
        )

    def save_to_ply(self, path: str, with_colors: bool = False):
        assert isinstance(self.xyz, np.ndarray) is True

        gaussian = self

        os.makedirs(os.path.dirname(path), exist_ok=True)

        xyz = gaussian.xyz
        normals = np.zeros_like(xyz)
        f_dc = gaussian.features_dc.reshape((gaussian.features_dc.shape[0], -1))
        # TODO: change sh degree
        if gaussian.sh_degrees > 0:
            f_rest = gaussian.features_rest.reshape((gaussian.features_rest.shape[0], -1))
        else:
            f_rest = np.zeros((f_dc.shape[0], 0))
        opacities = gaussian.opacities
        scale = gaussian.scales
        rotation = gaussian.rotations
        # f_extra = gaussian.real_features_extra

        def construct_list_of_attributes():
            l = ['x', 'y', 'z', 'nx', 'ny', 'nz']
            # All channels except the 3 DC
            for i in range(gaussian.features_dc.shape[1] * gaussian.features_dc.shape[2]):
                l.append('f_dc_{}'.format(i))
            if gaussian.sh_degrees > 0:
                for i in range(gaussian.features_rest.shape[1] * gaussian.features_rest.shape[2]):
                    l.append('f_rest_{}'.format(i))
            l.append('opacity')
            for i in range(gaussian.scales.shape[1]):
                l.append('scale_{}'.format(i))
            for i in range(gaussian.rotations.shape[1]):
                l.append('rot_{}'.format(i))
            # for i in range(self.real_features_extra.shape[1]):
            #     l.append('f_extra_{}'.format(i))
            return l

        dtype_full = [(attribute, 'f4') for attribute in construct_list_of_attributes()]
        attribute_list = [xyz, normals, f_dc, f_rest, opacities, scale, rotation]
        if with_colors is True:
            from internal.utils.sh_utils import eval_sh
            rgbs = np.clip((eval_sh(0, self.features_dc, None) + 0.5), 0., 1.)
            rgbs = (rgbs * 255).astype(np.uint8)

            dtype_full += [('red', 'u1'), ('green', 'u1'), ('blue', 'u1')]
            attribute_list.append(rgbs)

        elements = np.empty(xyz.shape[0], dtype=dtype_full)
        attributes = np.concatenate(attribute_list, axis=1)
        # do not save 'features_extra' for ply
        # attributes = np.concatenate((xyz, normals, f_dc, f_rest, opacities, scale, rotation, f_extra), axis=1)
        elements[:] = list(map(tuple, attributes))
        el = PlyElement.describe(elements, 'vertex')
        PlyData([el]).write(path)


class GaussianTransformUtils:
    _SH_C0 = 0.28209479177387814
    _SH_C1 = 0.4886025119029199
    _SH_C2 = [
        1.0925484305920792,
        -1.0925484305920792,
        0.31539156525252005,
        -1.0925484305920792,
        0.5462742152960396,
    ]
    _SH_C3 = [
        -0.5900435899266435,
        2.890611442640554,
        -0.4570457994644658,
        0.3731763325901154,
        -0.4570457994644658,
        1.445305721320277,
        -0.5900435899266435,
    ]
    _SH_C4 = [
        2.5033429417967046,
        -1.7701307697799304,
        0.9461746957575601,
        -0.6690465435572892,
        0.10578554691520431,
        -0.6690465435572892,
        0.47308734787878004,
        -1.7701307697799304,
        0.6258357354491761,
    ]

    @classmethod
    def _evaluate_sh_bases(cls, directions: torch.Tensor, degree: int) -> torch.Tensor:
        x, y, z = directions[:, 0], directions[:, 1], directions[:, 2]
        bases = [
            torch.full(
                (directions.shape[0],),
                cls._SH_C0,
                device=directions.device,
                dtype=directions.dtype,
            )
        ]
        if degree > 0:
            bases.extend([-cls._SH_C1 * y, cls._SH_C1 * z, -cls._SH_C1 * x])
        if degree > 1:
            xx, yy, zz = x * x, y * y, z * z
            xy, yz, xz = x * y, y * z, x * z
            bases.extend(
                [
                    cls._SH_C2[0] * xy,
                    cls._SH_C2[1] * yz,
                    cls._SH_C2[2] * (2.0 * zz - xx - yy),
                    cls._SH_C2[3] * xz,
                    cls._SH_C2[4] * (xx - yy),
                ]
            )
        if degree > 2:
            bases.extend(
                [
                    cls._SH_C3[0] * y * (3 * x * x - y * y),
                    cls._SH_C3[1] * x * y * z,
                    cls._SH_C3[2] * y * (4 * z * z - x * x - y * y),
                    cls._SH_C3[3] * z * (2 * z * z - 3 * x * x - 3 * y * y),
                    cls._SH_C3[4] * x * (4 * z * z - x * x - y * y),
                    cls._SH_C3[5] * z * (x * x - y * y),
                    cls._SH_C3[6] * x * (x * x - 3 * y * y),
                ]
            )
        if degree > 3:
            xx, yy, zz = x * x, y * y, z * z
            xy, yz, xz = x * y, y * z, x * z
            bases.extend(
                [
                    cls._SH_C4[0] * xy * (xx - yy),
                    cls._SH_C4[1] * yz * (3 * xx - yy),
                    cls._SH_C4[2] * xy * (7 * zz - 1),
                    cls._SH_C4[3] * yz * (7 * zz - 3),
                    cls._SH_C4[4] * (zz * (35 * zz - 30) + 3),
                    cls._SH_C4[5] * xz * (7 * zz - 3),
                    cls._SH_C4[6] * (xx - yy) * (7 * zz - 1),
                    cls._SH_C4[7] * xz * (xx - 3 * yy),
                    cls._SH_C4[8] * (xx * (xx - 3 * yy) - yy * (3 * xx - yy)),
                ]
            )
        return torch.stack(bases, dim=1)

    @staticmethod
    def _fibonacci_sphere(num_samples: int, device, dtype) -> torch.Tensor:
        indices = torch.arange(num_samples, device=device, dtype=dtype)
        z = 1.0 - 2.0 * (indices + 0.5) / num_samples
        radius = torch.sqrt(torch.clamp(1.0 - z * z, min=0.0))
        phi = np.pi * (3.0 - np.sqrt(5.0)) * indices
        return torch.stack(
            [radius * torch.cos(phi), radius * torch.sin(phi), z],
            dim=1,
        )

    @classmethod
    def _rotate_sh_features(
        cls,
        features: torch.Tensor,
        rotation_matrix: torch.Tensor,
    ) -> torch.Tensor:
        num_coeffs = features.shape[1]
        degree = int(round(np.sqrt(num_coeffs))) - 1
        if (degree + 1) ** 2 != num_coeffs or degree <= 0:
            return features

        supported_degree = min(degree, 4)
        rotate_coeffs = (supported_degree + 1) ** 2
        sample_count = max(4 * rotate_coeffs, 128)
        directions = cls._fibonacci_sphere(
            sample_count,
            device=features.device,
            dtype=features.dtype,
        )
        bases = cls._evaluate_sh_bases(directions, supported_degree)

        # For row-vector directions, a world-space ray maps into the object's
        # pre-rotation frame as d_local = d_world @ R.
        local_dirs = torch.nn.functional.normalize(
            directions @ rotation_matrix.to(device=features.device, dtype=features.dtype),
            dim=1,
        )
        local_bases = cls._evaluate_sh_bases(local_dirs, supported_degree)
        rotation_projection = torch.linalg.pinv(bases) @ local_bases

        rotated = features.clone()
        rotated[:, :rotate_coeffs, :] = torch.einsum(
            "ij,njc->nic",
            rotation_projection,
            features[:, :rotate_coeffs, :],
        )
        return rotated

    @staticmethod
    def translation(xyz, x: float, y: float, z: float):
        if x == 0. and y == 0. and z == 0.:
            return xyz

        return xyz + torch.tensor([[x, y, z]], device=xyz.device)

    @staticmethod
    def rescale(xyz, scaling, factor: float):
        if factor == 1.:
            return xyz, scaling
        return xyz * factor, scaling * factor

    @staticmethod
    def rx(theta):
        theta = torch.tensor(theta)
        return torch.tensor([[1, 0, 0],
                             [0, torch.cos(theta), -torch.sin(theta)],
                             [0, torch.sin(theta), torch.cos(theta)]], dtype=torch.float)

    @staticmethod
    def ry(theta):
        theta = torch.tensor(theta)
        return torch.tensor([[torch.cos(theta), 0, torch.sin(theta)],
                             [0, 1, 0],
                             [-torch.sin(theta), 0, torch.cos(theta)]], dtype=torch.float)

    @staticmethod
    def rz(theta):
        theta = torch.tensor(theta)
        return torch.tensor([[torch.cos(theta), -torch.sin(theta), 0],
                             [torch.sin(theta), torch.cos(theta), 0],
                             [0, 0, 1]], dtype=torch.float)

    @classmethod
    def rotate_by_euler_angles(cls, xyz, rotation, x: float, y: float, z: float):
        """
        rotate in z-y-x order, radians as unit
        """

        if x == 0. and y == 0. and z == 0.:
            return

        # rotate
        rotation_matrix = cls.rx(x) @ cls.ry(y) @ cls.rz(z)
        xyz, rotation = cls.rotate_by_matrix(
            xyz,
            rotation,
            rotation_matrix.to(xyz),
        )

        return xyz, rotation

    @classmethod
    def rotate_by_wxyz_quaternions(cls, xyz, rotations, features, quaternions: torch.tensor):
        if torch.all(quaternions == 0.) or torch.all(quaternions == torch.tensor(
                [1., 0., 0., 0.],
                dtype=quaternions.dtype,
                device=quaternions.device,
        )):
            return xyz, rotations, features

        # convert quaternions to rotation matrix
        rotation_matrix = torch.tensor(qvec2rotmat(quaternions.cpu().numpy()), dtype=torch.float, device=xyz.device)
        # rotate xyz
        xyz = torch.matmul(xyz, rotation_matrix.T)
        # rotate gaussian quaternions
        rotations = torch.nn.functional.normalize(cls.quat_multiply(
            rotations,
            quaternions,
        ))

        # Rotate all supported SH bands so relit directional effects stay in
        # the same frame as the transformed object.
        if features.shape[1] > 1:
            features = cls._rotate_sh_features(features, rotation_matrix)

        return xyz, rotations, features

    @staticmethod
    def quat_multiply(quaternion0, quaternion1):
        w0, x0, y0, z0 = torch.split(quaternion0, 1, dim=-1)
        w1, x1, y1, z1 = torch.split(quaternion1, 1, dim=-1)
        return torch.concatenate((
            -x1 * x0 - y1 * y0 - z1 * z0 + w1 * w0,
            x1 * w0 + y1 * z0 - z1 * y0 + w1 * x0,
            -x1 * z0 + y1 * w0 + z1 * x0 + w1 * y0,
            x1 * y0 - y1 * x0 + z1 * w0 + w1 * z0,
        ), dim=-1)

    @classmethod
    def rotate_by_matrix(cls, xyz, rotations, rotation_matrix):
        # rotate xyz
        xyz = torch.matmul(xyz, rotation_matrix.T)

        # rotate via quaternion
        rotations = torch.nn.functional.normalize(cls.quat_multiply(
            rotations,
            torch.tensor([rotmat2qvec(rotation_matrix.cpu().numpy())]).to(xyz),
        ))

        return xyz, rotations
