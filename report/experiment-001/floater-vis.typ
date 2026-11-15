// 처음 모델(COLMAP RGB 학습)의 잡티·검은 막 설명 슬라이드. 실험 세팅 실수라 report.typ에는 넣지 않고 기록으로만 둠 (AGENTS.md 3.7).
// 그림: fig/make_shell_figs.py (흰 배경 렌더), fig/make_floater_figs.py (잡티가 만든 가림 지도, 처음 모델).
#import "theme.typ": *

#let data-slide = [
#slide(kicker: "결과 A · 정답 검증 · 5번 문제", title: "처음 쓴 학습 사진은 배경 정보(alpha)가 빠져 있었음")[
  #let cap(body) = block(width: 100%, inset: (top: 0.15em), text(size: 11pt, fill: ink2, body))
  #grid(
    columns: (1fr, 1.25fr, 1fr),
    column-gutter: 0.6cm,
    align: top,
    [
      #image("fig/train_view_white.png", height: 3.7cm)
      #cap[*처음 모델*, 흰 배경 렌더. 화면 전체가 검게 덮임 (*검은 막*).]
    ],
    [
      #align(center, image("fig/floater_cube_with.png", height: 3.7cm))
      #cap[처음 모델, 점 하나의 방향별 가림 (검정 = 가림, 회색 = 표면 뒤). *잡티*가 수평선 근처를 통째로 가림.]
    ],
    [
      #image("fig/train_view_white_rgba.png", height: 3.7cm)
      #cap[원본 RGBA로 *다시 학습*. 물체만 남음.]
    ],
  )
  #v(0.3em)
  #grid(
    columns: (1fr, 1.1fr),
    column-gutter: 0.9cm,
    [
      #set text(size: 12.5pt)
      *원인*: 원본 lego 사진은 배경이 투명(RGBA). 처음에는 COLMAP으로 변환한 사진을 썼는데 여기서 alpha가 빠져 *배경이 검정으로 굳음*.
      - 검은 배경 앞의 검은 Gaussian은 사진과 구분이 안 돼 그대로 학습됨.
      - TranSplat의 alpha 마스크 loss(배경을 투명하게)도 꺼짐.
      #v(0.2em)
      #callout(color: c-aqua)[
        #set text(size: 12pt)
        원본 RGBA + 기본 설정으로 다시 학습. *이후 결과는 모두 다시 학습한 모델 기준.*
      ]
    ],
    [
      #set text(size: 12.5pt)
      #table(
        columns: (1fr, auto, auto),
        align: (left, right, right),
        table.header(text(fill: muted)[], text(fill: muted)[처음 모델], text(fill: muted)[다시 학습]),
        table.hline(stroke: 0.6pt + rule),
        [물체 밖 잡티], [1,907개], [0개],
        [흰 배경 렌더에서 덮인 화면 #note[(사진의 물체 26%)]], [100%], [26%],
        [고도 10° 광원 쪽이 그림자인 점], [100%], [38%],
        [wavelet / SH 오차비 #note[(10°, 계수 256개)]], text(fill: c-orange.darken(10%), weight: "bold")[2.9배], [1.9배],
        table.hline(stroke: 0.6pt + rule),
      )
      #note[잡티가 만든 크고 단순한 가짜 덩어리는 블록으로 그리는 wavelet에 유리 → 처음에는 wavelet이 실제보다 좋아 보였음. 정답 계산을 검증하다 발견.]
    ],
  )
]
]
