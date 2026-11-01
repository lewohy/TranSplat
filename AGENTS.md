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

### 3.1 `scripts/shadow_frequency_study.py` (미커밋)
합성 환경맵(균일 ambient + 각지름 2/5/10/30° 원판 광원, 3방향)으로 per-Gaussian diffuse irradiance를 여러 방식으로 계산해 **oracle** 대비 오차를 낸다. 각 행은 oracle에서 한 요소만 바꾼 것.

| 행 | 의미 |
|---|---|
| `oracle` | 기준값. SH 압축 없음, Fibonacci 4096방향 + 광원 내부 64방향 직접 적분, hard(0/1) visibility, 정확한 clamped cosine |
| `filt` | visibility만 ESM+PCF로 |
| `cos2` | cosine만 l≤2로 절단 |
| `sh{l}_L` / `_V` / `_LV` | 조명만 / visibility만 / 둘 다 SH 차수 l로 절단 (l=2,3,5,7,9). `sh3_LV`가 현재 방식 |
| `pipe1200` | 실제 Phase 1 + Phase 2 diffuse 코드 그대로 |
| `pipe1200_exactL` | 위와 같되 조명 SH만 정확히 투영 (차이 = 환경맵 샘플링 오차) |

지표:
- `rel_mae_{all,lit,penumbra,umbra}` = 영역별 `mean|E−E_oracle| / mean(E_oracle)`
- `shadow_depth = 1 − mean(E_umbra)/mean(E_lit)`, `shadow_depth_ratio` = 방법/oracle (1=정확, <1=그림자가 옅어짐)
- 영역: 광원을 향한 점 중 광원 내부 64샘플의 가시 비율 ≥98% lit, ≤2% umbra, 그 사이 penumbra

출력(`<ply 폴더>/shadow_frequency_study/`): `results.md`, `results.json`, `per_point.npz`, `envs/*.hdr`, `visibility.npz`(`--save-visibility`; 평가점 × Fibonacci 방향 hard visibility, wavelet 실험 입력).

검증: `--self-test`(CPU) 통과, 해석적 장면(평면 위 구)에서 경향 확인, 가짜 렌더러로 `run()` 전체 경로 확인.

### 3.2 lego 첫 실행 결과 (2026-10-28)
`sample/outputs/lego/point_cloud/iteration_30000/shadow_frequency_study/results.md` (기본 옵션, N=975,252, 평가점 20,000).

**신뢰할 수 있는 결론 (같은 측정 장치 내 상대 비교)**
- ESM 필터링이 그림자를 가장 많이 지운다: `filt`/`pipe1200`의 `shadow_depth_ratio` 0.42~0.70, `sh3_LV`는 0.97~0.99. `pipe1200_exactL ≈ filt` → 현재 파이프라인 오차의 대부분은 ESM.
- 작은 광원에서 환경맵 1200점 최근접 샘플링이 크게, 불규칙하게 틀린다: 예) `dir0_2deg` `pipe1200` 19.07 vs `exactL` 2.96.

**신뢰할 수 없는 부분: oracle 자체가 오염됨**
- floater 0.1%가 중심에서 최대 7.7까지 퍼져 있음(점의 99%는 1.6 이내) → `scene_radius = 13.9`로 약 9배 과대.
- 그 결과 그림자맵에서 물체 폭이 약 115px(1024 중), 픽셀 약 0.033 > surfel 중앙값 0.009 → 해상도 부족.
- ESM α ≈ 0.57로 너무 작아 그림자가 거의 투명.
- hard 판정은 반대로 과다 가림(acne 추정 + 내부 surfel 포함): AO 중앙값 0.079(정상 외부면이면 약 0.5), 평가점의 34%가 AO<0.05, umbra가 약 40%. `rel_mae_umbra`가 20~290으로 튀는 것도 분모(E_oracle umbra)가 거의 0이기 때문.
- 추세만 참고: penumbra SH 절단 오차는 l=3에서 0.40~0.51, l=9에서도 2° 광원은 0.38~0.44로 느리게 감소. L/V 절단 영향은 비슷.

## 4. 다음 할 일

판단에 필요한 질문 3개를 **한 번의 GPU 실행으로** 답하도록 study 스크립트를 확장한다. (사용자 승인 대기 중)

- **A. 기준(oracle) 신뢰성**
  1. floater에 강건한 scene center/radius (예: opacity>0.5 점의 99.5% 분위수)
  2. bias 개선 (slope-scaled bias 또는 normal offset, 옵션화)
  3. 학습 카메라(`cameras.json`)에서 실제로 보이는 Gaussian만 평가 (내부 surfel 제외)
  4. AO 분포를 결과에 출력 (visibility 정상 여부 확인)
  5. umbra 오차를 lit 평균으로 정규화한 지표 추가
  6. 수렴 확인: 그림자맵 해상도·방향 수 2배에서 oracle이 거의 안 변하는지
- **B. 쉬운 수정 후에도 SH 절단이 주 오차인가**: robust radius + 정확한 조명 투영만 적용한 "기본 수정 파이프라인" 행 추가.
- **C. 같은 계수 수에서 wavelet이 SH보다 나은가**: 수정된 visibility를 cube map으로 변환, Haar wavelet nonlinear 근사 vs SH를 계수 16/64/256에서 비교 (근사 오차와 최종 E 오차).
- 결과 끝에 아래 판단 기준에 맞춘 요약 표.

기존 `visibility.npz`는 저해상도로 경계가 뭉개져 wavelet 이점을 과소평가하므로 C의 판단 근거로 쓰지 않는다.

## 5. 판단 기준 (초안, 수치 임계값은 사용자 결정 필요)

- **진행(wavelet)**: B 이후에도 penumbra 오차의 대부분이 SH 절단 **그리고** SH l=9에서도 작은 광원(2~5°) 오차가 큼 **그리고** C에서 같은 계수 수의 wavelet이 확실히 낮음.
- **방향 전환**: 쉬운 수정만으로 충분, 또는 SH l=5~7로 충분, 또는 wavelet이 같은 예산에서 SH보다 낫지 않음.

## 6. 미결정 사항 (사용자 결정 필요)

- A+B+C 일괄 구현 진행 여부
- 판단 기준의 수치 임계값 ("대부분", "크게", "확실히"의 기준, 예: 오차 50% 이상, 2배 차이)
- lego COLMAP 장면의 up 축 (현재 `--light-dirs` 기본값은 축을 모르는 상태에서 고른 3방향)

## 7. 환경 메모

- 대상 GPU: RTX 5080(sm_120, 우선), RTX 4060 Ti(sm_89), RTX 3070(sm_86). 2026-11-02에 환경을 이에 맞게 올렸다.
  - Python 3.10, torch 2.7.1+cu128 / torchvision 0.22.1, base image `nvidia/cuda:12.8.1-devel-ubuntu22.04`. 호스트 드라이버는 570 이상이 필요하다.
  - CUDA 확장은 `pyproject.toml`의 `[tool.uv.extra-build-variables]`로 `TORCH_CUDA_ARCH_LIST="8.6;8.9;12.0"` 고정 빌드한다 (uv 캐시의 wheel을 다른 GPU 머신에서 재사용해도 동작하도록).
  - `simple-knn` submodule은 CUDA 12에서 `FLT_MAX` 미정의 오류가 나서 upstream `86710c2`(`<cfloat>` include)로 올렸다.
  - `numpy<2` 고정: open3d 0.18, scikit-image 0.21이 NumPy 1.x용으로 빌드되어 있다 (그래서 opencv는 4.11).
  - 이전 환경(Python 3.8 + torch 2.0.0+cu118)은 sm_120 커널이 없어 5080에서 어떤 CUDA 연산도 실패했다.
- 검증(2026-11-02, 컨테이너 재빌드 전): NVIDIA redist 아카이브로 CUDA 12.8 툴킷을 임시로 구성하고 `UV_PROJECT_ENVIRONMENT`를 다른 경로로 둔 채 `uv sync`. 확장 3개에 sm_86/89/120 SASS가 포함됨, 5080에서 knn·surfel 렌더·backward 정상, `--self-test` 통과, lego 축소 실행 정상 종료. 3070/4060 Ti 실기기 실행은 아직 확인하지 않았다.
- 컨테이너를 재빌드하기 전에는 `/usr/local/cuda`가 11.8이라 이 컨테이너 안에서 `uv sync`가 확장 빌드에서 실패한다. 재빌드 후 `uv sync`를 실행하면 `.venv`가 3.10으로 다시 만들어진다.
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
