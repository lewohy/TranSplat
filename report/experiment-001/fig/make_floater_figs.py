"""발표 자료용 실제 이미지: 잡티(floater)가 만든 비교 오류 (정답 계산 5번 문제).

v2(잡티 포함)에서 고도 10° 광원(dir2) 쪽이 모든 점에서 가려졌던 것을 보여준다.
(a) 그 광원 방향 그림자맵 카메라에서 본 컬러 렌더: 잡티 포함 / 제외
(b) 점 하나의 방향별 가림 지도 (cube map 6면 펼침, study와 같은 SH 좌표·hard 판정): 잡티 포함 / 제외
점은 v2와 v3의 공통 평가점 중 v2에서 dir2 원판이 전부 가렸고 v3에서는 전부 보이는 점 가운데 v3 밝기가 가장 큰 점.

실행: .venv/bin/python report/experiment-001/fig/make_floater_figs.py  (GPU 약 4분, 그림만 다시: --redraw)
출력: floater_view_{with,without}.png, floater_cube_{with,without}.png, floater_vis.npz, floater_meta.json
"""
import argparse
import json
import math
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
RUNS = REPO / "sample/outputs/lego/point_cloud/iteration_30000"
PLY = RUNS / "point_cloud.ply"
LIGHT = "dir2_10deg"
CUBE = 32  # 한 면의 칸 수 (study는 64)
CELL = 6  # 저장할 때 한 칸의 픽셀 수


def pick_point():
    a, b = np.load(RUNS / "shadow_frequency_study_v2/per_point.npz"), np.load(RUNS / "shadow_frequency_study_v3/per_point.npz")
    _, xa, xb = np.intersect1d(a["eval_idx"], b["eval_idx"], return_indices=True)
    flip = (a[f"{LIGHT}__lit_frac"][xa] <= 0.02) & (b[f"{LIGHT}__lit_frac"][xb] >= 0.98)
    cand = xb[flip]
    k = cand[np.argmax(b[f"{LIGHT}__oracle"][cand])]
    return int(b["eval_idx"][k]), b["normals_sh"][k], int(flip.sum())


def cube_image(vis, normal_sh, light_sh, up_sh):
    """[6*CUBE*CUBE] 보임(1)/가림(0) → 6면을 펼친 십자 그림 (SH 좌표 축 그대로라 study의 격자와 칸이 맞음).

    밝음 = 보임, 검정 = 가림, 회색 = normal 반대쪽 반구(2DGS 원판의 뒷면, 빛을 안 받음).
    표시: 파란 점 = n, 회색 X = -n, 주황 원 = 광원 방향, 초록 삼각형 = 장면의 위쪽. 면 경계는 회색 선.
    """
    n = CUBE * CELL
    s = (np.arange(n) + 0.5) / n * 2 - 1
    S, T = np.meshgrid(s, s)  # S: 오른쪽, T: 아래쪽
    one = np.ones_like(S)
    faces = {  # (행, 열): 방향. 이웃 면의 경계가 이어지는 표준 십자 배치
        (0, 1): (S, one, T), (1, 0): (-one, -T, S), (1, 1): (S, -T, one),
        (1, 2): (one, -T, -S), (1, 3): (-S, -T, -one), (2, 1): (S, -one, -T),
    }
    img = np.full((3 * n, 4 * n, 3), 255, np.uint8)
    colors = np.array([[46, 42, 40], [235, 238, 242], [178, 178, 178]], np.uint8)  # BGR
    best = {}  # 표시할 방향마다 가장 가까운 픽셀 (dot, x, y)

    for (r, c), xyz in faces.items():
        d = torch.nn.functional.normalize(torch.from_numpy(np.stack(xyz, -1).reshape(-1, 3)).float(), dim=1)
        t = sfs.cube_lookup(d, CUBE).numpy()
        k = (vis[t] > 0.5).astype(int)
        k[d.numpy() @ normal_sh <= 0] = 2
        img[r * n:(r + 1) * n, c * n:(c + 1) * n] = colors[k].reshape(n, n, 3)
        for name, v in (("n", normal_sh), ("-n", -normal_sh), ("light", light_sh), ("up", up_sh)):
            dot = d.numpy() @ v
            j = int(dot.argmax())
            if dot[j] > best.get(name, (-2,))[0]:
                best[name] = (dot[j], c * n + j % n, r * n + j // n)
    for (r, c) in faces:
        cv2.rectangle(img, (c * n, r * n), ((c + 1) * n - 1, (r + 1) * n - 1), (120, 120, 120), 2)
    # 위아래를 뒤집어 장면의 위쪽(lego는 SH 좌표 -y 근처)이 그림 위로 오게 함. 칸 격자는 그대로 맞음
    img = np.ascontiguousarray(img[::-1])
    best = {k: (v[0], v[1], 3 * n - 1 - v[2]) for k, v in best.items()}
    _, x, y = best["n"]
    cv2.circle(img, (x, y), 2 * CELL, (200, 110, 40), -1)
    _, x, y = best["-n"]
    q = 2 * CELL
    cv2.line(img, (x - q, y - q), (x + q, y + q), (90, 90, 90), 4)
    cv2.line(img, (x - q, y + q), (x + q, y - q), (90, 90, 90), 4)
    _, x, y = best["light"]
    cv2.circle(img, (x, y), 3 * CELL, (40, 140, 245), 4)
    _, x, y = best["up"]
    tri = np.array([(x, y - 3 * CELL), (x - 3 * CELL, y + 2 * CELL), (x + 3 * CELL, y + 2 * CELL)], np.int32)
    cv2.fillPoly(img, [tri], (110, 160, 40))
    return img


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--shadow-res", type=int, default=2048)
    parser.add_argument("--redraw", action="store_true", help="렌더 없이 floater_vis.npz로 그림만 다시 그림")
    args = parser.parse_args()
    device = "cuda"
    torch.set_grad_enabled(False)
    if args.redraw:
        c = np.load(OUT / "floater_vis.npz")
        for name in ("with", "without"):
            cv2.imwrite(str(OUT / f"floater_cube_{name}.png"), cube_image(c[name].astype(float), c["normal"], c["light"], c["up"]))
        return
    meta = json.loads((RUNS / "shadow_frequency_study_v3/results.json").read_text())["meta"]

    g = rt.load_ply(str(PLY))
    xyz = g["xyz"].detach()
    opaque = torch.sigmoid(g["opacity"].detach()[:, 0]) > meta["min_opacity"]
    center, _, radius, dist = sfs.robust_bounds(xyz, opaque, meta["radius_quantile"], meta["radius_margin"])
    clean = dict(g)
    clean["opacity"] = g["opacity"].detach().clone()
    clean["opacity"][dist > radius] = -30.0
    sets = {"with": g, "without": clean}

    idx, normal_sh, n_flip = pick_point()
    light_world = torch.tensor(meta["lights_world"][LIGHT], device=device)
    light_sh = sfs.to_sh_frame(light_world)

    # (a) 광원 방향에서 본 모습 (그림자맵 카메라와 같은 거리·화각, up만 장면 위쪽)
    cams = sfs.load_cameras(PLY.parents[2] / "cameras.json", device)
    up = torch.nn.functional.normalize(-torch.stack([c["R"][:, 1] for c in cams]).mean(0), dim=0)
    cam, _, _ = mdf.camera(center, light_world, radius, up, device)
    W2C = cam.world_view_transform
    p = xyz[idx] @ W2C[:3, :3] + W2C[3, :3]
    f = 1.0 / math.tan(cam.FoVx / 2)
    uv = ((p[0] * f / p[2] + 1) * mdf.RES / 2).item(), ((p[1] * f / p[2] + 1) * mdf.RES / 2).item()
    for name, gs in sets.items():
        pkg = render(cam, rt.MockGaussianModel(gs), rt.MockPipeline(), torch.ones(3, device=device))
        img = (pkg["render"].clamp(0, 1).permute(1, 2, 0).cpu().numpy() * 255).astype(np.uint8)
        img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        cv2.circle(img, (round(uv[0]), round(uv[1])), 14, (40, 140, 245), 4)
        cv2.imwrite(str(OUT / f"floater_view_{name}.png"), img)

    # (b) 점 하나의 방향별 가림 (study의 oracle과 같은 hard 판정, cube 방향)
    D, w = sfs.cube_directions(CUBE, device)
    margs = argparse.Namespace(**{k: meta[k] for k in ("oracle_depth", "bias_const", "bias_slope", "normal_offset")})
    eval_idx = torch.tensor([idx], device=device)
    normals = torch.tensor(normal_sh, device=device, dtype=torch.float32)[None]
    cache = dict(normal=normal_sh, light=light_sh.cpu().numpy(), up=sfs.to_sh_frame(up).cpu().numpy())
    stats = dict(point=idx, n_flip_points=n_flip, light=LIGHT, cube=CUBE, shadow_res=args.shadow_res)
    for name, gs in sets.items():
        mapper = sfs.ShadowMapper(gs, eval_idx, normals, center, radius, args.shadow_res, margs)
        vis = torch.stack([mapper(d, [meta["bias"]])[meta["bias"]][0] for d in rt.tqdm(D, desc=name)]).cpu().numpy()
        # 표면 아래(반구 밖) 방향은 원래 안 보이므로 보임 비율은 위쪽 반구만
        upper = (D @ normals[0]).cpu().numpy() > 0
        stats[f"visible_upper_{name}"] = float(vis[upper].mean())
        stats[f"ao_{name}"] = float((w.cpu().numpy() * vis * np.clip(D.cpu().numpy() @ normal_sh, 0, None)).sum() / math.pi)
        cache[name] = (vis > 0.5).astype(np.uint8)
        cv2.imwrite(str(OUT / f"floater_cube_{name}.png"), cube_image(vis, normal_sh, cache["light"], cache["up"]))
    np.savez_compressed(OUT / "floater_vis.npz", **cache)
    # 잡티 때문에만 가려진 방향 (n 쪽 반구)이 장면 위쪽 기준 어느 고도에 있나
    Dn = D.cpu().numpy()
    up_sh = cache["up"]
    only = upper & (cache["with"] == 0) & (cache["without"] == 1)
    elev = np.degrees(np.arcsin(np.clip(Dn @ up_sh, -1, 1)))
    stats["floater_only_frac_upper"] = float(only.sum() / upper.sum())
    stats["floater_only_elev_q10_50_90"] = np.percentile(elev[only], [10, 50, 90]).round(1).tolist()
    stats["normal_dot_up"] = float(normal_sh @ up_sh)
    # 2DGS 원판의 원래 normal(회전의 z축)이 카메라 투표로 뒤집혔는지
    raw = sfs.to_sh_frame(rt.quaternion2rotmat(torch.nn.functional.normalize(g["rotation"].detach()[idx:idx + 1], dim=1))[0, :, 2])
    stats["raw_normal_dot_voted"] = float(raw.cpu().numpy() @ normal_sh)
    (OUT / "floater_meta.json").write_text(json.dumps(stats, indent=2))
    print(stats)


if __name__ == "__main__":
    main()
