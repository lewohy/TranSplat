"""설명 문서용: 학습 카메라 한 대 시점에서 검은 배경 / 흰 배경 렌더 (검은 막이 배경색 때문에 안 보였던 것 확인).

실행: .venv/bin/python report/experiment-001/fig/make_shell_figs.py
출력: train_view_{black,white}.png, train_alpha.png, train_photo.png, shell_{top,side}.png,
      train_view_white_rgba.png (원본 RGBA로 다시 학습한 모델, 같은 시점)
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import torch

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_depth_figs as mdf  # noqa: E402
import radiance_transfer_TranSplat as rt  # noqa: E402
import shadow_frequency_study as sfs  # noqa: E402
from gaussian_renderer import render  # noqa: E402

OUT = Path(__file__).resolve().parent
PLY = REPO / "sample/outputs/lego/point_cloud/iteration_30000/point_cloud.ply"
PLY_RGBA = REPO / "sample/outputs/lego_rgba/point_cloud/iteration_30000/point_cloud.ply"
VIEW = 10  # r_10 (5번 슬라이드 사진과 같은 시점)


def main():
    g = rt.load_ply(str(PLY))
    cams = sfs.load_cameras(PLY.parents[2] / "cameras.json", "cuda")
    names = [c["img_name"] for c in json.loads((PLY.parents[2] / "cameras.json").read_text())]
    i = names.index(f"r_{VIEW}")
    model = rt.MockGaussianModel(g)
    for bg, name in ((0.0, "black"), (1.0, "white")):  # 마지막(흰 배경) pkg의 alpha를 아래에서 씀
        with torch.no_grad():
            pkg = render(cams[i]["cam"], model, rt.MockPipeline(), torch.full((3,), bg, device="cuda"))
        img = (pkg["render"].clamp(0, 1).permute(1, 2, 0).cpu().numpy() * 255).astype(np.uint8)
        cv2.imwrite(str(OUT / f"train_view_{name}.png"), cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
    a = pkg["rend_alpha"][0].clamp(0, 1).cpu().numpy()
    # 다시 학습한 모델의 같은 시점 (학습 카메라는 train만 뽑은 cameras_train.json)
    cams_rgba = sfs.load_cameras(PLY_RGBA.parents[2] / "cameras_train.json", "cuda")
    names_rgba = [c["img_name"] for c in json.loads((PLY_RGBA.parents[2] / "cameras_train.json").read_text())]
    with torch.no_grad():
        pkg_rgba = render(cams_rgba[names_rgba.index(f"r_{VIEW}")]["cam"], rt.MockGaussianModel(rt.load_ply(str(PLY_RGBA))),
                          rt.MockPipeline(), torch.ones(3, device="cuda"))
    img = (pkg_rgba["render"].clamp(0, 1).permute(1, 2, 0).cpu().numpy() * 255).astype(np.uint8)
    cv2.imwrite(str(OUT / "train_view_white_rgba.png"), cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
    cv2.imwrite(str(OUT / "train_alpha.png"), ((1 - a) * 255).astype(np.uint8))
    stats = dict(train_alpha_gt05=float((a > 0.5).mean()),
                 rgba_alpha_gt05=float((pkg_rgba["rend_alpha"][0] > 0.5).float().mean()))

    # 위에서 / 옆에서 본 흰 배경 렌더 (robust radius, 그 밖 잡티 제외)
    xyz = g["xyz"].detach()
    opaque = torch.sigmoid(g["opacity"].detach()[:, 0]) > 0.5
    center, _, radius, dist = sfs.robust_bounds(xyz, opaque, 0.995, 1.1)
    g1 = dict(g)
    g1["opacity"] = g["opacity"].detach().clone()
    g1["opacity"][dist > radius] = -30.0
    up = torch.nn.functional.normalize(-torch.stack([c["R"][:, 1] for c in cams]).mean(0), dim=0)
    fwd = torch.nn.functional.normalize(cams[i]["C"] - center, dim=0)
    side = torch.nn.functional.normalize(fwd - (fwd @ up) * up, dim=0)
    for name, d, upv in (("top", up, side), ("side", torch.nn.functional.normalize(side + 0.05 * up, dim=0), up)):
        cam, _, _ = mdf.camera(center, d, radius, upv, "cuda")
        with torch.no_grad():
            pkg = render(cam, rt.MockGaussianModel(g1), rt.MockPipeline(), torch.ones(3, device="cuda"))
        img = (pkg["render"].clamp(0, 1).permute(1, 2, 0).cpu().numpy() * 255).astype(np.uint8)
        cv2.imwrite(str(OUT / f"shell_{name}.png"), cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
    (OUT / "shell_meta.json").write_text(json.dumps(stats, indent=2))
    print(stats)
    src = REPO / "sample/colmaps/lego/dense/0/images" / f"r_{VIEW}.png"
    cv2.imwrite(str(OUT / "train_photo.png"), cv2.imread(str(src)))


if __name__ == "__main__":
    main()
