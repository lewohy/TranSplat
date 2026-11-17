// 연구미팅: wavelet 적용 전 실험 (고주파 그림자 개선 방향 검토)
// 컴파일: typst compile report.typ  (devcontainer는 TYPST_FONT_PATHS로 Pretendard를 찾는다. 로컬은 아래 목록 순서로 대체)

#import "@preview/cetz:0.4.2"
#import "theme.typ": *
#import "depth-shell.typ": depth-example
#import "sphere-vis.typ": shell, cut-graph
#import "light-vis.typ": disc-angle, sampling-slide, sky-slide, cube-weight-slide

#set page(
  paper: "presentation-16-9",
  margin: (x: 1.6cm, top: 1.3cm, bottom: 1.2cm),
  footer: context {
    let n = counter(page).get().first()
    if n > 1 {
      set text(size: 10pt, fill: muted)
      grid(
        columns: (1fr, auto),
        [연구미팅 · wavelet 적용 전 실험], [#n],
      )
    }
  },
)
#set text(
  font: ("Pretendard", "Noto Sans KR", "Noto Sans CJK KR", "Apple SD Gothic Neo", "Malgun Gothic"),
  size: 15pt,
  fill: ink,
  lang: "ko",
)
#set par(leading: 0.7em)
#set list(spacing: 0.75em, marker: text(fill: c-blue)[•])
#set enum(spacing: 0.75em)
#set table(stroke: none, inset: (x: 0.5em, y: 0.42em))


// ---------------------------------------------------------------------------
// 1. 표지
// ---------------------------------------------------------------------------
#{
  set page(footer: none)
  v(2.2cm)
  text(size: 13pt, fill: c-blue, weight: "semibold")[연구미팅 · 2026-11-02]
  v(0.3em)
  text(size: 38pt, weight: "bold")[wavelet 적용 전 실험]
  v(0.6em)
  text(size: 18pt, fill: ink2)[TranSplat 그림자 개선 방향을 정하기 위한 측정 결과]
  v(0.6cm)
}

// ---------------------------------------------------------------------------
// 2~6. TranSplat 그림자 계산 단계: 개요 → 1단계 bake ①②③ → 2단계 relight ④
// ---------------------------------------------------------------------------
// 단계 그림. 개요와 단계별 슬라이드에서 같이 쓴다.
#let vis-bake = box(width: 6cm, height: 3.2cm, {
  let cx = 2.4cm
  let cy = 1.65cm
  let r = 1.45cm
  place(top + left, dx: cx - r, dy: cy - r, circle(radius: r, stroke: 0.8pt + rule))
  for i in range(70) {
    let z = 1 - 2 * (i + 0.5) / 70
    let rr = calc.sqrt(1 - z * z)
    let phi = i * 2.39996
    let front = rr * calc.sin(phi) > 0
    dotc(
      cx + r * rr * calc.cos(phi),
      cy - r * z,
      r: if front { 0.045cm } else { 0.03cm },
      fill: if front { ink2 } else { c-base.lighten(30%) },
    )
  }
  place(top + left, dx: cx - 0.42cm, dy: cy - 0.18cm, rect(width: 0.84cm, height: 0.45cm, fill: c-base, radius: 2pt))
  place(top + left, dx: cx - 0.2cm, dy: cy - 0.4cm, rect(width: 0.4cm, height: 0.24cm, fill: c-base, radius: 2pt))
  let hx = cx + r * calc.cos(35deg)
  let hy = cy - r * calc.sin(35deg)
  arrow(hx, hy, cx + 0.5cm * calc.cos(35deg), cy - 0.5cm * calc.sin(35deg), paint: c-blue, th: 1.4pt)
  dotc(hx, hy, r: 0.1cm, fill: c-blue)
  seg(hx + 0.12cm, hy, 4.5cm, hy, stroke: (paint: c-blue, thickness: 0.8pt, dash: "dotted"))
  place(top + left, dx: 4.5cm, dy: hy - 0.38cm, rect(
    width: 0.75cm,
    height: 0.75cm,
    fill: gradient.radial(ink.lighten(25%), white, radius: 60%),
    stroke: 0.8pt + c-blue,
  ))
  lbl(4.3cm, hy + 0.5cm, [깊이 이미지], size: 9.5pt, fill: c-blue)
})
#let vis-test = box(width: 6cm, height: 3.2cm, {
  let px = 1.7cm
  let py = 2.8cm
  let wx = 3.2cm
  let wy = 0.8cm
  place(top + left, dx: 0.1cm, dy: py, line(length: 5.6cm, stroke: 1pt + ink2))
  place(top + left, dx: wx, dy: wy, rect(width: 0.6cm, height: py - wy, fill: c-base, radius: (
    top-left: 2pt,
    top-right: 2pt,
  )))
  for k in range(9) {
    let th = 10deg + k * 20deg
    let c = calc.cos(th)
    let s = calc.sin(th)
    let hit = c > 0 and (py - (wx - px) * s / c) >= wy
    if hit {
      let t = (wx - px) / c
      seg(px, py, px + t * c, py - t * s, stroke: (paint: ink, thickness: 1.2pt, dash: "dotted"))
      dotc(px + t * c, py - t * s, r: 0.07cm, fill: ink)
    } else {
      arrow(px, py, px + 1.6cm * c, py - 1.6cm * s, paint: c-blue, th: 1.2pt, head: 0.14cm)
    }
  }
  dotc(px, py, r: 0.1cm, fill: c-orange)
  lbl(px - 0.6cm, py + 0.08cm, [Gaussian], size: 9.5pt, fill: c-orange.darken(10%))
  lbl(wx + 0.7cm, wy + 0.1cm, [가림막], size: 9.5pt)
})
#let vis-sh = box(width: 6cm, height: 3.2cm, {
  let W = 2.2cm
  let H = 1.1cm
  let oy = 0.9cm
  let xa = W * occ-a / (2 * calc.pi)
  let xb = W * occ-b / (2 * calc.pi)
  place(top + left, curve(
    stroke: 1.8pt + ink,
    curve.move((0pt, oy)),
    curve.line((xa, oy)),
    curve.line((xa, oy + H)),
    curve.line((xb, oy + H)),
    curve.line((xb, oy)),
    curve.line((W, oy)),
  ))
  lbl(0cm, oy + H + 0.3cm, [방향별 가림\ (1,200개 값)], size: 9.5pt)
  arrow(2.4cm, oy + H / 2, 3.0cm, oy + H / 2)
  coeff-bars(occ-coeffs, 3.2cm, oy + H / 2, 0.75cm)
  lbl(3.2cm, oy + H + 0.3cm, [숫자 16개 (SH)\ 만 저장], size: 9.5pt, fill: c-orange.darken(15%))
})
#let vis-relight = box(width: 6cm, height: 3.2cm, {
  let oy = 0.8cm
  place(top + left, dx: 0cm, dy: oy, rect(width: 1.5cm, height: 0.95cm, radius: 2pt, fill: gradient.linear(
    rgb("#cfe3f7"),
    rgb("#f4f1e8"),
    angle: 90deg,
  )))
  place(top + left, dx: 0.9cm, dy: oy + 0.15cm, circle(radius: 0.14cm, fill: rgb("#f5b83d")))
  lbl(0cm, oy + 1.2cm, [새 환경맵\ (SH 16개)], size: 9.5pt)
  lbl(1.62cm, oy + 0.18cm, [×], size: 16pt)
  coeff-bars(occ-coeffs.slice(0, 9), 2.1cm, oy + 0.48cm, 0.5cm, bw: 0.11cm, gap: 0.03cm)
  lbl(2.1cm, oy + 1.2cm, [가림\ (SH 16개)], size: 9.5pt, fill: c-orange.darken(15%))
  arrow(3.5cm, oy + 0.48cm, 4.15cm, oy + 0.48cm)
  place(top + left, dx: 4.35cm, dy: oy - 0.12cm, circle(radius: 0.6cm, fill: gradient.radial(
    white,
    ink.lighten(45%),
    center: (30%, 30%),
    radius: 90%,
  )))
  lbl(4.35cm, oy + 1.2cm, [Gaussian의\ 새 밝기], size: 9.5pt)
})

#let mini(n, title, vis, body) = [
  #text(size: 13pt, weight: "bold")[#text(fill: c-blue)[#n] #title]
  #v(0.05em)
  #box(width: 100%, height: 2.8cm, align(center, scale(85%, reflow: true, vis)))
  #set text(size: 11pt, fill: ink2)
  #set par(leading: 0.55em)
  #body
]
#let stage-box(head, sub, color, body) = block(
  width: 100%,
  inset: (x: 0.6em, y: 0.6em),
  radius: 8pt,
  stroke: 1.2pt + color,
  fill: color.lighten(95%),
  [
    #text(size: 15pt, weight: "bold", fill: color.darken(10%), head) #h(0.4em) #text(size: 11.5pt, fill: muted, sub)
    #v(0.3em)
    #body
  ],
)

#slide(kicker: "배경 · 전체 흐름", title: "TranSplat의 그림자 구현 방식")[
  #let arr = align(center, pad(top: 2.2cm, text(size: 16pt, fill: muted)[→]))
  #v(0.2em)
  #grid(
    columns: (3.0fr, auto, 1.1fr),
    column-gutter: 0.25cm,
    stage-box([1단계 · bake], [조명과 무관. 물체마다 미리 한 번], c-blue)[
      #block(
        width: 100%,
        inset: (x: 0.5em, y: 0.5em),
        radius: 6pt,
        stroke: (paint: c-blue.lighten(30%), thickness: 1pt, dash: "dashed"),
      )[
        #text(size: 12pt, weight: "semibold", fill: c-blue)[↻ 방향 1,200개마다 반복 — 방향 하나씩 ① → ② → ③ 하고 다음 방향으로]
        #v(0.3em)
        #grid(
          columns: (1fr, auto, 1fr, auto, 1fr),
          column-gutter: 0.15cm,
          mini("①", "깊이 이미지 렌더", vis-bake)[그 방향 바깥의 카메라로 물체를 한 번 렌더],
          arr,
          mini("②", "Gaussian 가림 판정", vis-test)[깊이 이미지와 비교해 Gaussian마다 그 방향의 가림값(0\~1)],
          arr,
          mini("③", "SH에 누적", vis-sh)[가림값을 Gaussian마다 SH 16칸에 더해 둠],
        )
      ]
      #v(0.15em)
      #text(size: 12.5pt)[반복이 끝나면 → *Gaussian마다 SH 숫자 16개* = "모든 방향의 가림"을 요약해 저장]
    ],
    arr,
    stage-box([2단계 · relight], [\ 조명 바꿀 때마다], c-orange)[
      #v(0.35em)
      #mini("④", "새 조명 적용", vis-relight)[새 환경맵(SH 16개)과 가림(SH 16개)을 곱해 그림자가 들어간 밝기 계산]
    ],
  )
  #v(0.4em)
  #note[렌더링은 ①에서만, 방향당 1번 (총 1,200번). Gaussian 하나하나의 위치에서 렌더하지 않음. 다음 장부터 ①\~④를 한 장씩 설명.]
]

// ---------------------------------------------------------------------------
// 3. ① 깊이 이미지 렌더
// ---------------------------------------------------------------------------
#slide(kicker: "배경 · 1단계 bake (방향 1,200개 반복)", title: "① 방향마다 깊이 이미지 렌더")[
  #flow-nav("①")
  #let vis-cam = box(width: 13.4cm, height: 6.4cm, {
    let r = 1.35cm
    let x0 = 0.6cm
    let cy = 3.1cm
    let cx = x0 + 5 * r
    let t = calc.tan(2 * calc.asin(1 / 5) * 1.2 / 2)
    let hh(x) = (x - x0) * t
    let xn = cx - 1.5 * r
    let xf = cx + 1.5 * r
    place(top + left, curve(
      fill: c-blue.lighten(88%),
      stroke: none,
      curve.move((xn, cy - hh(xn))),
      curve.line((xf, cy - hh(xf))),
      curve.line((xf, cy + hh(xf))),
      curve.line((xn, cy + hh(xn))),
      curve.close(),
    ))
    seg(x0, cy, xf, cy - hh(xf), stroke: (paint: c-blue, thickness: 0.7pt, dash: "dashed"))
    seg(x0, cy, xf, cy + hh(xf), stroke: (paint: c-blue, thickness: 0.7pt, dash: "dashed"))
    seg(xn, cy - hh(xn), xn, cy + hh(xn), stroke: 1.2pt + c-blue)
    seg(xf, cy - hh(xf), xf, cy + hh(xf), stroke: 1.2pt + c-blue)
    place(top + left, dx: cx - r, dy: cy - r, circle(radius: r, stroke: (paint: ink2, thickness: 0.8pt, dash: "dotted")))
    place(top + left, dx: cx - 0.55cm, dy: cy - 0.1cm, rect(width: 1.1cm, height: 0.55cm, fill: c-base, radius: 2pt))
    place(top + left, dx: cx - 0.3cm, dy: cy - 0.4cm, rect(width: 0.55cm, height: 0.3cm, fill: c-base, radius: 2pt))
    dotc(cx, cy, r: 0.05cm, fill: ink)
    seg(cx, cy, cx + r * calc.cos(-50deg), cy + r * calc.sin(-50deg), stroke: 0.9pt + ink2)
    lbl(cx + 0.55cm, cy - 0.9cm, [$r$], size: 12pt)
    cam(x0, cy)
    lbl(x0 - 0.3cm, cy + 0.35cm, [카메라], size: 10pt, fill: c-blue)
    // 거리 5r
    let yb = cy + hh(xf) + 0.35cm
    seg(x0, yb, cx, yb, stroke: 0.7pt + ink2)
    seg(x0, yb - 0.1cm, x0, yb + 0.1cm, stroke: 0.7pt + ink2)
    seg(cx, yb - 0.1cm, cx, yb + 0.1cm, stroke: 0.7pt + ink2)
    lbl((x0 + cx) / 2 - 0.5cm, yb + 0.08cm, [$5r$ (방향 $i$ 쪽)], size: 10.5pt)
    // 기록 범위
    let yt = cy - hh(xf) - 0.25cm
    seg(xn, yt, xf, yt, stroke: 0.7pt + c-blue)
    seg(xn, yt - 0.1cm, xn, yt + 0.1cm, stroke: 0.7pt + c-blue)
    seg(xf, yt - 0.1cm, xf, yt + 0.1cm, stroke: 0.7pt + c-blue)
    lbl(xn - 0.6cm, yt - 0.55cm, [깊이 기록 범위: 중심 $plus.minus 1.5r$], size: 10.5pt, fill: c-blue)
    // 결과 이미지
    arrow(xf + 0.2cm, cy, xf + 0.75cm, cy)
    place(top + left, dx: xf + 0.85cm, dy: cy - 0.8cm, rect(
      width: 1.6cm,
      height: 1.6cm,
      fill: gradient.radial(ink.lighten(25%), white, radius: 60%),
      stroke: 0.8pt + c-blue,
    ))
    lbl(xf + 0.75cm, cy + 0.95cm, [깊이 이미지\ 1024×1024], size: 10pt, fill: c-blue)
  })
  #let vis-alpha = box(width: 13.4cm, height: 2.6cm, {
    let y = 1.0cm
    arrow(0.2cm, y, 9.6cm, y, paint: muted, th: 0.8pt)
    lbl(0.1cm, y + 0.2cm, [픽셀 하나의 시선], size: 9.5pt, fill: muted)
    for (x, w, a) in ((3.0cm, "0.6", 75%), (4.6cm, "0.3", 45%), (7.6cm, "0.1", 20%)) {
      place(top + left, dx: x - 0.22cm, dy: y - 0.55cm, ellipse(width: 0.44cm, height: 1.1cm, fill: c-orange.lighten(100% - a)))
      lbl(x - 0.35cm, y + 0.65cm, [$w = #w$], size: 9.5pt)
    }
    let d = 3.0 * 0.6 + 4.6 * 0.3 + 7.6 * 0.1
    seg(d * 1cm, y - 0.7cm, d * 1cm, y + 0.4cm, stroke: 1.6pt + c-blue)
    lbl(d * 1cm - 0.6cm, y - 1.05cm, [기록되는 깊이], size: 9.5pt, fill: c-blue)
    lbl(10.0cm, y - 0.5cm, [$d = (sum_k w_k z_k) / (sum_k w_k)$], size: 12pt)
  })
  #grid(
    columns: (1.1fr, 1fr),
    column-gutter: 0.9cm,
    [
      #vis-cam
      #v(0.2em)
      #vis-alpha
    ],
    [
      #set text(size: 13pt)
      *카메라 놓기*
      - 방향: 구 위에 고르게 퍼진 1,200개 중 $i$번째
      - 위치: 물체 중심에서 그 방향으로 $5r$, 중심을 바라봄
      - 화각: 반지름 $r$ 구가 꽉 차게 (1.2배 여유)
      *깊이 이미지에 적히는 값*
      - 픽셀마다 그 시선에 걸린 Gaussian들의 깊이를 *alpha로 가중평균* \
        #note[$w_k$: Gaussian $k$의 불투명도 × 앞쪽에서 남은 투과율. 맨 앞 하나가 아니라 섞인 값.]
      - 중심 $plus.minus 1.5r$ 밖은 기록 안 됨
      #v(0.2em)
      #callout(color: c-orange)[
        #set text(size: 12pt)
        $r$ = 1.8 × (중심에서 가장 먼 Gaussian까지 거리). \
        lego는 $r = 2.53$ (물체 대부분은 1.57 안에 있음). \
        → 그림자맵이 약 1.6배 거칠어짐 (#plink("result-a")[결과 A]).
      ]
    ],
  )
]

// ①의 실제 예시 (depth-shell.typ)
#depth-example

// ---------------------------------------------------------------------------
// 4. ② Gaussian 가림 판정
// ---------------------------------------------------------------------------
#slide(kicker: "배경 · 1단계 bake (방향 1,200개 반복)", title: "② 각 Gaussian의 가림 판정 (렌더 없이 계산만)")[
  #flow-nav("②")
  #let vis-depth = box(width: 13.4cm, height: 4.3cm, {
    let y = 1.7cm
    cam(0.5cm, y)
    lbl(0.1cm, y + 0.35cm, [①의 카메라], size: 9.5pt, fill: c-blue)
    place(top + left, dx: 4.6cm, dy: 0.3cm, rect(width: 0.7cm, height: 1.75cm, fill: c-base, radius: 2pt))
    lbl(3.7cm, 0.0cm, [앞쪽 표면 (가림체)], size: 9.5pt)
    place(top + left, dx: 10.0cm, dy: 0.5cm, rect(width: 0.35cm, height: 1.75cm, fill: c-base.lighten(40%), radius: 2pt))
    seg(1.0cm, y, 4.6cm, y, stroke: (paint: c-blue, thickness: 1pt, dash: "dotted"))
    seg(5.3cm, y, 9.85cm, y, stroke: (paint: muted, thickness: 1pt, dash: "dotted"))
    dotc(9.85cm, y, r: 0.13cm, fill: c-orange)
    lbl(9.2cm, 0.05cm, [Gaussian], size: 9.5pt, fill: c-orange.darken(10%))
    let ya = 3.45cm
    arrow(0.5cm, ya, 12.6cm, ya, paint: ink2, th: 0.8pt)
    lbl(12.0cm, ya + 0.15cm, [깊이], size: 9.5pt, fill: muted)
    seg(4.6cm, ya - 0.12cm, 4.6cm, ya + 0.12cm, stroke: 1.2pt + c-blue)
    lbl(4.1cm, ya + 0.2cm, [$d$ (깊이 이미지 값)], size: 10pt, fill: c-blue)
    seg(9.85cm, ya - 0.12cm, 9.85cm, ya + 0.12cm, stroke: 1.2pt + c-orange)
    lbl(9.2cm, ya + 0.2cm, [$z$ (Gaussian 깊이)], size: 10pt, fill: c-orange.darken(10%))
    place(top + left, dx: 4.6cm, dy: y + 0.35cm, rect(width: 0.6cm, height: 0.14cm, fill: muted))
    lbl(4.45cm, y + 0.5cm, [bias], size: 9pt, fill: muted)
    place(top + left, dx: 5.2cm, dy: y + 0.35cm, rect(width: 4.65cm, height: 0.14cm, fill: c-orange.lighten(30%)))
    lbl(6.4cm, y + 0.5cm, [관통 깊이 $p$], size: 10pt, fill: c-orange.darken(10%))
  })
  #let vis-pcf = box(width: 13.4cm, height: 4.6cm, {
    let px = 0.56cm
    let ox = 0.3cm
    let oy = 0.35cm
    let n = 7
    for i in range(n) {
      for j in range(n) {
        place(top + left, dx: ox + i * px, dy: oy + j * px, rect(
          width: px,
          height: px,
          fill: if i <= 3 { c-base.lighten(35%) } else { white },
          stroke: 0.4pt + rule,
        ))
      }
    }
    let cx = ox + 3.5 * px
    let cy = oy + 3.5 * px
    let offs = (
      (-0.942, -0.399),
      (0.946, -0.769),
      (-0.094, -0.929),
      (0.345, 0.294),
      (-0.916, 0.458),
      (-0.815, -0.879),
      (-0.383, 0.277),
      (0.975, 0.756),
    )
    for (u, v) in offs {
      let sx = 3.5 + 1.5 * u
      let hit = sx < 4.0
      dotc(cx + 1.5 * u * px, cy + 1.5 * v * px, r: 0.1cm, fill: if hit { ink } else { c-blue })
    }
    cross(cx, cy, s: 0.1cm, stroke: 1.4pt + c-orange)
    lbl(ox, oy + n * px + 0.1cm, [깊이 이미지 픽셀 (회색: 가림체가 찍힌 곳)], size: 9.5pt, fill: muted)
    let tx = ox + n * px + 0.6cm
    cross(tx + 0.12cm, 0.5cm, s: 0.09cm, stroke: 1.4pt + c-orange)
    lbl(tx + 0.35cm, 0.3cm, [Gaussian 중심이 떨어진 위치], size: 10.5pt)
    lbl(tx, 0.85cm, [#text(fill: ink)[●] 가림체 위 5곳: $e^(-0.58 times 0.47) = 0.76$], size: 10.5pt)
    lbl(tx, 1.4cm, [#text(fill: c-blue)[●] 가림체 밖 3곳: 관통 0 → $1$], size: 10.5pt)
    lbl(tx, 2.2cm, [평균 $= (5 times 0.76 + 3 times 1) / 8 = bold(0.85)$], size: 12pt)
    lbl(tx, 2.95cm, [→ 이 방향에서 이 Gaussian의 가림값], size: 10.5pt, fill: ink2)
  })
  #grid(
    columns: (1.1fr, 1fr),
    column-gutter: 0.9cm,
    [
      #vis-depth
      #vis-pcf
    ],
    [
      #set text(size: 12.5pt)
      Gaussian 85만 개를 *동시에* 계산 (행렬 곱 + 이미지 조회)
      + 중심 좌표를 ①의 카메라 좌표로 변환 \
        → 깊이 $z$, 깊이 이미지 위 위치
      + 그 위치 주변 8곳(반경 1.5픽셀)에서 $d$를 읽음
      + 곳마다 \
        관통 깊이 $p = max(0, z - d - "bias")$ \
        ESM $= e^(-alpha p)$ #note[1: 보임, 0에 가까울수록 가려짐]
      + 8곳 ESM 값의 평균 (PCF) = *이 방향의 가림값*
      #note[$alpha = 8 \/ r$ (lego 0.58), bias = 3 × Gaussian의 가장 긴 축. 예시는 가림체가 0.5 앞, bias 0.03.]
      #v(0.1em)
      #callout[
        #set text(size: 11.5pt)
        깊이를 평균내지 않고 *판정 결과를 평균* → 가림체 경계 ±1.5픽셀에서 0 → 1로 서서히 바뀜 (그림자 경계가 부드러워짐). 폭은 광원 크기와 무관하게 고정.
      ]
    ],
  )
]

// ---------------------------------------------------------------------------
// 5. ③ SH 누적
// ---------------------------------------------------------------------------
#slide(kicker: "배경 · 1단계 bake (방향 1,200개 반복)", title: "③ 가림값을 SH 16칸에 누적")[
  #flow-nav("③")
  #let basis = range(16).map(k => calc.sin(k * 1.7 + 0.6) * (1 - k / 24))
  #let acc = range(16).map(k => calc.cos(k * 0.9 + 0.3) * (1 - k / 20))
  #let bars16(cs, color: c-orange) = box(width: 2.9cm, height: 1.3cm, coeff-bars(cs, 0cm, 0.65cm, 0.6cm, color: color))
  #let cell(body) = align(center + horizon, body)
  #let row-title(body) = text(size: 13pt, weight: "bold", body)
  #grid(
    columns: (1.15fr, 1fr),
    column-gutter: 0.9cm,
    [
      #row-title[반복 $i$번째 · Gaussian 하나 기준]
      #v(0.2em)
      #grid(
        columns: (auto, auto, auto, auto, auto),
        column-gutter: 0.35cm,
        row-gutter: 0.2cm,
        cell(text(size: 20pt, weight: "bold", fill: c-orange)[0.85]),
        cell(text(size: 16pt)[×]),
        cell(bars16(basis, color: c-blue)),
        cell(text(size: 16pt)[→ +=]),
        cell(bars16(acc)),
        cell(note[②의 가림값]), [], cell(note[방향 $i$의 SH 기저값 16개]), [], cell(note[누적 16칸 (덧셈)]),
      )
      #v(0.5em)
      #row-title[1,200번 끝난 뒤 · 한 번]
      #v(0.2em)
      #grid(
        columns: (auto, auto, auto, auto, auto),
        column-gutter: 0.35cm,
        row-gutter: 0.2cm,
        cell(bars16(acc)),
        cell(text(size: 16pt)[×]),
        cell(box(width: 1.3cm, height: 1.3cm, stroke: 0.8pt + ink2, radius: 2pt, align(
          center + horizon,
          text(size: 10pt)[16×16],
        ))),
        cell(text(size: 16pt)[→]),
        cell(bars16(occ-coeffs)),
        cell(note[누적 16칸]), [], cell(note[보정 행렬]), [], cell(note[*SH 계수 16개 저장*]),
      )
    ],
    [
      #set text(size: 12.5pt)
      - Gaussian마다 *16칸짜리 통 하나*에 계속 더함. 가림값은 더한 뒤 버림.
      - 메모리: 85만 × 16칸 × 4바이트 ≈ *54 MB*. 반복해도 늘지 않음 \
        #note[(1,200개 값을 다 모아 두면 ≈ 4.1 GB)]
      - 보정 행렬은 방향 배치로만 정해짐 (방향이 구 위에 완전히 고르지 않은 것 보정). 모든 Gaussian 공통이라 마지막에 한 번 곱함.
      - 결과: 1,200방향의 가림 패턴을 SH 기저 16개의 합으로 가장 비슷하게 맞춘 것 (최소제곱).
      #v(0.2em)
      #callout(color: c-orange)[
        #set text(size: 12pt)
        16개 숫자로는 "보임 ↔ 가려짐"이 급하게 바뀌는 경계를 못 담음 → *날카로운 그림자가 뭉개지는 곳* (뒤의 "문제" 장).
      ]
    ],
  )
]

// ---------------------------------------------------------------------------
// 6. ④ 새 조명 적용
// ---------------------------------------------------------------------------
#slide(kicker: "배경 · 2단계 relight (조명 바꿀 때마다)", title: "④ 새 조명 적용")[
  #flow-nav("④")
  #grid(
    columns: (1fr, 1.15fr),
    column-gutter: 0.9cm,
    [
      #v(0.4em)
      #align(center, scale(140%, reflow: true, vis-relight))
      #v(0.6em)
      #callout(color: c-aqua)[
        #set text(size: 12.5pt)
        조명이 바뀌면 *여기만* 다시 계산. ①\~③의 SH 16개는 그대로 재사용 → 빠름.
      ]
      #v(0.2em)
      #note[specular(반사, 나머지 SH 색)도 "가려진 새 조명"을 반사 방향에서 읽어 변환하므로 가림이 들어감. 다만 촬영 조명 쪽은 가림 없이 나눔.]
    ],
    [
      #set text(size: 13pt)
      + *환경맵 → SH 16개* \
        새 조명(target)과 촬영 때 조명(source) 둘 다. \
        #note[1,200방향에서 가장 가까운 픽셀 하나씩 읽어 요약.]
      + *가려진 조명 = 조명 × 가림* \
        Gaussian마다 조명 SH 16개와 ③의 가림 SH 16개를 곱함. \
        #note[SH끼리 곱하는 공식(Gaunt 계수) 사용, 결과도 16개로 자름.]
      + *밝기 $E$* \
        가려진 조명을 Gaussian 표면 방향(normal) 쪽 반구에서 cosine으로 적분.
      + *색 바꾸기* \
        $c_"new" = c_"old" times E_"target" / E_"source"$ #note[(최대 3배)] \
        #note[Gaussian 색에는 촬영 때 조명·그림자가 이미 들어 있음 → 원래 밝기로 나누고 새 밝기를 곱함.]
    ],
  )
]

// ---------------------------------------------------------------------------
// 3. 문제
// ---------------------------------------------------------------------------
#slide(kicker: "배경", title: "문제: 작고 강한 광원의 그림자가 흐려짐")[
  #grid(
    columns: (1fr, 1.1fr),
    column-gutter: 1.0cm,
    [
      #callout(color: c-orange)[
        태양이나 스포트라이트처럼 *작고 강한 광원*의 그림자가 흐리고 옅어짐.
      ]
      #v(0.1em)
      #grid(
        columns: (1fr, 1fr),
        column-gutter: 0.3cm,
        align(center, shell("judge", [② 판정값 (ESM+PCF)], len: 1.55cm)),
        align(center, shell("sh16", text(fill: c-orange.darken(10%))[③ SH 16개로 복원], len: 1.55cm)),
      )
      #v(0.2em)
      #set text(size: 12.5pt)
      - 구 중심 = Gaussian 하나, 구 표면의 점 = 빛이 들어올 수 있는 쪽. 1/8만 껍질로 그림: *안으로 들어가고 어두울수록 가려짐*.
      - SH 16개는 구불구불한 가림 경계를 담지 못해 *넓고 옅은 얼룩*으로 퍼뜨림.
      #note[합성 예시: 지름 약 40°의 가림막, 경계 폭 3°. SH는 구 전체로 계산.]
    ],
    [
      #text(size: 13pt, fill: ink2)[#text(fill: c-blue)[*파란 선*]을 따라 읽은 값 (1 = 빛이 들어옴, 0 = 가려짐)]
      #v(0.5em)
      #pad(left: 0.5cm, cut-graph(13.4cm, 4.4cm))
      #legend((
        (name: "② 판정값 (점 = 방향마다 계산한 값)", color: ink),
        (name: "③ SH 16개로 복원", color: c-orange),
      ))
      #v(0.3em)
      #set text(size: 12.5pt)
      광원이 넓으면 넓은 범위를 평균해서 티가 덜 남. *작은 광원이 경계 근처*에 있으면 실제로는 밝아야 할 곳이 어둡게 (또는 반대로) 계산됨 → 그림자가 흐려지고 엉뚱한 곳이 어두워짐.
    ],
  )
]

// ---------------------------------------------------------------------------
// 4. 실험 대상
// ---------------------------------------------------------------------------
#slide(kicker: "질문", id: "question", title: "이번 실험 대상")[
  압축 방식을 SH 대신 *wavelet*으로 바꾸기. wavelet은 신호를 크기가 다른 블록 조각으로 나눠, 중요한 조각만 골라 저장. \
  -> 경계처럼 급한 변화에 적절할 수 있음.

  #v(0.5em)
  #grid(
    columns: (1fr, 1fr, 1fr),
    column-gutter: 0.8cm,
    callout[
      #tagl("result-a")[A] *정확한 GT 필요*
      #v(0.2em)
      #note[
        - 오차를 재려면 "압축하지 않은 정답"이 필요
        - 이 정답 계산 자체가 맞는지부터 확인 해야 함.
      ]
      #align(right, text(size: 11pt)[→ 결과 #pref("result-a")])
    ],
    callout[
      #tagl("result-b")[B] *압축이 주 원인인지 확인*
      #v(0.2em)
      #note[
        - 현재 코드에는 다른 오차 원인도 존재
        - 고친 뒤에도 남는 오차가 대부분 "16개로 요약"에서 오는지 확인 필요
      ]
      #align(right, text(size: 11pt)[→ 결과 #pref("result-b")])
    ],
    callout[
      #tagl("result-c")[C] *wavelet로 개선 가능한지*
      #v(0.2em)
      #note[
        - 같은 저장 공간을 줬을 때 wavelet의 오차가 SH보다 충분히 작은지.
        - 사용하는 메모리가 허용 범위 안에 있는지.
      ]
      #align(right, text(size: 11pt)[→ 결과 #pref("result-c")])
    ],
  )
  #v(0.7em)
  #[
    *판단 규칙*
    - B와 C 둘 다 "확인됨" → wavelet으로 진행
    - 하나라도 "기각됨" → 방향 전환
  ]
]

// ---------------------------------------------------------------------------
// 5. 실험 설계: 조건
// ---------------------------------------------------------------------------
#slide(kicker: "방법 · 실험 조건", id: "conditions", title: "실험 설계: 한 번에 한 요소만 바꿔서 비교")[
  #grid(
    columns: (1.5fr, 1fr),
    column-gutter: 0.8cm,
    [
      #table(
        columns: (auto, 1fr),
        align: (center, left),
        table.hline(stroke: 0.6pt + rule),
        text(fill: muted)[장면], [lego (Gaussian 85만 개)],
        table.hline(stroke: 0.6pt + rule),
        text(fill: muted)[평가점], [겉면 점 2만 개 #note[(고르는 과정은 #pref("eval-points"))]],
        table.hline(stroke: 0.6pt + rule),
        text(fill: muted)[조명],
        [균일한 하늘 + 원판 광원 1개. 크기 2°, 5°, 10°, 30° × 방향 3개 (고도 60°, 30°, 10°)\ #note[(참고: 하늘의 태양은 약 0.5°)]],
        table.hline(stroke: 0.6pt + rule),
        text(fill: muted)[정답], [*+4 정답*: 압축 없이 직접 계산 (#pref("sampling")) \ #note[계산 문제 1\~4번(#pref("result-a"))을 모두 고친 것. 안 고친 것은 +0]],
        table.hline(stroke: 0.6pt + rule),
        text(fill: muted)[비교],
        [+4 정답에서 한 요소만 변경
          → 그 요소가 만드는 오차만 분리],
        table.hline(stroke: 0.6pt + rule),
      )
      #v(0.3em)
      #image("r_10.png", height: 3.6cm)
    ],
    [
      #v(0.8em)
      #align(center, disc-angle)
      #v(0.4em)
      #set text(size: 12.5pt)
      - 광원 크기 = 점에서 원판 양 끝으로 그은 두 선 사이의 각 (*보이는 크기*). 스포트라이트가 빛을 퍼뜨리는 각이 아님.
      - 광원은 아주 멀리 있어서 어느 점에서 봐도 같은 크기.
      #note[그림은 과장 (약 15°). 고도는 위쪽 방향(장면 up 축) 기준.]
    ],
  )
]

// 평가점 고르기
#slide(kicker: "방법 · 실험 조건", id: "eval-points", title: "평가할 점 2만 개를 고르는 과정")[
  #let steps = (
    (850109, [학습된 Gaussian 전체], []),
    (514491, [불투명도 0.5 초과], [반투명한 Gaussian은 그림자를 거의 안 만들고 표면 위치도 불분명]),
    (511918, [물체 범위 안], [중심에서 1.43 이내 (불투명한 점의 99.5%가 들어가는 거리). 멀리 떨어진 잡티 제외]),
    (415504, [학습 카메라 2대 이상에서 보임], [카메라 이미지에서 그 픽셀에 렌더된 표면과 깊이 차이 3픽셀 이내]),
    (283516, [렌더된 표면에 붙어 있음], [가장 가까운 카메라에서 0.5픽셀 이내. 표면 아래 층 제외 (#plink("result-a")[결과 A] 3번)]),
    (20000, [무작위로 2만 개], [계산량 때문 (점마다 방향 2.5만 개 판정). 시드 고정]),
  )
  #let fmt-n(n) = {
    let s = str(n)
    let out = ""
    for (i, ch) in s.clusters().enumerate() {
      if i > 0 and calc.rem(s.len() - i, 3) == 0 { out += "," }
      out += ch
    }
    out
  }
  #grid(
    columns: (1.75fr, 1fr),
    column-gutter: 0.7cm,
    [
      #grid(
        columns: (1.9cm, 1fr, 2.4cm),
        column-gutter: 0.35cm,
        row-gutter: 0.5em,
        ..steps.enumerate().map(((i, (n, name, why))) => {
          let last = i == steps.len() - 1
          (
            align(right + top, text(size: 13pt, weight: "bold", fill: if last { c-blue } else { ink })[#fmt-n(n)]),
            [
              #if i > 0 [#tag[#i] ]#text(size: 12.5pt, weight: "semibold")[#name]
              #if why != [] { linebreak(); text(size: 10.5pt, fill: ink2, why) }
            ],
            pad(top: 0.2em, box(width: 2.4cm * n / 850109 + 0.06cm, height: 0.3cm, fill: if last { c-blue } else { c-base }, radius: 1pt)),
          )
        }).flatten(),
      )
    ],
    [
      #v(0.4em)
      #align(center, cetz.canvas(length: 0.85cm, {
        import cetz.draw: *
        // 물체 단면: 위쪽 선이 렌더된 표면
        rect((0, -2.2), (6.2, 0), fill: c-lego.lighten(70%), stroke: none)
        line((0, 0), (6.2, 0), stroke: 2pt + c-lego.darken(25%))
        content((6.25, 0.0), anchor: "west", text(size: 9.5pt, fill: ink2)[렌더된\ 표면])
        // 카메라 두 대
        for (cx, cy) in ((0.6, 3.0), (5.4, 3.2)) {
          rect((cx - 0.28, cy - 0.18), (cx + 0.28, cy + 0.18), fill: c-blue, stroke: none, radius: 2pt)
        }
        content((0.6, 3.5), text(size: 9.5pt, fill: c-blue)[카메라])
        let pts = (
          ((2.6, 0.0), c-aqua, "a"),
          ((3.9, -0.32), c-orange, "b"),
          ((2.0, -1.4), muted, "c"),
        )
        for (p, col, _) in pts {
          line((0.6, 3.0), p, stroke: (paint: col, thickness: 0.7pt, dash: "dashed"))
          line((5.4, 3.2), p, stroke: (paint: col, thickness: 0.7pt, dash: "dashed"))
        }
        for (p, col, _) in pts { circle(p, radius: 0.13, fill: col, stroke: 0.6pt + white) }
        content((2.6, 0.45), text(size: 10pt, fill: c-aqua.darken(25%), weight: "bold")[남김])
        content((4.15, -0.75), anchor: "west", text(size: 10pt, fill: c-orange.darken(15%))[살짝 아래: 필터 4에서 제외])
        content((2.0, -1.85), text(size: 10pt, fill: muted)[깊이 묻힘: 필터 3에서 제외])
      }))
      #v(0.3em)
      #set text(size: 12pt)
      - 픽셀 차이 = 점과 렌더된 표면의 *깊이 차이를 그 거리에서의 픽셀 크기로* 잰 값.
      - 걸러진 점은 렌더 화면에 직접 보이지 않는 점 → relight 결과에도 안 보임.
      #note[한계: 바깥 면이라도 학습 카메라에서 안 보이는 틈 안쪽은 빠짐.]
    ],
  )
]

// 정답 계산의 방향 샘플 (light-vis.typ)
#sampling-slide


// ---------------------------------------------------------------------------
// 6. 실험 설계: 지표와 비교 대상
// ---------------------------------------------------------------------------
#slide(kicker: "방법 · 지표와 비교 대상", title: "실험 설계: 무엇을 재고, 무엇과 비교했나")[
  #let vis-metric = box(width: 15.5cm, height: 5.0cm, {
    let W = 14.5cm
    let H = 3.6cm
    let ox = 0.6cm
    let oy = 0.9cm
    let x0 = 0.42
    let x1 = 0.58
    let ss(x, a, b) = {
      let t = calc.clamp((x - a) / (b - a), 0, 1)
      1 - t * t * (3 - 2 * t)
    }
    let E(x) = 0.25 + 0.75 * ss(x, x0, x1)
    let Es(x) = 0.27 + 0.68 * ss(x, 0.3, 0.74)
    let X(x) = ox + W * x
    let Y(v) = oy + H * (1.05 - v)
    place(top + left, dx: X(x0), dy: oy - 0.15cm, rect(
      width: W * (x1 - x0),
      height: H + 0.15cm,
      fill: c-orange.lighten(88%),
    ))
    for i in range(0, 41) {
      let x = x0 + (x1 - x0) * i / 40
      seg(X(x), Y(E(x)), X(x), Y(Es(x)), stroke: 1pt + c-orange.lighten(20%))
    }
    let xs = range(0, 201).map(i => i / 200)
    place(top + left, curve(
      stroke: 2.6pt + ink,
      curve.move((X(0), Y(E(0)))),
      ..xs.slice(1).map(x => curve.line((X(x), Y(E(x))))),
    ))
    place(top + left, curve(
      stroke: 2.2pt + c-blue,
      curve.move((X(0), Y(Es(0)))),
      ..xs.slice(1).map(x => curve.line((X(x), Y(Es(x))))),
    ))
    place(top + left, dx: ox, dy: Y(1.0), line(length: W * x0, stroke: (paint: ink2, thickness: 0.9pt, dash: "dashed")))
    lbl(X(0.01), Y(1.0) - 0.5cm, [밝은 곳 평균 밝기 (나누는 값)], size: 10.5pt)
    lbl(X(0.12), oy - 0.75cm, [밝은 곳], size: 11.5pt, fill: muted)
    lbl(X(x0) - 0.25cm, oy - 0.75cm, [반그림자 (여기서 잼)], size: 11.5pt, fill: c-orange.darken(15%))
    lbl(X(0.8), oy - 0.75cm, [그림자], size: 11.5pt, fill: muted)
    lbl(X(x1) + 0.15cm, Y(0.62), [|추정 − +4 정답|], size: 11pt, fill: c-orange.darken(15%))
    place(top + left, dx: ox, dy: oy + H, line(length: W, stroke: 0.8pt + ink2))
    lbl(ox, oy + H + 0.15cm, [표면 위의 위치 → (그림자 경계를 가로지름)], size: 10.5pt, fill: muted)
  })
  #grid(
    columns: (1.3fr, 1fr),
    column-gutter: 1cm,
    [
      *지표: 그림자 경계 오차*
      #v(0.1em)
      #legend(((name: "+4 정답", color: ink), (name: "추정", color: c-blue)))
      #scale(85%, reflow: true, origin: top + left, vis-metric)
      #[
        #set text(size: 12pt)
        $ "오차" = (limits("평균")_(i in P) abs(E_i - E_i^"+4 정답")) / (limits("평균")_(i in L) E_i^"+4 정답") $
        #note[$E_i$: 점 $i$의 밝기 · $P$: 반그림자 점 (원판 64방향 중 2\~62개 보임) · $L$: 밝은 곳 점 (63개 이상). 예) 0.2 = 경계에서 밝은 곳 밝기의 20%만큼 틀림. 작을수록 좋음.]
      ]
    ],
    [
      *비교 대상: 아래 5가지를 각각 계산해 +4 정답과 비교*
      #v(0.2em)
      #set text(size: 12pt)
      #table(
        columns: (auto, 1fr, auto),
        align: (left + horizon, left + horizon, center + horizon),
        inset: (x: 0.4em, y: 0.5em),
        table.hline(stroke: 0.6pt + rule),
        text(fill: muted)[계산한 것], text(fill: muted)[알고 싶은 것], text(fill: muted)[질문],
        table.hline(stroke: 0.6pt + rule),
        [① TranSplat], [지금 얼마나 틀리나], tagl("question")[B],
        table.hline(stroke: 0.3pt + rule),
        [② ① + SBF], [수정만으로 얼마나 개선되는지], tagl("question")[B],
        table.hline(stroke: 0.3pt + rule),
        [③ +4 정답 + SH 압축만\ #note[(계수 16 / 100 / 256개)]], [SH 압축 오차], [#tagl("question")[B] #tagl("question")[C]],
        table.hline(stroke: 0.3pt + rule),
        [④ +4 정답 + wavelet 압축만\ #note[(계수 8 → 256개)]], [같은 메모리면\ ③보다 나은가], tagl("question")[C],
        table.hline(stroke: 0.3pt + rule),
        [⑤ 광원만 그림자맵으로], [대안이 될까], tagl("alt", color: c-aqua)[대안],
        table.hline(stroke: 0.6pt + rule),
      )
      #note[SBF (SH-preserving Basic Fixes): SH 16개는 그대로 두고 압축 외의 기본 오류만 고친 것. \ ③ ④는 +4 정답에서 압축 하나만 넣은 것 → 늘어난 오차가 곧 압축 탓.]
    ],
  )
]

// ---------------------------------------------------------------------------
// 7. A: 정답 계산의 문제들
// ---------------------------------------------------------------------------
#slide(kicker: "결과 A · 정답 검증", id: "result-a", q: "A", title: "새로운 문제: 정답 계산도 어려움")[
  #let VW = 9cm
  #let VH = 2.0cm
  #let card(n, title, vis, prob, fix) = block(
    width: 100%,
    height: 5.3cm,
    breakable: false,
    inset: (x: 0.6em, y: 0.5em),
    radius: 6pt,
    stroke: 0.8pt + rule,
    {
      text(size: 13pt, weight: "bold")[#tag[#n] #title]
      v(0.1em)
      scale(85%, origin: top + left, reflow: true, box(width: VW, height: VH, clip: true, vis))
      v(0.1em)
      set text(size: 10.5pt)
      set par(leading: 0.55em)
      grid(
        columns: (auto, 1fr),
        column-gutter: 0.5em,
        row-gutter: 0.45em,
        text(fill: c-orange.darken(10%), weight: "semibold")[문제], prob,
        text(fill: c-aqua.darken(20%), weight: "semibold")[수정], fix,
      )
    },
  )
  #let v1 = {
    let cx = 1.3cm
    let cy = 1.05cm
    place(top + left, dx: cx - 0.96cm, dy: cy - 0.96cm, circle(radius: 0.96cm, stroke: (
      paint: c-orange,
      thickness: 1.2pt,
      dash: "dashed",
    )))
    place(top + left, dx: cx - 0.6cm, dy: cy - 0.6cm, circle(radius: 0.6cm, stroke: 1.2pt + c-blue))
    place(top + left, dx: cx - 0.45cm, dy: cy - 0.1cm, rect(width: 0.9cm, height: 0.45cm, fill: c-base, radius: 2pt))
    place(top + left, dx: cx - 0.2cm, dy: cy - 0.35cm, rect(width: 0.4cm, height: 0.26cm, fill: c-base, radius: 2pt))
    lbl(2.5cm, 1.2cm, [물체 범위 1.57], fill: c-blue)
    lbl(2.5cm, 0.2cm, [가장 먼 점 × 1.8 = 2.53], fill: c-orange.darken(10%))
  }
  #let v2 = {
    let sy = 1.15cm
    place(top + left, curve(
      stroke: 1.4pt + ink2,
      curve.move((0.3cm, sy)),
      ..range(1, 31).map(i => curve.line((0.3cm + i * 0.21cm, sy + 0.08cm * calc.sin(i * 0.9)))),
    ))
    let flips = (false, true, true, false, true, false, false)
    for (i, f) in flips.enumerate() {
      let x = 0.8cm + i * 0.85cm
      if f { arrow(x, sy, x, sy + 0.75cm, paint: c-orange, th: 1.3pt, head: 0.14cm) } else {
        arrow(x, sy, x, sy - 0.75cm, paint: c-blue, th: 1.3pt, head: 0.14cm)
      }
    }
    cam(7.6cm, 0.35cm, color: ink2)
    lbl(7.1cm, 0.65cm, [학습 카메라], size: 9.5pt)
    lbl(7.0cm, 1.35cm, [뒤집힌 방향], size: 9.5pt, fill: c-orange.darken(10%))
  }
  #let v3 = {
    for k in range(14) {
      dotc(0.6cm + k * 0.42cm, 0.75cm, r: 0.09cm, fill: c-blue)
      dotc(0.8cm + k * 0.42cm, 1.2cm, r: 0.08cm, fill: c-base)
      if k < 13 { dotc(0.6cm + k * 0.42cm, 1.65cm, r: 0.08cm, fill: c-base) }
    }
    lbl(6.1cm, 0.5cm, [겉면 → 평가], size: 9.5pt, fill: c-blue)
    lbl(6.1cm, 1.3cm, [속 점 → 제외], size: 9.5pt)
  }
  #let v4 = {
    let discs = ((0.4, 1.55), (2.1, 1.65), (3.8, 1.42), (5.5, 1.6))
    for (x, y) in discs {
      place(top + left, dx: x * 1cm, dy: y * 1cm - 0.17cm, ellipse(
        width: 2.1cm,
        height: 0.34cm,
        fill: c-base.lighten(40%),
        stroke: 0.6pt + c-base,
      ))
    }
    let t = calc.tan(12deg)
    seg(3.15cm, 1.65cm, 4.1cm, 1.65cm - 0.95cm * t, stroke: 1.2pt + c-orange)
    dotc(3.15cm, 1.65cm, r: 0.08cm, fill: c-orange)
    cross(4.1cm, 1.65cm - 0.95cm * t)
    seg(3.15cm, 1.65cm, 3.15cm, 1.15cm, stroke: (paint: c-blue, thickness: 0.8pt, dash: "dashed"))
    arrow(3.15cm, 1.15cm, 7.8cm, 1.15cm - 4.65cm * t, paint: c-blue, th: 1.2pt, head: 0.14cm)
    dotc(3.15cm, 1.15cm, r: 0.08cm, fill: c-blue)
    place(top + left, dx: 8.0cm, dy: 0.05cm, circle(radius: 0.16cm, fill: rgb("#f5b83d")))
    lbl(0.4cm, 0.35cm, [이웃 Gaussian에 걸림], size: 9.5pt, fill: c-orange.darken(10%))
  }
  #grid(
    columns: (1fr, 1fr, 1fr),
    column-gutter: 0.5cm,
    row-gutter: 0.3cm,
    card(
      "1",
      "장면 크기를 너무 크게 잡음",
      v1,
      [가장 먼 점 거리 × 1.8로 반지름 2.53 (물체는 1.57) → 그림자맵이 약 1.6배 거칠어짐.],
      [물체 점 99.5% 범위 × 1.1로 계산],
    ),
    card(
      "2",
      "표면 앞/뒤가 뒤집힘",
      v2,
      [표면 방향(normal)의 부호가 임의라 약 49%가 안쪽을 향함 → 빛을 반대쪽에서 받음.],
      [학습 카메라들이 본 쪽을 앞으로 (투표)],
    ),
    card(
      "3",
      "표면 아래 점까지 평가",
      v3,
      [겉면 아래 겹겹이 쌓인 Gaussian은 원래 하늘이 안 보여 평균을 왜곡.],
      [카메라 2대 이상에 보이는 겉면 점만 평가],
    ),

    card(
      "4",
      "자기 그림자 착각",
      v4,
      [겹친 납작한 Gaussian끼리 서로 가린다고 판정 → 얼룩 그림자.],
      [판정할 때 점을 표면 방향으로 살짝 띄움 (#pref("judge"))],
    ),
    grid.cell(colspan: 2, block(
      width: 100%,
      height: 5.3cm,
      breakable: false,
      inset: (x: 0.7em, y: 0.6em),
      radius: 6pt,
      fill: c-aqua.lighten(90%),
      stroke: 1.2pt + c-aqua,
      {
        text(size: 13pt, weight: "bold")[원래 TranSplat 코드에도 이 문제가 있나?]
        v(0.3em)
        set text(size: 12pt)
        set par(leading: 0.55em)
        table(
          columns: (auto, 1fr),
          inset: (x: 0.4em, y: 0.3em),
          align: (left + top, left + top),
          tag[1], [*문제 있음.* 장면 크기 = 1.8 × 가장 먼 점 거리 (그림자맵이 1.6배 거칠어짐)],
          tag[2], [*문제 있음.* normal 부호를 보정하지 않음],
          tag[3], [해당 없음. 평가할 점을 고르는 문제 (렌더와 무관)],
          tag[4], [해당 없음. 다른 방식 사용 (크기×3 bias + ESM)],
        )
        v(0.2em)
        text(size: 12pt)[→ 1·2는 원래 코드에도 있어 *고쳐야 함* (#plink("result-b")[결과 B])]
      },
    )),
  )
]

// ---------------------------------------------------------------------------
// 8. A: 고친 결과
// ---------------------------------------------------------------------------
#slide(kicker: "결과 A · 정답 검증", q: "A", title: "정답 계산을 고친 결과")[
  #grid(
    columns: (1fr, 1.05fr),
    column-gutter: 1cm,
    [
      *점이 하늘을 얼마나 보나 (#plink("ao-def")[AO])*
      #v(0.1em)
      #[
        #set text(size: 12pt)
        - 0 = 완전히 가려짐, 1 = 하늘이 다 보임
        - 정상적인 바깥 표면이면 0.3보다 훨씬 큼
        - #text(fill: c-orange.darken(10%))[+0 정답: 29%의 점이 "거의 다 가려짐"(0.05 미만)]
      ]
      #v(0.1em)
      #legend(((name: "AO 중앙값", color: c-blue), (name: "거의 다 가려진 점 비율", color: c-orange)))
      #bars(
        ("+0 정답", "+1 정답", "+2 정답", "+3 정답", "+4 정답"),
        ((name: "AO 중앙값", color: c-blue), (name: "거의 다 가려진 점 비율", color: c-orange)),
        ((0.274, 0.273, 0.515, 0.608, 0.669), (0.285, 0.287, 0.062, 0.006, 0.007)),
        ymax: 0.8,
        ticks: (0, 0.2, 0.4, 0.6, 0.8),
        h: 3.2cm,
        w: 10.5cm,
        xlabel: [+n = 문제 n번까지 고침 · 무작위 2만 개 (+3부터 겉면 1.1만 개)],
      )
      #note[1번(장면 크기)은 AO를 바꾸지 않음: 그림자맵이 1.6배 거칠어져도 넓은 방향의 평균은 그대로. 거칠어짐은 날카로운 그림자 경계에서만 문제가 됨.]
    ],
    [
      *+4 정답을 얼마나 믿을 수 있나*
      #v(0.1em)
      #set text(size: 12.5pt)
      +4 정답에서 설정을 하나씩 바꿔 다시 계산하고, 바꾸기 전과의 차이를 같은 지표(반그림자 오차)로 잼.
      #v(0.2em)
      #table(
        columns: (1fr, auto, auto, auto, auto),
        align: (left, right, right, right, right),
        table.header(text(fill: muted)[바꾼 설정], text(fill: muted)[2°], text(fill: muted)[5°], text(fill: muted)[10°], text(fill: muted)[30°]),
        table.hline(stroke: 0.6pt + rule),
        [그림자맵 해상도 2배], [0.08], [0.05], [0.04], [0.02],
        [방향 수 2배], [0.02], [0.02], [0.02], [0.01],
        [표면에서 띄우는 거리 1.5배], [0.18], [0.13], [0.09], [0.05],
        table.hline(stroke: 0.6pt + rule),
      )
      #note[비교 대상의 오차는 0.1\~0.4 (#plink("result-b")[결과 B]). 해상도·방향 수로 인한 차이는 이보다 충분히 작음. 띄우는 거리는 작은 광원에서 차이가 커서, 2° 결과는 추세만 봄.]
      #v(0.3em)
      #callout[
        #set text(size: 12pt)
        정확한 가림을 아는 단순 장면(평면 위 구, 실제 렌더러)에서 가림 판정 오류 2\~3%.
      ]
    ],
  )
]


// ---------------------------------------------------------------------------
// 9. B: 오차 분해
// ---------------------------------------------------------------------------
#slide(kicker: "결과 B · 오차는 어디서 오나", id: "result-b", q: "B", title: "SBF로 오차 1.2~1.9배 감소, 남은 오차는 대부분 SH 압축")[
  #let series = (
    (name: "TranSplat", color: c-base),
    (name: "TranSplat + SBF (SH 16개는 그대로)", color: c-blue),
    (name: "+4 정답 + SH 16개 압축만", color: c-orange),
    (name: "+4 정답 + SH 100개 압축만", color: c-aqua),
  )
  #grid(
    columns: (1.45fr, 1fr),
    column-gutter: 0.9cm,
    [
      #legend(series)
      #v(0.2em)
      #bars(
        ("2°", "5°", "10°", "30°"),
        series,
        (
          (0.387, 0.331, 0.240, 0.203),
          (0.208, 0.204, 0.197, 0.160),
          (0.184, 0.177, 0.162, 0.105),
          (0.154, 0.141, 0.108, 0.027),
        ),
        ymax: 0.45,
        ticks: (0, 0.1, 0.2, 0.3, 0.4),
        h: 4.9cm,
        w: 13cm,
        xlabel: [광원 크기 · 세로축: 그림자 경계 오차 (낮을수록 좋음)],
      )
      #note[주황·초록은 나머지를 모두 +4 정답과 똑같이 계산하고 가림·조명만 SH로 압축한 것. 즉 *압축 하나가 만드는 오차*. 파랑은 실제 TranSplat 계산 순서(방향 1,200개, SH 16개)에 수정만 넣은 것. \ 모든 막대는 normal 부호(#plink("result-a")[2번])를 고친 상태 (원래 코드는 49%가 뒤집혀 회색보다 나쁨).]
    ],
    [
      #set text(size: 13pt)
      #callout[
        *파랑에 넣은 SBF* → 오차 *1.2\~1.9배* 감소
        #set text(size: 12pt)
        + 장면 크기를 물체 범위로 (#plink("result-a")[1번 문제])
        + 환경맵 SH 요약을 정확히 (1,200점 최근접 샘플 대신 적분) #note[← 작은 광원에서 가장 큼 (2°: 0.39 → 0.28)]
        + 흐린 판정(ESM) 대신 +4 정답과 같은 #plink("judge")[0/1 판정 + 표면에서 띄우기]
        #note[왜 먼저: wavelet은 압축만 바꿈 → 압축과 무관한 오차를 먼저 걷어내야 압축 몫을 잴 수 있음.]
      ]
      #verdict("B", "확인됨")[
        수정 후 남는 오차(파랑)와 SH 16개 압축만의 오차(주황)가 거의 같음 → *남은 오차는 대부분 압축 때문*
      ]
      #v(0.2em)
      #callout(color: c-aqua)[
        SH 숫자를 6배(100개)로 늘려도 작은 광원 오차는 *16\~20%만* 줆. SH를 늘리는 건 비효율적.
      ]
    ],
  )
]

// ---------------------------------------------------------------------------
// 10. C: wavelet vs SH
// ---------------------------------------------------------------------------
#slide(kicker: "결과 C · wavelet vs SH", id: "result-c", q: "C", title: "wavelet과 SH의 메모리 비교")[
  #let series = (
    (name: "같은 개수: +4 정답 + SH 256개 vs + wavelet 256개", color: c-blue),
    (name: "같은 메모리: +4 정답 + SH 256개 vs + wavelet 128개", color: c-orange),
  )
  #grid(
    columns: (1.4fr, 1fr),
    column-gutter: 0.9cm,
    [
      #legend(series)
      #v(0.2em)
      #bars(
        ("2°", "5°", "10°", "30°"),
        series,
        ((1.33, 1.70, 1.86, 0.91), (1.03, 1.16, 1.16, 0.63)),
        ymax: 2.4,
        ticks: (0, 0.5, 1.0, 1.5, 2.0),
        h: 5.4cm,
        refs: ((1.0, "1 = 둘이 같음"), (2.0, "2 = 진행 기준")),
        w: 10.5cm,
        xlabel: [세로축: SH 쪽 오차 ÷ wavelet 쪽 오차 (1보다 크면 wavelet이 나음)],
      )
      #note[+4 정답의 가림만 압축하고 조명은 정확히 둠 → 차이는 압축 방식에서만 생김. 16개, 64개에서도 0.9\~1.4배. 방향 해상도를 2배로 올려 다시 재도 비율 변화 ±0.1 이내 (해상도 탓이 아님).]
    ],
    [
      #verdict("C", "기각됨", color: c-orange)[
        같은 메모리 기준 *0.6\~1.2배*. 같은 개수로 봐도 최대 1.9배(10°)로 *2배 기준에 못 미침*
      ]
      #v(0.3em)
      *메모리 환산* #note[(fp32)]
      #set text(size: 12.5pt)
      #table(
        columns: (1fr, auto, auto),
        align: (left, right, right),
        table.header(text(fill: muted)[저장 방식], text(fill: muted)[점 하나], text(fill: muted)[lego 전체]),
        table.hline(stroke: 0.6pt + rule),
        [SH 16개 (현재)], [64 B], [54 MB],
        [SH 256개], [1 KB], [0.87 GB],
        [wavelet 128개 (값 + 위치)], [1 KB], [0.87 GB],
        table.hline(stroke: 0.6pt + rule),
        text(fill: muted)[압축 없음 (방향 24,576개)], text(fill: muted)[98 KB], text(fill: muted)[84 GB],
        table.hline(stroke: 0.6pt + rule),
      )
      #note[wavelet은 "어느 조각인지" 위치도 저장해야 해서 같은 메모리면 *개수가 절반*. 위치는 4바이트로 가정 (2바이트로 줄이면 wavelet 약 170개). lego 전체 = Gaussian 85만 개. 실험은 평가점 2만 개만 계산해서 실제 사용량은 따로 기록하지 않음 → 계수 수로 환산.]
    ],
  )
]

// ---------------------------------------------------------------------------
// 11. 결과 분석
// ---------------------------------------------------------------------------
#slide(kicker: "해석", title: "결과 분석")[
  #grid(
    columns: (1fr, auto),
    column-gutter: 1.2cm,
    [
      #set text(size: 14pt)
      *1. 가려지는 경계가 기울거나 휘어 있으면 불리*
      #set list(spacing: 0.5em)
      #text(size: 12.5pt)[
        - Haar wavelet은 정사각형 블록(큰 블록 → 작은 블록)을 겹쳐서 그림
        - 경계가 기울거나 휘어 있으면 경계가 지나는 칸마다 작은 블록이 필요
        - 적은 개수로는 계단처럼 깨짐 (SH는 부드럽게 뭉갬) \
          → 결국 둘 다 비슷한 오차 발생
      ]

      #v(0.3em)
      *2. 실사용에서는 점마다 쓸 수 있는 숫자가 적음*
      #text(size: 12.5pt)[
        - Gaussian 약 85만 개에 각각 저장해야 해서, 256개만 써도 0.9 GB (#pref("result-c"))
        - 그래서 실험도 실사용 가능한 16\~256개 범위에서 비교함 (평가점 2만 개만 계산해서 실험 자체의 메모리 문제는 없었음)
        - 이 범위에서는 wavelet 이점이 안 나옴. wavelet이 강했던 원 논문은 *환경맵 하나*를 골라 압축하고, 점 쪽 데이터는 훨씬 크게 저장함
      ]

      #v(0.3em)
      *3. 큰 광원(30°)에서는 SH가 오히려 나음*
      #text(size: 12.5pt)[
        - 부드러운 그림자는 SH가 원래 잘 담음
      ]
    ],
    [
      #let n = 16
      #let s = 0.42cm
      #let cx = 8.3
      #let cy = 7.6
      #let r = 5.4
      #let inside(x, y) = calc.pow(x - cx, 2) + calc.pow(y - cy, 2) < r * r
      #let edge = 0
      #for j in range(n) {
        for i in range(n) {
          let k = (inside(i, j), inside(i + 1, j), inside(i, j + 1), inside(i + 1, j + 1)).filter(v => v).len()
          if k > 0 and k < 4 { edge += 1 }
        }
      }
      #v(0.5em)
      #box(width: n * s, height: n * s, {
        for j in range(n) {
          for i in range(n) {
            let k = (inside(i, j), inside(i + 1, j), inside(i, j + 1), inside(i + 1, j + 1)).filter(v => v).len()
            let fill = if k == 4 { ink.lighten(30%) } else if k > 0 { c-orange.lighten(35%) } else { soft }
            place(top + left, dx: i * s, dy: j * s, rect(width: s, height: s, fill: fill, stroke: 0.4pt + white))
          }
        }
        place(top + left, dx: (cx - r) * s, dy: (cy - r) * s, circle(radius: r * s, stroke: 1.5pt + ink))
      })
      #v(0.3em)
      #box(width: n * s, note[
        #box(width: 0.8em, height: 0.8em, fill: c-orange.lighten(35%), baseline: 0.1em) 경계가 지나는 칸 #edge 개. 이 칸마다 작은 블록이 필요.
      ])
    ],
  )
]

// ---------------------------------------------------------------------------
// 12. 대안
// ---------------------------------------------------------------------------
#slide(kicker: "대안", id: "alt", title: "작은 광원만 따로 처리하기 (광원 분리)")[
  #grid(
    columns: (1fr, 1.2fr),
    column-gutter: 1cm,
    [
      #set text(size: 13pt)
      #let node(body, color: c-blue) = box(
        width: 100%,
        inset: (x: 0.6em, y: 0.45em),
        radius: 5pt,
        fill: color.lighten(88%),
        stroke: 0.8pt + color.lighten(40%),
        body,
      )
      #node(color: c-base)[*새 환경맵*]
      #align(center, text(size: 12pt, fill: muted)[↓ 밝고 작은 부분을 떼어냄])
      #grid(
        columns: (1fr, 1fr),
        column-gutter: 0.4cm,
        row-gutter: 0.25cm,
        node(color: c-orange)[*작은 광원* #note[(태양, 조명)]], node(color: c-aqua)[*나머지* #note[(하늘, 벽 반사)]],
        node(color: c-orange)[다시 조명할 때 그림자맵으로 *직접* 계산],
        node(color: c-aqua)[기존 SH 16개 그대로\ #note[부드러운 빛이라 뭉개져도 티가 덜 남]],
      )
      #align(center, text(size: 12pt, fill: muted)[↓ 더함])
      #node(color: c-base)[*최종 밝기*]
      #v(0.4em)
      #callout(color: c-aqua)[
        #set text(size: 12pt)
        작은 광원(2\~10°)에서 2048px 광원 분리는 SH 100개보다 *약 3\~4배*, TranSplat + SBF보다 *약 5\~6배* 정확함. 30°에서는 비슷함.
      ]
    ],
    [
      #set text(size: 12.5pt)
      #let hl(body) = text(weight: "bold", fill: c-blue.darken(10%), body)
      #table(
        columns: (1fr, auto, auto, auto, auto),
        align: (left, right, right, right, right),
        table.header(
          text(fill: muted)[그림자 경계 오차],
          text(fill: muted)[2°],
          text(fill: muted)[5°],
          text(fill: muted)[10°],
          text(fill: muted)[30°],
        ),
        table.hline(stroke: 0.6pt + rule),
        [TranSplat], [0.39], [0.33], [0.24], [0.20],
        [TranSplat + SBF], [0.21], [0.20], [0.20], [0.16],
        [+4 정답 + SH 100개], [0.15], [0.14], [0.11], [0.03],
        table.hline(stroke: 0.6pt + rule),
        [광원 분리 · 1024px, 샘플 16], [0.13], [0.09], [0.07], [0.04],
        [광원 분리 · 2048px, 샘플 16], hl[0.04], hl[0.04], hl[0.03], hl[0.03],
        table.hline(stroke: 0.6pt + rule),
      )
      #note[px = 광원 방향 그림자맵 해상도, 샘플 = 광원 안에서 쏘는 방향 수. 샘플 1개(딱딱한 그림자)는 0.21\~0.26으로 오히려 나쁨 → 부드러운 그림자용 샘플이 필요.]
      #v(0.2em)
      #callout[
        #set text(size: 11.5pt)
        *광원 분리 수치는 직접 측정함* (`shadow_hybrid_check.py`)
        - 같은 lego 평가점에서 원판 광원 부분만 그림자맵(광원 안 방향 16개)으로 다시 계산 → +4 정답과 비교
        - 하늘은 +4 정답값 그대로 → *광원 그림자 오차만* 본 것. 하늘을 SH 16개로 바꾸면 +0.001 (균일한 하늘이라 최선의 경우)
        - TranSplat 본 코드에는 아직 구현하지 않음
      ]
    ],
  )
]

// ---------------------------------------------------------------------------
// 13. 결론
// ---------------------------------------------------------------------------
#slide(kicker: "정리", title: "결론과 다음 단계")[
  #grid(
    columns: (1fr, 1fr),
    column-gutter: 1cm,
    [
      *결론*
      #table(
        columns: (auto, 1fr),
        align: (left + top, left + top),
        table.hline(stroke: 0.6pt + rule),
        tagl("question")[A],
        [
          정답 계산의 문제 4개 수정 \
          (장면 크기·normal 부호는 원래 코드에도 있음)
        ],
        table.hline(stroke: 0.6pt + rule),
        tagl("question")[B], [*확인됨.* SBF 후 남는 오차는 대부분 압축],
        table.hline(stroke: 0.6pt + rule),
        tagl("question", color: c-orange)[C], [*기각됨.* 같은 메모리면 wavelet ≈ SH],
        table.hline(stroke: 0.6pt + rule),
      )
      #callout(color: c-orange)[
        *wavelet 구현은 보류.* 대신 *기존 코드 수정 + 광원 분리*로 방향을 바꾸는 것을 제안.
      ]
      *다음 단계*
      + SBF를 본 코드에 반영
      + 환경맵에서 광원 추출 + 그림자맵 직접 계산 구현
      + 실제 HDR 환경맵(실내, 해가 있는 야외)으로 재검증
    ],
    [
      *한계*
      #set text(size: 13.5pt)
      - 합성 조명(균일한 하늘 + 원판)만 씀. 실제 환경맵은 광원을 떼어낸 나머지도 복잡할 수 있음.
      - lego에 대해서만 실험해봄
      - 2° 광원은 +4 정답 자체의 불확실성(해상도 0.08, 띄우는 거리 0.18)이 오차와 비슷한 크기라 추세만 봄.
      - 광원 분리 2048px 수치는 같은 해상도의 +4 정답과 비교한 것이라 낙관적 (실제로는 0.02\~0.08 더 클 수 있음).
      - wavelet에는 여러 종류(Haar, Daubechies 같은 부드러운 wavelet, 구면 wavelet 등)가 있는데 가장 단순한 Haar만 비교함. \
        (다만 참고한 triple product 방식(Ng 2004)이 Haar 기준이라 실제 후보도 Haar)

      #v(0.3em)
      *검토*
      - 판단 기준(같은 메모리에서 2배)이 적절한지
      - 광원 분리 방향에 놓친 함정이 없는지
      - 재검증에 쓸 실제 HDR 환경맵 추천
    ],
  )
]

// ---------------------------------------------------------------------------
// 부록
// ---------------------------------------------------------------------------
// 0/1 판정 기준
#slide(kicker: "부록 · 정답 계산", id: "judge", title: "보임 1 / 가림 0 판정 기준")[
  #let c-sun = rgb("#f5b83d")
  #let fig-offset = cetz.canvas(length: 0.8cm, {
    import cetz.draw: *
    // 빛 (그림자맵 카메라 쪽)
    for x in (0.6, 1.6, 2.6, 3.6) {
      line((x + 1.2, 2.6), (x, 0.55), stroke: (paint: c-sun.darken(10%), thickness: 0.6pt, dash: "dashed"))
    }
    content((4.7, 2.75), text(size: 9.5pt, fill: c-sun.darken(30%))[빛])
    // 겹친 납작한 Gaussian
    for (x, y) in ((0.3, 0.42), (1.6, 0.30), (2.9, 0.44)) {
      circle((x + 0.7, y), radius: (0.95, 0.13), fill: c-base.lighten(40%), stroke: 0.6pt + c-base)
    }
    // 평가점 P와 띄운 점 P'
    line((2.3, 0.30), (2.3, 1.15), stroke: 1pt + c-blue, mark: (end: ">", fill: c-blue))
    circle((2.3, 0.30), radius: 0.08, fill: c-orange, stroke: none)
    circle((2.3, 1.15), radius: 0.09, fill: c-blue, stroke: none)
    content((2.45, 0.05), anchor: "north-west", text(size: 9.5pt, fill: c-orange.darken(10%))[P: 그대로면 "가림"])
    content((2.45, 1.2), anchor: "west", text(size: 9.5pt, fill: c-blue)[P': 띄운 위치])
  })
  #let fig-slope = cetz.canvas(length: 0.8cm, {
    import cetz.draw: *
    let th = 50deg
    // 빛이 위에서 수직으로, 표면은 th만큼 기울어짐 (normal과 빛 사이 각 = th)
    let w = 1.4
    let x0 = 0.9
    line((x0, 2.5), (x0, 0.0), stroke: (paint: c-sun.darken(10%), thickness: 0.6pt, dash: "dashed"))
    line((x0 + w, 2.5), (x0 + w, 0.0 - w * calc.tan(th)), stroke: (paint: c-sun.darken(10%), thickness: 0.6pt, dash: "dashed"))
    // 텍셀 폭
    line((x0, 2.3), (x0 + w, 2.3), stroke: 1.2pt + ink2, mark: (start: "|", end: "|"))
    content((x0 + w / 2, 2.6), text(size: 9.5pt)[텍셀 1개 폭 $w$])
    // 기울어진 표면
    line((x0 - 0.5, 0.5 * calc.tan(th)), (x0 + w + 0.6, -(w + 0.6) * calc.tan(th)), stroke: 2pt + c-lego.darken(25%))
    // 깊이 차이
    line((x0 + w + 0.35, 0.0), (x0 + w + 0.35, -w * calc.tan(th)), stroke: 1.2pt + c-orange, mark: (start: "|", end: "|"))
    line((x0, 0.0), (x0 + w + 0.5, 0.0), stroke: (paint: c-orange, thickness: 0.5pt, dash: "dotted"))
    content((x0 + w + 0.5, -0.8), anchor: "west", text(size: 9.5pt, fill: c-orange.darken(10%))[깊이 차이\ $= w times tan theta$])
    // normal과 각
    let nx = calc.sin(th)
    let ny = calc.cos(th)
    let px = x0 + w * 0.5
    let py = -w * 0.5 * calc.tan(th)
    line((px, py), (px + 0.9 * nx, py + 0.9 * ny), stroke: 1pt + c-blue, mark: (end: ">", fill: c-blue))
    content((px + 0.9 * nx + 0.1, py + 0.9 * ny + 0.15), text(size: 9.5pt, fill: c-blue)[$n$])
    content((px - 0.25, py + 0.75), text(size: 9.5pt, fill: ink2)[$theta$])
  })
  #grid(
    columns: (1fr, 1fr),
    column-gutter: 1cm,
    [
      #callout[
        #set text(size: 13pt)
        방향마다 그림자맵에 기록된 깊이 $d_"map"$과 비교:
        $ "가림" quad <==> quad d(P') - d_"map" > epsilon $
        #set text(size: 12pt)
        $P'$ = 점을 *normal 방향으로 띄운* 위치, $epsilon$ = *깊이 허용치*
      ]
      #v(0.2em)
      #set text(size: 12pt)
      #table(
        columns: (auto, 1fr),
        align: (left + top, left + top),
        table.hline(stroke: 0.6pt + rule),
        [*띄우는 거리*], [$2 times$ (그 Gaussian의 가장 긴 반지름) \ #note[lego 표면 점은 보통 *0.016* (물체 반지름 1.57의 약 1%)]],
        table.hline(stroke: 0.3pt + rule),
        [*깊이 허용치* $epsilon$], [$w times (1 + tan theta)$ \ #note[$theta$: normal과 빛 방향 사이 각. 정면 *0.0019*, 45° 0.0038, 60° 0.0052, 84° 이상은 0.021에서 멈춤]],
        table.hline(stroke: 0.3pt + rule),
        [*텍셀 폭* $w$], [그림자맵 픽셀 1개가 물체 중심 깊이에서 덮는 폭 \ #note[카메라는 중심에서 $5r$, 화면 폭 3.87 ÷ 2048px = *0.0019*. 물체 앞뒤로 ±20% 차이는 무시]],
        table.hline(stroke: 0.6pt + rule),
      )
      #note[비교: TranSplat(ESM)은 띄우지 않고 허용치를 $3 times$ 가장 긴 반지름(보통 0.023)으로 고정, 넘은 만큼 $exp$로 흐리게 줄임.]
    ],
    [
      #text(size: 12.5pt, weight: "semibold")[① 왜 띄우나 (#plink("result-a")[4번 문제])]
      #align(center, fig-offset)
      #note[표면이 납작한 원판 여러 장으로 겹쳐 있어, 점이 이웃 원판보다 조금만 아래 있어도 "가려짐"으로 판정됨.]
      #v(0.2em)
      #grid(
        columns: (auto, 1fr),
        column-gutter: 0.4cm,
        align: horizon,
        fig-slope,
        [
          #text(size: 12.5pt, weight: "semibold")[② 왜 경사만큼 허용치를 키우나]
          #v(-0.3em)
          #note[그림자맵 픽셀 하나에는 깊이가 하나만 기록됨. 비스듬한 표면은 그 픽셀 안에서도 깊이가 $w tan theta$만큼 달라져, 같은 표면끼리 가린다고 착각할 수 있음.]
        ],
      )
    ],
  )
]

// 하늘 부분 밝기와 AO (light-vis.typ)
#sky-slide

// cube map 칸의 넓이 w_j (light-vis.typ)
#cube-weight-slide
