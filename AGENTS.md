# AGENTS.md

이 저장소에서 작업하는 에이전트(Claude 세션 등)를 위한 인수인계 문서입니다.
작업을 시작하기 전에 전체를 읽고, 작업이 끝날 때마다 아래 [문서 유지 규칙](#문서-유지-규칙)에 따라 갱신하세요.

마지막 갱신: 2026-11-02

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
| `C_{V,LV,T}_{sh K,haar K}` | V / L·V / transfer를 SH 또는 Haar(cube face별 2D, nonlinear top-k)로 같은 계수 수 K로 압축 |

지표: `nmae_{region} = mean|E−E_oracle|(region) / mean E_oracle(lit)`. 영역은 광원 내부 샘플 가시 비율로 lit(≥98%)/penumbra/umbra(≤2%).

oracle 오염 원인과 수정 (2026-11-02 확인):
- floater로 scene radius 9배 과대 → opaque 점 99.5% 분위수 × 1.1.
- surfel normal 부호가 임의(약 48%가 뒤집힘) → 학습 카메라 투표로 방향 결정. up 축도 카메라에서 자동 추정.
- 내부 surfel 층이 가림으로 판정됨 → 2개 이상 학습 뷰에서 보이고 렌더 표면 0.5px 이내인 점만 평가.
- texel 단위 bias는 겹친 surfel에서 acne → normal 방향으로 2×max_scale 오프셋.
- 합성 장면(평면 위 구, 실제 rasterizer, ray-cast 정답)에서 normal/slope bias의 오판정률이 2~3%로 확인됨.

### 3.2 lego 첫 실행 (2026-10-28) — oracle 오염으로 폐기
`shadow_frequency_study/` 결과는 위 오염(AO 중앙값 0.079) 때문에 판단 근거로 쓰지 않는다. "ESM이 그림자를 크게 지운다", "작은 광원에서 1200점 최근접 환경맵 샘플링이 크게 틀린다"는 결론은 3.3에서 다시 확인됨.

### 3.3 lego 본 실행 (2026-11-02)
`sample/outputs/lego/point_cloud/iteration_30000/shadow_frequency_study_v2/results.md` (기본 옵션, 평가점 40,000, 약 45분 / RTX 5080).

A. oracle 신뢰성
- radius 1.918 (phase 1 공식 13.939), 그림자맵 texel 0.0023 < surfel 중앙값 0.009.
- AO 중앙값 0.395, AO<0.05 비율 3.7% (이전 0.079 / 34%) → visibility 정상.
- oracle 자체 불확실성(penumbra nMAE): res2x 0.093/0.054/0.026/0.021, normal_wide bias 0.20/0.12/0.055/0.043 (2/5/10/30°). **2°는 오차 측정치(~0.2)와 같은 크기라 신뢰 불가**, 5°는 경계, 10° 이상은 신뢰 가능.

B. 쉬운 수정 후 오차 구성 (penumbra nMAE, 2/5/10/30°)
- `pipe1200` 0.44/0.74/0.41/0.26 → `pipefix1200` 0.25/0.24/0.22/0.14 → `pipefix1200_hard` 0.21/0.21/0.17/0.11.
- `sh3_LV` 0.23/0.25/0.23/0.11 ≈ pipefix → 쉬운 수정 후 남는 오차는 거의 전부 SH 절단 (share 0.95~1.04).
- SH 차수 올려도 느리게 감소: `sh9_LV` 0.18/0.19/0.14/0.03. 30°만 l=7에서 충분.

C. 같은 계수 수의 Haar vs SH (ratio = SH/Haar, >1이면 Haar가 나음)
- V 압축: 5° 1.53/1.84/2.39, 10° 1.74/2.59/2.85 (K=16/64/256). 2°는 1.25 내외 — cube 64 floor(0.102)가 오차와 같은 크기라 판별 불가.
- LV 압축(triple product): K=16에서 Haar가 더 나쁨(ratio 0.38~0.87). 조명을 16개 Haar 계수로 못 담음. K≥64에서는 V와 비슷.
- 30°는 K≥64에서 차이 없음.
- Haar는 계수마다 index가 필요해 haar{K/2}가 sh{K}와 같은 메모리. 근사 L2 기준 haar32 0.414 vs sh64 0.393, haar128 0.271 vs sh256 0.312 → 같은 메모리에서 이점은 K가 클 때만 소폭.

신뢰할 수 있는 결론
- 현재 파이프라인 오차의 절반 이상은 쉬운 수정(robust radius, 정확한 조명 투영, ESM 대신 hard 판정)으로 없어진다.
- 그 뒤 남는 오차는 SH 절단이 주 원인이고, l=9까지 올려도 작은 광원에서 큼 (B1, B2 성립).
- Haar의 이점은 5~10° 광원, 계수 64 이상에서 1.8~2.9배. 현재 예산(16계수)과 L·V 동시 압축에서는 이점이 없거나 역전.

추세만 참고
- 2° 광원 비교 전체 (oracle 해상도·cube 64 floor 한계).
- 같은 메모리 기준 비교 (per-light 최종 E 오차가 아닌 근사 L2로만 확인).

## 4. 다음 할 일

- 2° 판별: `--cube-res 128` (필요하면 `--shadow-res 4096`)로 C만 재실행해 floor를 낮춘 상태에서 Haar 이점이 커지는지 확인.
- 같은 메모리(haar{K/2} vs sh{K}) 기준 최종 E 오차를 판정 표에 추가.
- 쉬운 수정을 `radiance_transfer_TranSplat.py`에 반영할지 결정 후 구현 (robust radius, 조명 SH 정확 투영, ESM 파라미터/hard 판정).
- wavelet으로 간다면 계수 예산(64~256)과 메모리/속도 비용 추정이 선행되어야 함.

## 5. 판단 기준 (초안, 수치 임계값은 사용자 결정 필요)

- **진행(wavelet)**: B 이후에도 penumbra 오차의 대부분이 SH 절단 **그리고** SH l=9에서도 작은 광원(2~5°) 오차가 큼 **그리고** C에서 같은 계수 수의 wavelet이 확실히 낮음.
- **방향 전환**: 쉬운 수정만으로 충분, 또는 SH l=5~7로 충분, 또는 wavelet이 같은 예산에서 SH보다 낫지 않음.
- 스크립트 기본 임계값(잠정): share 0.5, large 0.1, ratio 2.0, small lights = 2, 5°. 3.3 실행에서 B1·B2는 성립, C는 모든 K에서 불성립(2°가 끌어내림).

## 6. 미결정 사항 (사용자 결정 필요)

- 판단 기준의 수치 임계값 확정 (현재 잠정값은 5 참고). 특히 "small lights"에 신뢰 불가한 2°를 포함할지.
- 허용 계수 예산 (16 유지 / 64 / 256): C 결론이 예산에 따라 갈림.
- 쉬운 수정만 먼저 본 코드에 반영할지.

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
- 이 컨테이너 안에서 `nix build`는 권한 오류로 안 된다 (2026-10-28 기준. flake 변경은 컨테이너 재빌드로 반영).
- `git`은 소유자 불일치로 `git -c safe.directory='*' ...` 형태로 실행해야 한다.
- 커밋 메시지: 기능 단위로 분리, 짧은 한국어 제목, 상세는 본문.

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
