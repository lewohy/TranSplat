"""발표 자료용 실제 이미지: 한 방향에서 본 lego 깊이 이미지 (phase 1과 같은 카메라·렌더러).

실행: .venv/bin/python report/experiment-001/fig/make_depth_figs.py
출력: 이 폴더의 depth_*.png, color_fixed.png, depth_meta.json
"""
import json
import math
import sys
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn.functional as F
from matplotlib import colormaps

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
import radiance_transfer_TranSplat as rt  # noqa: E402
from gaussian_renderer import render  # noqa: E402

OUT = Path(__file__).resolve().parent
PLY = REPO / "sample/outputs/lego_rgba/point_cloud/iteration_30000/point_cloud.ply"  # 원본 RGBA로 학습한 모델 (AGENTS.md 3.7)
RES = 1024
ELEV, AZIM = 35.0, 200.0  # up 축(학습 카메라 평균) 기준 고도/방위각 (도)
# 슬라이드에 표시하는 지점 (픽셀 x, y). 깊이는 주변 5x5의 중앙값을 depth_meta.json에 기록
PROBES = {"cab": (450, 285), "bucket": (590, 440), "plate": (640, 700)}


def camera(center, direction, radius, up, device):
    """rt.create_telephoto_camera와 같은 배치(거리 5r, 화각, near/far ±1.5r). up만 장면의 위쪽으로 (그림 보기 좋게)."""
    D = radius * 5.0
    origin = center + direction * D
    forward = F.normalize(center - origin, dim=0)
    right = F.normalize(torch.cross(up, forward, dim=0), dim=0)
    true_up = F.normalize(torch.cross(forward, right, dim=0), dim=0)
    R = torch.stack([right, -true_up, forward], dim=1)
    W2C = torch.eye(4, device=device)
    W2C[:3, :3], W2C[3, :3] = R, -origin @ R
    fov = 2.0 * math.asin(radius / D) * 1.2
    znear, zfar = D - radius * 1.5, D + radius * 1.5
    P = rt.getProjectionMatrix(znear, zfar, fov, fov).transpose(0, 1).to(device)
    return rt.MiniCam(RES, RES, fov, fov, znear, zfar, W2C, W2C @ P, origin), znear, zfar


def render_depth(g, cam):
    """phase 1과 같은 렌더 (depth_ratio 0 = alpha 가중평균 깊이). (깊이, alpha, 색)"""
    model = rt.MockGaussianModel(g)
    bg = torch.ones(3, device="cuda")
    with torch.no_grad():
        pkg = render(cam, model, rt.MockPipeline(), bg)
    return (
        pkg["surf_depth"][0].cpu().numpy(),
        pkg["rend_alpha"][0].cpu().numpy(),
        pkg["render"].clamp(0, 1).permute(1, 2, 0).cpu().numpy(),
    )


def save_depth(name, depth, lo, hi, valid=None):
    """가까울수록 밝게. 기록 없는 픽셀(0)은 연회색 배경."""
    valid = depth > 0 if valid is None else valid
    t = np.clip((depth - lo) / (hi - lo), 0, 1)
    rgb = colormaps["magma"](1.0 - t)[..., :3]
    rgb[~valid] = (0.93, 0.93, 0.92)
    cv2.imwrite(str(OUT / name), cv2.cvtColor((rgb * 255).astype(np.uint8), cv2.COLOR_RGB2BGR))
    return float(valid.mean())


def main():
    g = rt.load_ply(str(PLY))
    xyz = g["xyz"].detach()
    cams = json.loads((PLY.parents[2] / "cameras.json").read_text())
    up = F.normalize(-torch.tensor([c["rotation"] for c in cams], device="cuda")[:, :, 1].mean(0), dim=0)
    ref = torch.eye(3, device="cuda")[int(up.abs().argmin())]
    e1 = F.normalize(ref - (ref @ up) * up, dim=0)
    e2 = torch.cross(up, e1, dim=0)
    el, az = math.radians(ELEV), math.radians(AZIM)
    d = math.cos(el) * (math.cos(az) * e1 + math.sin(az) * e2) + math.sin(el) * up

    # 현재 TranSplat phase 1 그대로: 평균 중심, 1.8 × 최대 거리, 잡티 포함.
    c0 = xyz.mean(0)
    r0 = torch.norm(xyz - c0, dim=1).max().item() * 1.8
    cam0, n0, f0 = camera(c0, d, r0, up, "cuda")
    dep0, _, _ = render_depth(g, cam0)

    # 수정: opaque 점 99.5% 분위수 × 1.1, 그 밖 잡티는 그림자맵에서 제외 (shadow_frequency_study와 같음).
    opaque = torch.sigmoid(g["opacity"].detach()[:, 0]) > 0.5
    c1 = xyz[opaque].median(0).values
    dist = torch.norm(xyz - c1, dim=1)
    r1 = torch.quantile(dist[opaque], 0.995).item() * 1.1
    g1 = dict(g)
    g1["opacity"] = g["opacity"].detach().clone()
    g1["opacity"][dist > r1] = -30.0
    cam1, n1, f1 = camera(c1, d, r1, up, "cuda")
    dep1, alpha1, col1 = render_depth(g1, cam1)
    cv2.imwrite(str(OUT / "color_fixed.png"), cv2.cvtColor((col1 * 255).astype(np.uint8), cv2.COLOR_RGB2BGR))

    # 같은 색 범위로 비교하려면 물체 깊이 범위(수정 버전)를 공통으로 쓴다.
    v = dep1[dep1 > 0]
    lo, hi = float(np.percentile(v, 1)), float(np.percentile(v, 99))
    cov0 = save_depth("depth_transplat.png", dep0, lo + (5 * r0 - 5 * r1), hi + (5 * r0 - 5 * r1))
    cov1 = save_depth("depth_fixed.png", dep1, lo, hi)
    # 참고: alpha 0.5 미만 픽셀(옅은 Gaussian만 걸린 곳)을 지운 것. phase 1은 이런 픽셀도 깊이로 쓴다.
    save_depth("depth_fixed_alpha05.png", dep1, lo, hi, valid=alpha1 >= 0.5)
    a = (np.clip(alpha1, 0, 1) * 255).astype(np.uint8)
    cv2.imwrite(str(OUT / "alpha_fixed.png"), 255 - a)
    meta = dict(
        elev_azim=(ELEV, AZIM), direction=d.tolist(), up=up.tolist(),
        transplat=dict(radius=r0, near=n0, far=f0, coverage=cov0),
        probes={k: float(np.median(dep1[y - 2:y + 3, x - 2:x + 3])) for k, (x, y) in PROBES.items()},
        fixed=dict(radius=r1, near=n1, far=f1, coverage=cov1, frac_alpha_lt05=float(((dep1 > 0) & (alpha1 < 0.5)).mean()), depth_lo=lo, depth_hi=hi, n_culled=int((dist > r1).sum())),
    )
    (OUT / "depth_meta.json").write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
