// 연구미팅: wavelet 적용 전 실험 (고주파 그림자 개선 방향 검토)
// 컴파일: typst compile report.typ  (devcontainer는 TYPST_FONT_PATHS로 Pretendard를 찾는다. 로컬은 아래 목록 순서로 대체)

#import "theme.typ": *
#import "depth-shell.typ": depth-example, black-shell

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
        lego는 잡티 때문에 $r = 13.9$ (물체만 보면 약 1.9). \
        → 이미지 대부분이 빈 공간, ②의 판정도 무뎌짐 (결과 A).
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
      Gaussian 97.5만 개를 *동시에* 계산 (행렬 곱 + 이미지 조회)
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
      - 메모리: 97.5만 × 16칸 × 4바이트 ≈ *62 MB*. 반복해도 늘지 않음 \
        #note[(1,200개 값을 다 모아 두면 ≈ 4.7 GB)]
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
    columns: (1fr, 1.15fr),
    column-gutter: 1.2cm,
    [
      #v(0.6em)
      #callout(color: c-orange)[
        태양이나 스포트라이트처럼 *작고 강한 광원*의 그림자가 흐리고 옅어짐.
      ]
      #v(0.3em)
      - ③에서 가림을 숫자 16개로 줄이면, "가려짐 ↔ 보임"이 급하게 바뀌는 경계가 부드럽게 뭉개짐.
      - 광원이 크면 넓은 범위를 평균하므로 티가 덜 남.
      - 광원이 작고 경계 근처에 있으면 오차가 커질 수 있음 \
        → 그림자가 흐려지거나 엉뚱한 곳이 어두워짐.
      #v(0.4em)
    ],
    [
      #let W = 14cm
      #let H = 4.4cm
      #let a = occ-a
      #let b = occ-b
      #let N = 3
      #let f(x) = {
        let s = 1 - (b - a) / (2 * calc.pi)
        for k in range(1, N + 1) {
          s += -(calc.sin(k * b) - calc.sin(k * a)) / (k * calc.pi) * calc.cos(k * x)
          s += (calc.cos(k * b) - calc.cos(k * a)) / (k * calc.pi) * calc.sin(k * x)
        }
        s
      }
      #let px(x) = W * x / (2 * calc.pi)
      #let py(v) = H * (1.15 - v) / 1.4
      #let pts = range(0, 201).map(i => 2 * calc.pi * i / 200)
      #text(size: 13pt, fill: ink2)[한 점에서 본 방향별 가림 (1 = 하늘이 보임, 0 = 가려짐)]
      #v(0.3em)
      #box(width: W, height: H + 0.9cm, {
        place(top + left, dy: py(0), line(length: W, stroke: 0.6pt + rule))
        place(top + left, dy: py(1), line(length: W, stroke: 0.6pt + rule))
        place(top + left, curve(
          stroke: 2.5pt + ink,
          curve.move((0pt, py(1))),
          curve.line((px(a), py(1))),
          curve.line((px(a), py(0))),
          curve.line((px(b), py(0))),
          curve.line((px(b), py(1))),
          curve.line((W, py(1))),
        ))
        place(top + left, curve(
          stroke: 2pt + c-orange,
          curve.move((0pt, py(f(0)))),
          ..pts.slice(1).map(x => curve.line((px(x), py(f(x))))),
        ))
        place(top + left, dx: px(a) + 0.15cm, dy: py(0) + 0.15cm, text(size: 11pt, fill: ink2)[가림막 방향])
        // 경계 근처의 작은 광원
        place(top + left, dx: px(b) - 0.45cm, dy: py(1) - 0.75cm, circle(radius: 0.17cm, fill: rgb("#f5b83d")))
        place(top + left, dx: px(b) + 0.05cm, dy: py(1) - 0.8cm, text(size: 11pt, fill: ink2)[작은 광원])
        place(top + left, dy: H + 0.25cm, text(size: 11pt, fill: muted)[방향 →])
      })
      #legend(((name: "실제 가림", color: ink), (name: "숫자 몇 개로 요약 (경계가 뭉개짐)", color: c-orange)))
    ],
  )
]

// ---------------------------------------------------------------------------
// 4. 실험 대상
// ---------------------------------------------------------------------------
#slide(kicker: "질문", title: "이번 실험 대상")[
  압축 방식을 SH 대신 *wavelet*으로 바꾸기. wavelet은 신호를 크기가 다른 블록 조각으로 나눠, 중요한 조각만 골라 저장. \
  -> 경계처럼 급한 변화에 적절할 수 있음.

  #v(0.5em)
  #grid(
    columns: (1fr, 1fr, 1fr),
    column-gutter: 0.8cm,
    callout[
      #tag[A] *정확한 GT 필요*
      #v(0.2em)
      #note[
        - 오차를 재려면 "압축하지 않은 정답"이 필요
        - 이 정답 계산 자체가 맞는지부터 확인 해야 함.
      ]
    ],
    callout[
      #tag[B] *압축이 주 원인인지 확인*
      #v(0.2em)
      #note[
        - 현재 코드에는 다른 오차 원인도 존재
        - 고친 뒤에도 남는 오차가 대부분 "16개로 요약"에서 오는지 확인 필요
      ]
    ],
    callout[
      #tag[C] *wavelet로 개선 가능한지*
      #v(0.2em)
      #note[
        - 같은 저장 공간을 줬을 때 wavelet의 오차가 SH보다 충분히 작은지.
        - 사용하는 메모리가 허용 범위 안에 있는지.
      ]
    ],
  )
  #v(0.7em)
  #[
    *판단 규칙*
    - B와 C 둘 다 "예" → wavelet으로 진행
    - 하나라도 "아니오" → 방향 전환
  ]
]

// ---------------------------------------------------------------------------
// 5. 실험 설계: 조건
// ---------------------------------------------------------------------------
#slide(kicker: "방법 · 실험 조건", title: "실험 설계: 한 번에 한 요소만 바꿔서 비교")[
  #grid(
    align: horizon,
    columns: (2fr, 1fr),
    column-gutter: 1.2cm,
    [
      #table(
        columns: (auto, 1fr),
        align: (center, left),
        table.hline(stroke: 0.6pt + rule),
        text(fill: muted)[장면], [lego (Gaussian 97.5만 개 중 표면 점 4만 개 평가)],
        table.hline(stroke: 0.6pt + rule),
        text(fill: muted)[조명],
        [균일한 하늘 + 원판 광원 1개. 크기 2°, 5°, 10°, 30° × 방향 3개\ #note[(참고: 태양은 약 0.5°)]],
        table.hline(stroke: 0.6pt + rule),
        text(fill: muted)[정답], [압축 없이 방향 약 2.5만 개 각각에서 그림자맵을 그려 직접 계산],
        table.hline(stroke: 0.6pt + rule),
        text(fill: muted)[비교],
        [정답에서 한 요소만 변경
          → 그 요소가 만드는 오차만 분리],
        table.hline(stroke: 0.6pt + rule),
      )
    ],
    image("r_10.png", width: 100%, height: 10cm, fit: "contain"),
  )
]

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
    lbl(X(x1) + 0.15cm, Y(0.62), [|추정 − 정답|], size: 11pt, fill: c-orange.darken(15%))
    place(top + left, dx: ox, dy: oy + H, line(length: W, stroke: 0.8pt + ink2))
    lbl(ox, oy + H + 0.15cm, [표면 위의 위치 → (그림자 경계를 가로지름)], size: 10.5pt, fill: muted)
  })
  #grid(
    columns: (1.3fr, 1fr),
    column-gutter: 1cm,
    [
      *지표: 그림자 경계 오차*
      #v(0.1em)
      #legend(((name: "정답", color: ink), (name: "추정", color: c-blue)))
      #scale(85%, reflow: true, origin: top + left, vis-metric)
      #[
        #set text(size: 12pt)
        $ "오차" = (limits("평균")_(i in P) abs(E_i - E_i^"정답")) / (limits("평균")_(i in L) E_i^"정답") $
        #note[$E_i$: 점 $i$의 밝기 · $P$: 반그림자 점 · $L$: 밝은 곳 점. 예) 0.2 = 경계에서 밝은 곳 밝기의 20%만큼 틀림. 작을수록 좋음.]
      ]
    ],
    [
      *비교 대상: 아래 5가지를 각각 계산해 정답과 비교*
      #v(0.2em)
      #set text(size: 12pt)
      #table(
        columns: (auto, 1fr, auto),
        align: (left + horizon, left + horizon, center + horizon),
        inset: (x: 0.4em, y: 0.5em),
        table.hline(stroke: 0.6pt + rule),
        text(fill: muted)[계산한 것], text(fill: muted)[알고 싶은 것], text(fill: muted)[질문],
        table.hline(stroke: 0.6pt + rule),
        [① 현재 TranSplat 그대로], [지금 얼마나 틀리나], tag[B],
        table.hline(stroke: 0.3pt + rule),
        [② ① + 쉬운 수정 4가지], [수정만으로 얼마나 개선되는지], tag[B],
        table.hline(stroke: 0.3pt + rule),
        [③ 정답 + SH 압축만\ #note[(계수 16 / 100 / 256개)]], [SH 압축 오차], [#tag[B] #tag[C]],
        table.hline(stroke: 0.3pt + rule),
        [④ 정답 + wavelet 압축만\ #note[(계수 8 → 256개)]], [같은 메모리면\ ③보다 나은가], tag[C],
        table.hline(stroke: 0.3pt + rule),
        [⑤ 광원만 그림자맵으로], [대안이 될까], tag(color: c-aqua)[대안],
        table.hline(stroke: 0.6pt + rule),
      )
      #note[③ ④는 정답에서 압축 하나만 넣은 것 → 늘어난 오차가 곧 압축 탓.]
    ],
  )
]

// ---------------------------------------------------------------------------
// 7. A: 정답 계산의 문제들
// ---------------------------------------------------------------------------
#slide(kicker: "결과 A · 정답 검증", title: "새로운 문제: 정답 계산도 어려움")[
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
  #let floaters = ((3.4, 0.5), (4.1, 1.7), (4.9, 0.8), (5.5, 1.5), (3.8, 1.2), (6.1, 0.4), (5.2, 1.9))
  #let v1 = {
    let cx = 1.3cm
    let cy = 1.05cm
    place(top + left, dx: cx - 5.4cm, dy: cy - 5.4cm, circle(radius: 5.4cm, stroke: (
      paint: c-orange,
      thickness: 1.2pt,
      dash: "dashed",
    )))
    place(top + left, dx: cx - 0.8cm, dy: cy - 0.8cm, circle(radius: 0.8cm, stroke: 1.2pt + c-blue))
    place(top + left, dx: cx - 0.45cm, dy: cy - 0.1cm, rect(width: 0.9cm, height: 0.45cm, fill: c-base, radius: 2pt))
    place(top + left, dx: cx - 0.2cm, dy: cy - 0.35cm, rect(width: 0.4cm, height: 0.26cm, fill: c-base, radius: 2pt))
    for (x, y) in floaters { dotc(x * 1cm, y * 1cm, r: 0.07cm, fill: muted) }
    lbl(2.2cm, 1.5cm, [물체 범위 1.9], fill: c-blue)
    lbl(6.85cm, 0.85cm, [잡티까지\ 포함 13.9], fill: c-orange.darken(10%))
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
  #let v5 = {
    cam(0.45cm, 0.95cm)
    place(top + left, dx: 6.6cm, dy: 0.3cm, rect(width: 1.7cm, height: 1.2cm, fill: ink.lighten(25%), radius: 2pt))
    for k in range(5) {
      let y = 0.42cm + k * 0.27cm
      seg(0.8cm, y, 3.3cm, y, stroke: 1.1pt + c-blue)
      seg(3.3cm, y, 6.6cm, y, stroke: (paint: c-base, thickness: 0.8pt, dash: "dotted"))
    }
    for (x, y) in ((3.4, 0.35), (3.6, 0.7), (3.35, 1.0), (3.65, 1.3), (3.45, 1.55), (3.9, 0.55), (3.85, 1.15)) {
      dotc(x * 1cm, y * 1cm, r: 0.11cm, fill: muted)
    }
    lbl(4.1cm, 1.45cm, [잡티], size: 9.5pt)
    lbl(6.6cm, 1.52cm, [전부 "가려짐"], size: 9.5pt)
  }
  #grid(
    columns: (1fr, 1fr, 1fr),
    column-gutter: 0.5cm,
    row-gutter: 0.3cm,
    card(
      "1",
      "장면 크기를 너무 크게 잡음",
      v1,
      [잡티까지 포함해 장면 반지름을 13.9로 잡음 (물체는 1.9) → 그림자맵이 약 7배 거칠어짐.],
      [잡티를 뺀 99.5% 범위 × 1.1로 계산],
    ),
    card(
      "2",
      "표면 앞/뒤가 뒤집힘",
      v2,
      [표면 방향(normal)의 부호가 임의라 약 48%가 안쪽을 향함 → 빛을 반대쪽에서 받음.],
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
      [판정할 때 점을 표면 방향으로 살짝 띄움],
    ),
    card(
      "5",
      "잡티가 카메라 앞을 막음",
      v5,
      [물체 밖 잡티가 그림자맵 카메라와 물체 사이에 있어 그 방향 전체가 "가려짐".],
      [그림자 계산에서 잡티(1,907개) 제외],
    ),
    block(
      width: 100%,
      height: 5.3cm,
      breakable: false,
      inset: (x: 0.7em, y: 0.6em),
      radius: 6pt,
      fill: c-aqua.lighten(90%),
      stroke: 1.2pt + c-aqua,
      {
        text(size: 13pt, weight: "bold")[기존 TranSplat에도 있나?]
        v(0.1em)
        set text(size: 11pt)
        table(
          columns: (auto, 1fr),
          inset: (x: 0.3em, y: 0.22em),
          align: (left + top, left + top),
          tag[1], [*있음.* 장면 크기 = 1.8 × 가장 먼 점 거리],
          tag[2], [*있음.* normal 부호를 보정하지 않음],
          tag[3], [평가용 문제 (렌더에는 영향 적음)],
          tag[4], [다른 방식 사용 (크기×3 bias + ESM)],
          tag[5], [*있음.* 그림자맵에 잡티 포함],
        )
        text(size: 11pt)[→ *TranSplat도 고치면 개선 가능* (결과 B)]
      },
    ),
  )
]

// ---------------------------------------------------------------------------
// 8. A: 고친 결과
// ---------------------------------------------------------------------------
#slide(kicker: "결과 A · 정답 검증", title: "정답 계산을 고친 결과")[
  #grid(
    columns: (1fr, 1.05fr),
    column-gutter: 1cm,
    [
      *점이 하늘을 얼마나 보나 (AO)*
      #v(0.1em)
      #box(width: 100%, height: 2.3cm, {
        let px = 2.2cm
        let py = 2.0cm
        let r = 1.5cm
        place(top + left, dx: 0.2cm, dy: py, line(length: 4.4cm, stroke: 1pt + ink2))
        for i in range(36) {
          let t0 = i * 5deg
          let t1 = (i + 1) * 5deg
          let blocked = t1 <= 55deg
          seg(
            px + r * calc.cos(t0),
            py - r * calc.sin(t0),
            px + r * calc.cos(t1),
            py - r * calc.sin(t1),
            stroke: (if blocked { 3pt } else { 2.4pt }) + (if blocked { ink } else { c-blue }),
          )
        }
        place(top + left, dx: 3.85cm, dy: 0.6cm, rect(width: 0.45cm, height: py - 0.6cm, fill: c-base, radius: (
          top-left: 2pt,
          top-right: 2pt,
        )))
        dotc(px, py, r: 0.1cm, fill: c-orange)
        lbl(4.9cm, 0.45cm, [하늘 중 #text(fill: c-blue, weight: "bold")[보이는 비율] (0\~1)], size: 11pt)
        lbl(4.9cm, 1.0cm, [정상적인 바깥 표면이면 0.3보다 훨씬 큼], size: 11pt, fill: muted)
        lbl(4.9cm, 1.45cm, [처음 0.08 = "거의 다 가려짐"으로 잘못 계산], size: 11pt, fill: c-orange.darken(10%))
      })
      #v(0.2em)
      #bars(
        ("처음", "1~4번 수정", "+ 5번 (잡티 제외)"),
        ((name: "중앙값", color: c-blue),),
        ((0.079, 0.395, 0.655),),
        ymax: 0.8,
        ticks: (0, 0.2, 0.4, 0.6, 0.8),
        h: 3.4cm,
        w: 10.5cm,
        xlabel: [평가점 4만 개의 AO 중앙값],
      )
      #note[검증: 정답을 아는 단순 장면(평면 위 구)에서 판정 오류 2\~3%. 그림자맵 해상도를 2배로 올렸을 때 결과가 바뀌는 정도: 2° 광원 0.09, 10° 이상 0.04 이하.]
    ],
    [
      *잡티 (floater)*
      #v(0.1em)
      #box(width: 100%, height: 2.6cm, {
        let cx = 2.2cm
        let cy = 1.35cm
        place(top + left, dx: cx - 1.05cm, dy: cy - 1.05cm, circle(radius: 1.05cm, stroke: (
          paint: c-blue,
          thickness: 0.8pt,
          dash: "dashed",
        )))
        place(top + left, dx: cx - 0.65cm, dy: cy - 0.05cm, rect(
          width: 1.3cm,
          height: 0.55cm,
          fill: c-base,
          radius: 2pt,
        ))
        place(top + left, dx: cx - 0.3cm, dy: cy - 0.4cm, rect(width: 0.6cm, height: 0.35cm, fill: c-base, radius: 2pt))
        for (x, y, r) in (
          (0.35, 0.3, 0.12),
          (4.0, 0.4, 0.1),
          (4.4, 2.0, 0.14),
          (0.5, 2.3, 0.09),
          (3.7, 1.2, 0.08),
          (0.2, 1.3, 0.1),
        ) {
          place(top + left, dx: x * 1cm - r * 1cm, dy: y * 1cm - r * 1cm, circle(
            radius: r * 1cm,
            fill: muted.transparentize(40%),
          ))
        }
        place(top + left, dx: 5.2cm, dy: 0.25cm, box(width: 8.4cm, text(size: 11.5pt)[
          학습 중 *허공에 생긴 Gaussian*. 사진에서는 거의 안 보이지만 그림자 계산에서는 가림막이 됨.\
          #text(fill: muted)[lego: 97.5만 개 중 1,907개 (0.2%)]
        ]))
      })
      #v(0.5em)
      *5번 문제가 만든 착시*
      #v(0.1em)
      #let grid-map(n, s, dark) = box(width: n * s, height: n * s, {
        for j in range(n) {
          for i in range(n) {
            place(top + left, dx: i * s, dy: j * s, rect(width: s, height: s, stroke: 0.4pt + white, fill: if dark(
              i,
              j,
            ) { ink.lighten(25%) } else { soft.darken(4%) }))
          }
        }
      })
      #let shadow(i, j) = j >= 6 and i + j >= 9
      #grid(
        columns: (auto, auto, 1fr),
        column-gutter: 0.45cm,
        align: top,
        [#grid-map(8, 0.28cm, (i, j) => shadow(i, j) or (i < 4 and j < 4)) \ #note[고치기 전]],
        [#grid-map(8, 0.28cm, shadow) \ #note[고친 뒤]],
        text(size: 11.5pt)[
          방향별 가림 지도에 격자와 딱 맞는 *큰 정사각형 덩어리*(잡티가 막은 방향)가 생김 → 블록 단위로 그리는 wavelet에 아주 유리한 모양.
          #v(0.2em)
          #text(fill: c-orange.darken(15%))[중간 결과에서 wavelet이 *최대 2.9배* 좋아 보인 원인. 고치자 사라짐.]
        ],
      )
    ],
  )
]

// A 보충: lego의 검은 막 (depth-shell.typ)
#black-shell

// ---------------------------------------------------------------------------
// 9. B: 오차 분해
// ---------------------------------------------------------------------------
#slide(kicker: "결과 B · 오차는 어디서 오나", title: "잡티 제외 등 4가지 수정으로 오차 절반, 남은 오차는 SH 압축")[
  #let series = (
    (name: "현재 TranSplat 코드", color: c-base),
    (name: "4가지 수정 적용 (SH 16개는 그대로)", color: c-blue),
    (name: "정답 + SH 16개 압축만", color: c-orange),
    (name: "정답 + SH 100개 압축만", color: c-aqua),
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
          (0.459, 0.537, 0.346, 0.260),
          (0.216, 0.213, 0.199, 0.153),
          (0.176, 0.177, 0.165, 0.114),
          (0.134, 0.126, 0.099, 0.028),
        ),
        ymax: 0.6,
        h: 5.4cm,
        w: 13cm,
        xlabel: [광원 크기 · 세로축: 그림자 경계 오차 (낮을수록 좋음)],
      )
      #note[주황·초록은 나머지를 모두 정답과 똑같이 계산하고 가림·조명만 SH로 압축한 것. 즉 *압축 하나가 만드는 오차*. 파랑은 실제 TranSplat 계산 순서(방향 1,200개, SH 16개)에 수정만 넣은 것.]
    ],
    [
      #set text(size: 13pt)
      #callout[
        *파랑에 넣은 4가지 수정* → 오차 *2\~2.5배* 감소
        #set text(size: 12pt)
        + 잡티를 그림자맵에서 제외
        + 장면 크기를 잡티 뺀 범위로 계산
        + 환경맵 SH 요약을 정확히 (1,200점 최근접 샘플 대신 적분)
        + 흐린 판정(ESM) 대신 0/1 판정 + 표면에서 띄우기
      ]
      #verdict("B", "예")[
        수정 후 남는 오차(파랑)와 SH 16개 압축만의 오차(주황)가 거의 같음 → *남은 오차는 대부분 압축 때문*
      ]
      #v(0.2em)
      #callout(color: c-aqua)[
        SH 숫자를 6배(100개)로 늘려도 작은 광원 오차는 *25%만* 줆. SH를 늘리는 건 비효율적.
      ]
    ],
  )
]

// ---------------------------------------------------------------------------
// 10. C: wavelet vs SH
// ---------------------------------------------------------------------------
#slide(kicker: "결과 C · wavelet vs SH", title: "wavelet과 SH의 메모리 비교")[
  #let series = (
    (name: "같은 개수 (둘 다 256개)", color: c-blue),
    (name: "같은 메모리 (wavelet 128개 vs SH 256개)", color: c-orange),
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
        ((1.12, 1.59, 1.72, 0.81), (0.94, 1.05, 1.01, 0.60)),
        ymax: 2.4,
        ticks: (0, 0.5, 1.0, 1.5, 2.0),
        h: 5.4cm,
        refs: ((1.0, "1 = 둘이 같음"), (2.0, "2 = 진행 기준")),
        w: 10.5cm,
        xlabel: [세로축: SH 오차 ÷ wavelet 오차 (1보다 크면 wavelet이 나음)],
      )
      #note[16개, 64개에서도 0.9\~1.4배. 방향 해상도를 2배로 올려 다시 재도 비율 변화 ±0.1 이내 (해상도 탓이 아님).]
    ],
    [
      #verdict("C", "아니오", color: c-orange)[
        같은 메모리 기준 *0.6\~1.05배*. 같은 개수로 봐도 최대 1.7배로 *2배 기준에 못 미침*
      ]
      #v(0.3em)
      *메모리 환산* #note[(fp32)]
      #set text(size: 12.5pt)
      #table(
        columns: (1fr, auto, auto),
        align: (left, right, right),
        table.header(text(fill: muted)[저장 방식], text(fill: muted)[점 하나], text(fill: muted)[lego 전체]),
        table.hline(stroke: 0.6pt + rule),
        [SH 16개 (현재)], [64 B], [62 MB],
        [SH 256개], [1 KB], [1.0 GB],
        [wavelet 128개 (값 + 위치)], [1 KB], [1.0 GB],
        table.hline(stroke: 0.6pt + rule),
        text(fill: muted)[압축 없음 (방향 24,576개)], text(fill: muted)[98 KB], text(fill: muted)[96 GB],
        table.hline(stroke: 0.6pt + rule),
      )
      #note[wavelet은 "어느 조각인지" 위치도 저장해야 해서 같은 메모리면 *개수가 절반*. 위치는 4바이트로 가정 (2바이트로 줄이면 wavelet 약 170개). lego 전체 = Gaussian 97.5만 개. 실험은 평가점 4만 개만 계산해서 실제 사용량은 따로 기록하지 않음 → 계수 수로 환산.]
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
        - Gaussian 약 100만 개에 각각 저장해야 해서, 256개만 써도 1 GB (앞 슬라이드)
        - 그래서 실험도 실사용 가능한 16\~256개 범위에서 비교함 (평가점 4만 개만 계산해서 실험 자체의 메모리 문제는 없었음)
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
#slide(kicker: "대안", title: "작은 광원만 따로 처리하기 (광원 분리)")[
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
        작은 광원(2\~10°)에서 2048px 광원 분리는 SH 100개보다 *약 3배*, 4가지 수정 후보다 *약 5배* 정확함. 30°에서는 비슷함.
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
        [현재 코드], [0.46], [0.54], [0.35], [0.26],
        [4가지 수정 후], [0.22], [0.21], [0.20], [0.15],
        [SH 100개 (압축만)], [0.13], [0.13], [0.10], [0.03],
        table.hline(stroke: 0.6pt + rule),
        [광원 분리 · 1024px, 샘플 16], [0.13], [0.10], [0.07], [0.05],
        [광원 분리 · 2048px, 샘플 16], hl[0.04], hl[0.04], hl[0.03], hl[0.03],
        table.hline(stroke: 0.6pt + rule),
      )
      #note[px = 광원 방향 그림자맵 해상도, 샘플 = 광원 안에서 쏘는 방향 수. 샘플 1개(딱딱한 그림자)는 0.20\~0.27로 오히려 나쁨 → 부드러운 그림자용 샘플이 필요.]
      #v(0.2em)
      #callout[
        #set text(size: 11.5pt)
        *광원 분리 수치는 직접 측정함* (`shadow_hybrid_check.py`)
        - 같은 lego 평가점에서 원판 광원 부분만 그림자맵(광원 안 방향 16개)으로 다시 계산 → 정답과 비교
        - 하늘은 정답값 그대로 → *광원 그림자 오차만* 본 것. 하늘을 SH 16개로 바꾸면 +0.001 (균일한 하늘이라 최선의 경우)
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
        tag[A],
        [
          정답 계산의 문제 5개 수정 \
          (3개는 기존 TranSplat에도 있음)
        ],
        table.hline(stroke: 0.6pt + rule),
        tag[B], [Yes. 4가지 수정 후 남는 오차는 대부분 압축],
        table.hline(stroke: 0.6pt + rule),
        tag(color: c-orange)[C], [No. 같은 메모리면 wavelet ≈ SH],
        table.hline(stroke: 0.6pt + rule),
      )
      #callout(color: c-orange)[
        *wavelet 구현은 보류.* 대신 *기존 코드 수정 + 광원 분리*로 방향을 바꾸는 것을 제안.
      ]
      *다음 단계*
      + 4가지 수정을 본 코드에 반영
      + 환경맵에서 광원 추출 + 그림자맵 직접 계산 구현
      + 실제 HDR 환경맵(실내, 해가 있는 야외)으로 재검증
    ],
    [
      *한계*
      #set text(size: 13.5pt)
      - 합성 조명(균일한 하늘 + 원판)만 씀. 실제 환경맵은 광원을 떼어낸 나머지도 복잡할 수 있음.
      - lego에 대해서만 실험해봄
      - 2° 광원은 정답 자체의 불확실성(0.09)이 오차와 비슷한 크기라 추세만 봄.
      - 광원 분리 2048px 수치는 같은 해상도 정답과 비교한 것이라 낙관적 (실제로는 0.02\~0.09 더 클 수 있음).
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
