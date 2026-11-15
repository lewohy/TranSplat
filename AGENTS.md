# AGENTS.md

이 저장소에서 작업하는 에이전트(Claude 세션 등)를 위한 인수인계 문서입니다.
작업을 시작하기 전에 전체를 읽고, 작업이 끝날 때마다 아래 [문서 유지 규칙](#문서-유지-규칙)에 따라 갱신하세요.

마지막 갱신: 2026-11-15

---

## 1. 현재 목표

TranSplat(arXiv 2503.22676, 본 저장소)의 한계 중 하나인 **고주파(날카로운) self-shadow 재구성**을 개선하려 한다.
후보 방향은 visibility/조명 표현을 SH 대신 **wavelet 기반**(Ng et al. 2003/2004의 triple product wavelet 계열)으로 바꾸는 것이다.

**지금 단계의 목표는 구현이 아니라 판단 근거 수치 확보다.**
"wavelet 방향으로 진행할지 / 방향을 바꿀지"를 설명할 수 있는 실험 수치를 먼저 뽑는다.

## 2. 배경: TranSplat의 그림자 계산 경로

핵심 파일은 `radiance_transfer_TranSplat.py` 하나다.

1. **Phase 1 (bake, `phase_1_bake_visibility_sh`)**: Fibonacci 방향 1200개마다 그 방향에서 물체를 보는 망원 카메라로 depth(그림자맵)를 렌더하고, 각 Gaussian이 가려졌는지 판정 → per-Gaussian visibility를 SH(l≤3, 16계수) `V_lm`으로 투영.
   - 판정은 ESM(`exp(-α·깊이차)`, `α = 8/scene_radius`) + 8-tap Poisson PCF, bias = 3×max_scale.
   - `scene_radius = 1.8 × (중심에서 가장 먼 Gaussian 거리)`.
2. **Phase 2 diffuse (`phase_2_decoupled_relight`)**: 환경맵을 1200방향 최근접 픽셀 샘플링으로 SH 투영(`compute_global_sh_coeffs`) → Gaunt tensor로 `L·V` 곱(l≤3에서 절단) → l≤2 clamped cosine으로 irradiance.

3. **Phase 2 색 변환**: diffuse는 `c_new = c_old × E_target/(E_source + floor)` (floor = 0.05×가림 없는 source irradiance, 최대 3배). specular(l≥1 rest 계수)도 가려진 target 조명 `L·V`를 반사 방향에서 읽어 변환하므로 V가 들어간다 (A_l 추정은 가림 없는 source 조명으로 나눔). 2026-11-14 확인, 이전 "specular는 V를 안 씀" 설명은 틀림.
   - study는 target irradiance E만 평가했다. 최종 색에 쓰이는 비율(source 쪽 그림자 제거 포함), Gaussian 크기에 따른 화면상 그림자 경계, specular 경로는 아직 측정하지 않았다.

좌표 규약: SH 방향 공간은 world 대비 **x축이 뒤집혀 있다** (코드 곳곳의 x-flip 참고).
`evaluate_sh_bases_torch`는 l≤3까지만 구현되어 있고, `l_max`가 PLY의 `sh_degree`에 묶여 있다.

## 3. 지금까지 한 일

### 3.1 `scripts/shadow_frequency_study.py`
합성 환경맵(균일 ambient + 각지름 2/5/10/30° 원판 광원, 3방향)으로 per-Gaussian diffuse irradiance를 여러 방식으로 계산해 **oracle** 대비 오차를 낸다. 각 행은 oracle에서 한 요소만 바꾼 것. 실행 한 번으로 A(oracle 신뢰성)/B(쉬운 수정 후 SH 절단 비중)/C(Haar vs SH)와 판정 표를 `results.md` 맨 위에 출력한다.

| 행 | 의미 |
|---|---|
| `oracle` | 기준값. cube map(기본 64²×6) 방향 + 광원 내부 샘플 직접 적분, hard visibility(median depth, 그림자맵 2048, normal offset bias), 정확한 clamped cosine |
| `oracle_res2x` / `oracle_dir2x` / `oracle_bias_*` | 수렴·bias 민감도 확인 (그림자맵 4096 / 방향 2배 / 다른 bias) |
| `filt` | visibility만 ESM+PCF로 |
| `cos2` | cosine만 l≤2로 절단 |
| `sh{l}_L` / `_V` / `_LV` | 조명만 / visibility만 / 둘 다 SH 차수 l로 절단. `sh3_LV`가 현재 방식 |
| `pipe1200` | 실제 Phase 1 + Phase 2 diffuse 코드 그대로 |
| `pipe1200_exactL` | 위와 같되 조명 SH만 정확히 투영 |
| `pipefix1200` / `_hard` | 쉬운 수정(robust radius + 정확한 조명 투영) 파이프라인, ESM / hard visibility |
| `C_{V,LV,T}_{sh K,haar K}` | V / L·V / transfer를 SH 또는 Haar(cube face별 2D, nonlinear top-k)로 계수 K개로 압축. 요약은 압축 안 한 cube 대비 오차(`*_vscube`)로 비교 |
| `C_H_*` | hybrid: 광원은 정확한 그림자, ambient만 압축 V |

지표: `nmae_{region} = mean|E−E_oracle|(region) / mean E_oracle(lit)`. 영역은 광원 내부 샘플 가시 비율로 lit(≥98%)/penumbra/umbra(≤2%).

oracle 오염 원인과 수정 (2026-11-02 확인):
- robust radius 밖 floater가 그림자맵 카메라와 물체 사이를 막음 → 이 study의 그림자맵에서 제외 (`--keep-floaters`로 끔). `pipe*` 행은 phase 1 그대로.
- floater로 scene radius 약 7배 과대 (lego: 13.9 vs 1.9) → opaque 점 99.5% 분위수 × 1.1.
- surfel normal 부호가 임의(약 48%가 뒤집힘) → 학습 카메라 투표로 방향 결정. up 축도 카메라에서 자동 추정.
- 내부 surfel 층이 가림으로 판정됨 → 2개 이상 학습 뷰에서 보이고 렌더 표면 0.5px 이내인 점만 평가.
- texel 단위 bias는 겹친 surfel에서 acne → normal 방향으로 2×max_scale 오프셋.
- 합성 장면(평면 위 구, 실제 rasterizer, ray-cast 정답)에서 normal/slope bias의 오판정률이 2~3%로 확인됨.

### 3.2 lego 첫 실행 (2026-10-28) — oracle 오염으로 폐기
`shadow_frequency_study/` 결과는 위 오염(AO 중앙값 0.079) 때문에 판단 근거로 쓰지 않는다. "ESM이 그림자를 크게 지운다", "작은 광원에서 1200점 최근접 환경맵 샘플링이 크게 틀린다"는 결론은 3.4에서 다시 확인됨.

### 3.3 lego v2 실행 (2026-11-02) — floater 가림으로 폐기
`shadow_frequency_study_v2/`는 robust radius 밖 floater 280개(중심에서 4.3~7.5)가 그림자맵 카메라와 물체 사이에 있어 dir2(고도 10°) 광원이 전부 umbra였고, 그 방향 cone이 모든 점에서 검게 나왔다. 이 큰 검은 블록 때문에 Haar 이점이 과대(최대 2.9배)로 나왔다. 수치는 쓰지 않는다.

### 3.4 lego v3 + cube 128 + hybrid (2026-11-02)
- `sample/outputs/lego/point_cloud/iteration_30000/shadow_frequency_study_v3/results.md`: floater 제외(1,907개), 평가점 40,000, cube 64.
- `.../shadow_frequency_study_c128/results.md`: `--only-compact --cube-res 128`, 평가점 20,000.
- `.../shadow_frequency_study_v3/hybrid_check.md`: `scripts/shadow_hybrid_check.py`. 광원만 relight 시점 그림자맵(해상도 × 광원 내부 샘플 수)으로 처리했을 때의 오차.

수치 (penumbra nMAE, 2/5/10/30°):
- A. AO 중앙값 0.655, AO<0.05 0.6%. oracle 불확실성 res2x 0.092/0.062/0.044/0.023, normal_wide 0.19/0.15/0.11/0.05.
- B. `pipe1200` 0.46/0.54/0.35/0.26 → `pipefix1200_hard` 0.22/0.21/0.20/0.15. `sh3_LV` 0.18/0.18/0.17/0.11, `sh9_LV` 0.13/0.13/0.10/0.03.
- C (cube 기준 압축 오차만, SH/Haar 비율):

  | 방식 | 2° | 5° | 10° | 30° |
  |---|---|---|---|---|
  | V, 같은 K=256 | 1.12 | 1.59 | 1.72 | 0.81 |
  | V, 같은 메모리 (haar128 vs sh256) | 0.94 | 1.05 | 1.01 | 0.60 |
  | T, 같은 K=256 | 1.23 | 1.79 | 1.83 | 0.86 |
  | T, 같은 메모리 | 0.99 | 1.20 | 1.16 | 0.63 |

  K=16, 64에서는 같은 K로도 0.9~1.4배다. LV는 K=16에서 Haar가 약 3배 나쁘다 (조명을 16개 Haar 계수로 못 담음). cube 64와 128의 비율 차이는 ±0.1 이내. cube floor는 2°에서 0.094 → 0.054로 줄었다.
- hybrid (광원 그림자 오차만, oracle 2048×64 대비):

  | 그림자맵 | 2° | 5° | 10° | 30° |
  |---|---|---|---|---|
  | 1024px×16 | 0.130 | 0.096 | 0.071 | 0.045 |
  | 2048px×16 | 0.044 | 0.038 | 0.034 | 0.031 |

  샘플 1개(hard 그림자)는 0.20~0.27이다. ambient 쪽은 SH16으로 0.001 (합성 ambient가 균일해서 최선의 경우).

신뢰할 수 있는 결론
- **per-Gaussian Haar wavelet은 같은 메모리에서 SH보다 낫지 않다** (2~10°에서 0.92~1.20배, 30°에서는 0.6배). 같은 계수 수 기준으로도 이점은 K=256, 5~10°에서 1.6~1.8배뿐이고, 판정 임계 2배를 넘는 경우가 없다. cube 해상도를 올려도 바뀌지 않는다.
- SH 차수 증가도 효율이 낮다: l=3 → 9(계수 6배)로 작은 광원 오차가 25%만 준다.
- 쉬운 수정만으로 현재 파이프라인 오차가 2~2.5배 준다. floater 제거, robust radius, 조명 정확 투영, ESM 대신 hard 판정이다. 실제 phase 1도 같은 floater 문제를 갖고 있다 (radius 13.9, floater 포함 렌더).
- 날카로운 광원을 relight 시점 그림자맵으로 따로 처리하면(2048px, 샘플 16) 광원 그림자 오차가 0.03~0.04다. 1024px×16도 5° 이상에서는 모든 압축 방식(SH256 포함)보다 낮다. 샘플 1개짜리 hard 그림자는 오히려 SH보다 나쁘므로 soft 샘플링이 필요하다.

추세만 참고
- 2° 절대 오차 (oracle 해상도 불확실성 0.09).
- 2048px hybrid 오차는 같은 해상도 oracle 대비라 해상도 오차가 빠져 있다 (실제는 res2x 수준 0.02~0.09가 더해질 수 있음).
- 합성 환경맵(균일 ambient + 원판) 기준이다. 실제 HDR에서는 광원 분리 후 남는 부분이 균일하지 않아 hybrid의 ambient 오차가 커질 수 있다. 저장소에 실제 HDR은 없다.

### 3.5 발표 자료 (2026-11-02)
- `report/experiment-001/report.typ`: 연구미팅용 슬라이드 21장, **2026-11-15부터 수치·그림은 다시 학습한 `lego_rgba` 기준 (3.7)** (TranSplat 그림자 구현 개요 → 1단계 bake ① 깊이 이미지 렌더 (+ 개념 3D 그림·실제 lego 깊이 이미지 2장) / ② 가림 판정(ESM+PCF) / ③ SH 누적 → 2단계 relight ④ → 문제 (한 Gaussian의 방향별 가림을 구 껍질 3D 그림과 그 단면 그래프로, 둘 다 실제 SH16 복원값) → 질문 A/B/C → 실험 조건(광원 크기 = 점에서 본 각지름 그림) → 정답 계산(하늘 2.5만 방향 + 원판 64방향, 보이는 개수로 L/P/그림자) → 하늘 부분 밝기와 AO 식 → 지표 → A 정답 계산 문제 4개 → 수정 결과(AO, 정답 신뢰도) → B → C·메모리 환산 → 결과 분석 → 광원 분리 → 결론·한계). ①~③은 코드에서 방향 1,200개마다 한 번에 도는 루프라 1단계로 묶고, 위치 표시는 `flow-nav`. 실험 조건 슬라이드는 표 아래에 lego 사진(`r_10.png`), 오른쪽에 광원 크기 그림. 답 강조는 `verdict` 컴포넌트.
  - 파일 구성: 색·컴포넌트·그림 도우미는 `theme.typ`, set 규칙(페이지·글꼴)은 `report.typ`에만 둔다. `depth-shell.typ`(`depth-example`)과 `light-vis.typ`(`disc-angle`, `sampling-slide`, `sky-slide`), `sphere-vis.typ`(`shell`, `cut-graph`, 데이터는 `fig/make_sphere_vis.py` → `fig/sphere_vis.json`, 합성 가림막과 그 SH16 복원)은 단독 컴파일용이 아니라 슬라이드 묶음을 내보내고 `report.typ`가 import해서 배치한다. 컴파일은 `report.typ` 하나.
  - 잡티 가림 지도 (2026-11-15, 처음 모델 기준, 지금 슬라이드에는 안 씀): `fig/make_floater_figs.py`(GPU 약 4분, 렌더 결과는 `fig/floater_vis.npz`에 저장해 `--redraw`로 그림만 다시 그림). v2에서 고도 10° 광원이 가려졌다가 v3에서 보이는 점(공통 평가점 5,200개 중 2,767개) 중 하나(#776526)의 방향별 가림을 cube 32, 6면 펼침으로 잡티 포함/제외 렌더. n / −n / 광원 / 장면 위쪽 표시, 위쪽이 그림 위로 오게 상하 반전.
    - 잡티 때문에만 가려진 방향은 n 쪽 반구의 34%, 장면 위쪽 기준 고도 −21°~+17°(10~90% 분위)로 **수평선 근처 띠**다. 이전에 슬라이드에 쓴 "격자와 딱 맞는 정사각형", "하늘 위쪽 통째로"는 둘 다 틀려서 고침. 이 점 AO 0.38 → 0.83.
    - 이 점의 원래 2DGS normal(회전 z축)은 카메라 투표 normal과 정반대 (2번 문제의 실제 예).
    - lego의 장면 위쪽은 SH 좌표 (−0.03, −0.84, −0.54)로 cube 축과 맞지 않는다.
    - v2의 "Haar 2.9배"는 C 표(V/LV 압축, 10°, K=256, 정답 대비 오차: SH 0.076 vs Haar 0.027). v2에서 10° 광원 dir2는 반그림자 점이 0개라 10° 평균은 dir0, dir1만으로 계산됨. v3 같은 칸은 같은 K 1.61, 같은 메모리 1.02 (v3는 압축 안 한 cube 대비 오차라 잣대가 약간 다름).
    - 같은 스크립트가 광원 시점 컬러 렌더(`floater_view_*.png`, 잡티 포함이면 화면 전체가 검게 덮임)도 만들지만 슬라이드에는 안 넣음.
  - 정답 계산 문제 중 1(장면 크기), 2(normal 부호)는 `radiance_transfer_TranSplat.py`에도 그대로 있다. 잡티는 처음 모델의 데이터 준비 문제라 슬라이드에서 뺌 (3.7).
  - 메모리는 실험에서 직접 재지 않았고 계수 수로 환산했다 (fp32, Haar 위치 4바이트 가정. lego_rgba 85만 개 기준 SH256 ≈ Haar128 ≈ 0.87 GB).
- `report/experiment-001/demo.html`: 한 점의 가림 지도를 SH / Haar로 압축해 비교하는 브라우저 데모 (실험과 같은 cube 64, top-k Haar, l≤15 SH).
- 데모로 확인한 경향 (합성 장면, 추세만 참고): 표면 기울기 0°(가림 경계가 cube 격자와 나란함)에서는 Haar가 같은 개수 기준 2~2.7배 낫고, 25° 이상 기울면 0.6~1.4배로 이점이 사라진다. 같은 메모리 기준은 대부분 1 이하. 3.4의 "곡선 경계에서 Haar 비효율" 해석과 맞는다.

### 3.6 lego의 "검은 막"과 깊이 이미지 설명 자료 (2026-11-14)
- 설명 슬라이드 (`report/experiment-001/depth-shell.typ`, report.typ 안에 포함. cetz 개념 그림 + 실제 렌더), 그림은 `report/experiment-001/fig/make_depth_figs.py`, `make_shell_figs.py`로 생성.
- lego 학습 사진은 배경이 검정(`white_background=False`)이라, 판 높이에 납작한 검은 Gaussian 원판이 학습됨: 장면 반지름(1.92) 안 불투명 점의 7.8%(43,955개), 밝기 < 0.03, 높이 중앙값이 판 바닥 수준. 학습 시점(r_10)을 흰 배경으로 렌더하면 화면 전체가 alpha > 0.5. robust radius 기반 잡티 제거로는 안 지워진다.
- 영향 (신뢰): `shadow_frequency_study.py --drop-dark 0.03 --eval-idx-from <v3>/per_point.npz`로 막(밝기 < 0.03인 불투명 점 45,797개, 반지름 밖 포함)을 그림자맵·평가점에서 지우고 v3와 같은 설정으로 재실행 → `.../shadow_frequency_study_v4_nodark/results.md`. v3와 같은 평가점 36,826개로 비교.
  - 정답 밝기: 막이 아래쪽 ambient(전방위 균일 0.2)를 바닥처럼 가려 v3 정답이 평균 2.2% 어두웠음(lit 평균 대비, 점의 약 38%가 1% 넘게 밝아짐). 원판 광원 그림자 판정이 바뀐 점은 1~5%. 반그림자 비율은 그대로. AO 중앙값 0.615 → 0.659.
  - penumbra nMAE(2/5/10/30°) v3 → v4: `sh3_LV` 0.177/0.179/0.167/0.114 → 0.176/0.177/0.163/0.110, `pipefix1200_hard` 0.217/0.216/0.202/0.153 → 0.213/0.211/0.195/0.146, C 비율(V, 같은 메모리) 0.98/1.04/1.00/0.60 → 0.98/1.01/0.95/0.58. **3.4의 B·C 결론은 유지.**
  - 실제 phase 1 그대로인 `pipe1200`만 0.46/0.54/0.35/0.26 → 0.38/0.59/0.36/0.28로 ±0.08 흔들림.
  - `shadow_hybrid_check.py`도 `drop_dark`를 읽지만 v4로는 아직 안 돌림 (원판 그림자 판정 변화가 작아 결론 영향은 없을 것으로 봄).
- 현재 phase 1은 expected depth + `depth > 0`이면 유효라서, 옅은 Gaussian만 걸린 픽셀도 가림체가 된다 (고친 반지름 기준 한 방향 깊이 이미지에서 깊이가 찍힌 픽셀의 24%가 alpha < 0.5). 쉬운 수정에 "alpha 0.5 미만 픽셀 무시(또는 median depth)"를 추가 검토.

### 3.7 lego를 원본 RGBA로 다시 학습 (2026-11-15)
- 기존 `sample/outputs/lego`는 COLMAP으로 다시 만든 `sample/colmaps/lego/dense/0`(왜곡 보정 과정에서 alpha가 빠진 798px RGB, 배경 검정)로 학습되어 alpha 마스크 loss가 안 걸렸다. 저자 권장 경로(README: RGBA synthetic → alpha 마스크, `--lambda_alpha 0.05`)가 아니었음. 검은 막과 잡티는 이 데이터 준비 때문.
- 원본: NeRF 공식 예제 데이터(`https://cseweb.ucsd.edu/~viscomp/projects/LF/papers/ECCV20/nerf/nerf_example_data.zip`, bmild/nerf의 `download_example_data.sh`)의 lego → `sample/nerf_synthetic/lego`. train 100장이 기존 `sample/colmaps/lego/images`와 픽셀 단위로 동일.
- 학습: `train.py -s sample/nerf_synthetic/lego -m sample/outputs/lego_rgba --white_background --eval` (나머지 기본값, 약 15분, test PSNR 35.7). `cameras.json`은 test 200 + train 100이라 study용으로 train만 뽑은 `cameras_train.json`을 씀.
- 모델 비교 (신뢰): 물체 밖 잡티 1,907 → 0, phase 1 장면 반지름 13.8 → 2.53 (robust 1.57), r_10 흰 배경 렌더의 alpha>0.5 비율 100% → 26.4% (사진 물체 26.3%) → 검은 막 없음. normal 부호 뒤집힘은 여전히 49% (2DGS 고유).
- study: `sample/outputs/lego_rgba/point_cloud/iteration_30000/shadow_frequency_study/results.md` (v3 설정과 같되 평가점 20,000 = 현재 기본값, 다른 점 집합). penumbra nMAE 2/5/10/30°:
  - A: AO 중앙값 0.672, res2x 0.081/0.053/0.036/0.019.
  - B: `pipe1200` 0.387/0.331/0.240/0.203 (v4 0.38/0.59/0.36/0.28), `pipe1200_exactL` 0.276/0.263/0.250/0.208, `pipefix1200_hard` 0.208/0.204/0.197/0.160, `sh3_LV` 0.184/0.177/0.162/0.105, `sh9_LV` 0.154/0.141/0.108/0.027. 쉬운 수정 효과는 1.9/1.6/1.2/1.3배로 줄었다 (잡티·장면 크기 문제가 원래 없으므로). 남은 큰 수정은 조명 SH 정확 투영(작은 광원)과 hard 판정. share_hard 0.88/0.87/0.82/0.66 → B1·B2 성립 유지.
  - C (V, 같은 메모리 haar128 vs sh256): 1.03/1.16/1.16/0.63, 같은 K=256: 1.33/1.70/1.86/0.91. 임계 2배를 넘는 조건 없음 → **3.4의 C 결론 유지.**
- hybrid (`shadow_hybrid_check.py`, 같은 폴더 `hybrid_check.md`): 1024px×16 0.128/0.088/0.065/0.044, 2048px×16 0.042/0.036/0.034/0.032, 샘플 1개 0.21~0.26. 처음 모델과 거의 같음.
- 깊이 이미지 예시(`make_depth_figs.py`)도 새 모델로 다시 렌더: 물체 밖 기록 없음, alpha<0.5 픽셀 0.3% (처음 모델 24%) → 3.6의 "alpha 0.5 미만 픽셀 무시" 검토는 이 모델에서는 불필요.
- 발표 자료 반영 (2026-11-15, 사용자 결정): 전체를 새 모델 수치로 교체. 1번(장면 크기)은 2.53 vs 1.57로 영향이 작아진 문제로, 잡티·검은 막·처음 학습 사진 이야기는 실험 세팅 실수라 슬라이드에서 모두 뺌 (사용자 결정, 정답 계산 문제는 4개). 정답 신뢰도 표에 띄우는 거리 1.5배(normal_wide) 차이 0.18/0.13/0.09/0.05를 새로 넣음 (2° 결과는 추세만).

## 4. 다음 할 일

방향 제안 (사용자 확인 필요): wavelet 대신 **쉬운 수정 + 광원 분리 hybrid**.
1. `radiance_transfer_TranSplat.py`에 쉬운 수정 반영: floater 제외/robust radius, 조명 SH 정확 투영(최근접 1200점 샘플링 대체), visibility 판정(hard + normal offset 또는 ESM 파라미터 재조정).
2. hybrid 구현: 환경맵에서 밝은 광원 추출 → 광원은 relight 시점에 그림자맵(soft, 샘플 16 정도)으로, 나머지는 기존 SH V로.
3. 실제 HDR 몇 장(실내/야외 해, 창문)으로 study를 다시 돌려 hybrid의 나머지 SH 오차와 광원 추출 기준을 확인.

## 5. 판단 기준

- **진행(wavelet)**: B 이후에도 penumbra 오차의 대부분이 SH 절단 **그리고** SH l=9에서도 작은 광원(2~5°) 오차가 큼 **그리고** C에서 같은 계수 수의 wavelet이 확실히 낮음.
- **방향 전환**: 쉬운 수정만으로 충분, 또는 SH l=5~7로 충분, 또는 wavelet이 같은 예산에서 SH보다 낫지 않음.
- 잠정 임계값: share 0.5, large 0.1, ratio 2.0, small lights = 2, 5°. 3.4 기준으로 B1·B2는 성립하고 C는 모든 K·메모리 조건에서 불성립 → 기준상 **방향 전환**. 사용자 확정 전.

## 6. 미결정 사항 (사용자 결정 필요)

- 4의 방향 제안(wavelet 중단, 쉬운 수정 + hybrid) 승인 여부.
- 판단 임계값 확정 (결론은 임계값을 1.5배로 낮춰도 같은 메모리 기준에서는 바뀌지 않는다).
- 실제 HDR 테스트용 환경맵 선택.

## 7. 환경 메모

- 대상 GPU: RTX 5080(sm_120, 우선), RTX 4060 Ti(sm_89), RTX 3070(sm_86). 2026-11-02에 환경을 이에 맞게 올렸다.
  - Python 3.10, torch 2.7.1+cu128 / torchvision 0.22.1, base image `nvidia/cuda:12.8.1-devel-ubuntu22.04`. 호스트 드라이버는 570 이상이 필요하다.
  - CUDA 확장은 `pyproject.toml`의 `[tool.uv.extra-build-variables]`로 `TORCH_CUDA_ARCH_LIST="8.6;8.9;12.0"` 고정 빌드한다 (uv 캐시의 wheel을 다른 GPU 머신에서 재사용해도 동작하도록).
  - `simple-knn` submodule은 CUDA 12에서 `FLT_MAX` 미정의 오류가 나서 upstream `86710c2`(`<cfloat>` include)로 올렸다.
  - `numpy<2` 고정: open3d 0.18, scikit-image 0.21이 NumPy 1.x용으로 빌드되어 있다 (그래서 opencv는 4.11).
  - 이전 환경(Python 3.8 + torch 2.0.0+cu118)은 sm_120 커널이 없어 5080에서 어떤 CUDA 연산도 실패했다.
- 검증(2026-11-02, 컨테이너 재빌드 전): NVIDIA redist 아카이브로 CUDA 12.8 툴킷을 임시로 구성하고 `UV_PROJECT_ENVIRONMENT`를 다른 경로로 둔 채 `uv sync`. 확장 3개에 sm_86/89/120 SASS가 포함됨, 5080에서 knn·surfel 렌더·backward 정상, `--self-test` 통과, lego 축소 실행 정상 종료. 3070/4060 Ti 실기기 실행은 아직 확인하지 않았다.
- 컨테이너를 재빌드하기 전에는 `/usr/local/cuda`가 11.8이라 이 컨테이너 안에서 `uv sync`가 확장 빌드에서 실패한다. 재빌드 후 `uv sync`를 실행하면 `.venv`가 3.10으로 다시 만들어진다.
- 별도 셸 접근 (2026-11-02 추가, 컨테이너 재빌드 후 반영): 호스트의 repo 루트에서 `devcontainer exec --workspace-folder . zellij -l welcome` → 열린 세션 목록에서 고르거나 새로 생성 (바로 붙으려면 `zellij attach --create main`). CLI는 호스트에 `pnpm add -g @devcontainers/cli` (또는 `npm i -g`)로 설치. VS Code로 연 컨테이너에도 그대로 붙는다.
  - release note/startup tip은 끄고, 대신 세션 첫 pane에 detach/종료 키 안내를 fish greeting으로 띄운다 (`.devcontainer/zellij/greeting.fish`). zellij는 alternate screen을 쓰므로 호스트 터미널 자체 스크롤백은 쓸 수 없고 zellij 스크롤백(마우스 휠, `Ctrl s`)을 쓴다.
  - zellij 웹 클라이언트: `postStartCommand`로 컨테이너 loopback `127.0.0.1:8082`에 띄우고 `forwardPorts`로 호스트 localhost에 노출. loopback 외 바인딩은 zellij가 TLS 인증서를 요구해서 이렇게 했다. `forwardPorts`는 VS Code 등 포워딩을 지원하는 클라이언트로 컨테이너를 열었을 때만 동작한다.
  - 로그인 토큰은 `zellij web --create-token`, `~/.local/share/zellij`(named volume)에 저장되어 재빌드 후에도 유지.
  - zellij 0.45.1은 config 파일이 없으면 웹 서버가 "started"를 출력하고도 listen하지 않는다 → 설정을 `.devcontainer/zellij/config.kdl`에서 이미지에 복사.
- 한글 폰트: `flake.nix`에 `pretendard`(nixpkgs, `share/fonts/opentype`)를 넣고 Dockerfile ENV에 `TYPST_FONT_PATHS=/opt/transplat-env/share/fonts`를 둔다 (2026-11-02, 컨테이너 재빌드 후 반영).
  - typst/tinymist는 nix env 경로를 시스템 폰트로 찾지 않아 이 ENV가 필요하다. typst CLI와 `tinymist lsp` 모두 `TYPST_FONT_PATHS`를 읽고, buildEnv의 심볼릭 링크도 따라간다 (임시 폴더로 확인).
  - fontconfig 기반 프로그램(브라우저, matplotlib 등)은 이 경로를 모른다. 필요하면 fontconfig 설정을 따로 추가해야 한다.
  - 재빌드 전에는 Pretendard OTF를 받아 `--font-path`로 지정해 컴파일했다.
- typst `@preview` 패키지(cetz 0.4.2 등)는 첫 컴파일 때 인터넷에서 받아 캐시한다 (2026-11-14 컨테이너에서 동작 확인).
- 컨테이너에 브라우저/node가 없다. HTML 확인은 scratch에 playwright Chromium을 받고, 부족한 공유 라이브러리를 `apt-get download`(사용자 경로 apt lists)로 받아 `LD_LIBRARY_PATH`로 지정해 headless 실행했다.
- 이 컨테이너 안에서 `nix build`는 권한 오류로 안 된다 (2026-10-28 기준. flake 변경은 컨테이너 재빌드로 반영).
- 컨테이너에서 `nvidia-smi`가 "Failed to initialize NVML: Unknown Error"를 내고 torch가 CUDA를 못 찾으면 컨테이너 재시작으로 해결됨 (2026-11-15, `/dev/nvidia*`는 남아 있었음).
- `git`은 소유자 불일치로 `git -c safe.directory='*' ...` 형태로 실행해야 한다.

## 8. 커밋 규칙

- 제목은 `타입: 짧은 한국어 요약`이고, 요약은 명사형으로 끝낸다 (`…추가`, `…수정`, `…구현`).
- 타입은 Conventional Commits 중 하나를 쓴다.
  - `feat`: 새 기능, 또는 사용자가 볼 수 있는 동작 변경 (예: 새 실험 스크립트, 스크립트에 새 옵션).
  - `fix`: 버그 수정.
  - `refactor`: 동작은 그대로 두고 코드만 바꿈.
  - `perf`: 성능 개선.
  - `style`: 서식이나 import 순서만 바꿈 (코드 변경 없음).
  - `test`: 테스트 추가·수정.
  - `docs`: 문서만 바꿈 (AGENTS.md, `report/` 발표 자료 포함).
  - `build`: 의존성과 빌드 설정 (`pyproject.toml`, `uv.lock`, `flake.nix`, Dockerfile, submodule).
  - `ci`: CI 설정.
  - `chore`: 앱 코드도 빌드도 아닌 나머지 정리 (편집기 설정, `.gitignore`, devcontainer 편의 설정 등).
  - `revert`: 이전 커밋 되돌리기.
- 변경은 가능한 한 위 타입 중 하나에 맞춘다. 정말 맞는 것이 없을 때만 다른 접두어를 쓴다.
- 본문은 제목 아래 빈 줄을 두고 `-` 목록으로 세부 내용을 적는다. 빈 줄이 없으면 git이 메시지 전체를 제목으로 읽는다.
- 변경을 단위별로 나눈다. 각 커밋은 따로 떼어도 동작해야 한다. 이 저장소에는 lint/format/typecheck 설정이 없으므로, 바꾼 스크립트는 실행(가능하면 `--self-test`)되고 `report.typ`는 컴파일되는 상태로 커밋한다.

---

## 문서 유지 규칙

이 문서는 세션 간 인수인계용이므로 **작업 단위가 끝날 때마다** 갱신한다.

- 갱신할 때 맨 위 "마지막 갱신" 날짜를 바꾼다. 날짜는 상대 표현("어제") 대신 절대 날짜로 쓴다.
- **3. 지금까지 한 일**: 새로 만든/바꾼 스크립트, 실행 결과와 결론을 추가한다. 결과는 파일 경로와 핵심 수치를 함께 적고, "신뢰할 수 있는 결론"과 "추세만 참고"를 구분한다.
- **4. 다음 할 일**: 끝난 항목은 지우고 3으로 옮긴다. 새로 생긴 계획을 추가한다.
- **5, 6**: 사용자가 결정하면 6에서 지우고 5나 해당 섹션에 결정 내용과 날짜를 적는다.
- **7**: 환경에서 새로 알게 된 제약/우회 방법을 적는다.
- 틀린 것으로 밝혀진 내용은 남겨두지 말고 고치거나 지운다 (필요하면 "이전 가정 X는 Y로 반박됨"으로 한 줄 남김).
- 코드나 git 기록으로 알 수 있는 세부사항(함수 구현 등)은 반복해서 적지 않는다.
