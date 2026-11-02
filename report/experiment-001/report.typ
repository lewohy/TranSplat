// 연구미팅: wavelet 적용 전 실험 (고주파 그림자 개선 방향 검토)
// 컴파일: typst compile report.typ  (devcontainer는 TYPST_FONT_PATHS로 Pretendard를 찾는다. 로컬은 아래 목록 순서로 대체)

#let ink = rgb("#0b0b0b")
#let ink2 = rgb("#52514e")
#let muted = rgb("#8a8984")
#let rule = rgb("#e4e3df")
#let soft = rgb("#f4f3f0")
#let c-blue = rgb("#2a78d6")
#let c-orange = rgb("#eb6834")
#let c-aqua = rgb("#1baf7a")
#let c-base = rgb("#a9a8a3")

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

#let slide(title: none, kicker: none, body) = {
  pagebreak(weak: true)
  if kicker != none {
    text(size: 12pt, fill: c-blue, weight: "semibold", kicker)
    v(0.15em)
  }
  if title != none {
    text(size: 23pt, weight: "bold", title)
    v(0.45em)
  }
  body
}
#let note(body) = text(size: 11.5pt, fill: ink2, body)
#let callout(body, color: c-blue) = block(
  width: 100%,
  breakable: false,
  inset: (x: 0.9em, y: 0.7em),
  radius: 6pt,
  fill: color.lighten(90%),
  stroke: (left: 3pt + color),
  body,
)
#let tag(body, color: c-blue) = box(
  inset: (x: 0.45em, y: 0.2em),
  radius: 4pt,
  fill: color.lighten(85%),
  text(size: 12pt, weight: "semibold", fill: color.darken(25%), body),
)
// 질문(A/B/C)에 대한 답을 강조하는 박스. 결과 슬라이드마다 같은 모양으로 쓴다.
#let verdict(q, answer, color: c-blue, body) = block(
  width: 100%,
  breakable: false,
  inset: (x: 0.8em, y: 0.65em),
  radius: 6pt,
  fill: color.lighten(88%),
  stroke: 1.5pt + color,
  grid(
    columns: (auto, 1fr),
    column-gutter: 0.8em,
    align: horizon,
    box(inset: (x: 0.6em, y: 0.4em), radius: 5pt, fill: color, text(
      size: 21pt,
      weight: "bold",
      fill: white,
    )[#q: #answer]),
    text(size: 12.5pt, body),
  ),
)
#let placeholder(w, h, body) = rect(
  width: w,
  height: h,
  radius: 6pt,
  fill: soft,
  stroke: (paint: muted, thickness: 1pt, dash: "dashed"),
  align(center + horizon, text(size: 13pt, fill: muted, body)),
)

#let fmt(v, d: 2) = {
  let s = str(calc.round(v, digits: d))
  let p = s.split(".")
  if p.len() == 1 { s + "." + "0" * d } else { s + "0" * (d - p.at(1).len()) }
}

// 그림 도우미. 모두 box 안에서 왼쪽 위 기준 좌표로 쓴다.
#let dotc(x, y, r: 0.06cm, fill: ink2) = place(top + left, dx: x - r, dy: y - r, circle(
  radius: r,
  fill: fill,
  stroke: none,
))
#let lbl(x, y, body, size: 10pt, fill: ink2) = place(top + left, dx: x, dy: y, text(size: size, fill: fill, body))
#let seg(x0, y0, x1, y1, stroke: 1pt + ink2) = place(top + left, curve(stroke: stroke, curve.move((x0, y0)), curve.line(
  (x1, y1),
)))
#let arrow(x0, y0, x1, y1, paint: ink2, th: 1pt, head: 0.18cm) = {
  let dx = (x1 - x0) / 1cm
  let dy = (y1 - y0) / 1cm
  let l = calc.sqrt(dx * dx + dy * dy)
  let ux = dx / l
  let uy = dy / l
  let bx = x1 - ux * head
  let by = y1 - uy * head
  seg(x0, y0, bx, by, stroke: th + paint)
  place(top + left, curve(
    fill: paint,
    stroke: none,
    curve.move((x1, y1)),
    curve.line((bx - uy * head * 0.55, by + ux * head * 0.55)),
    curve.line((bx + uy * head * 0.55, by - ux * head * 0.55)),
    curve.close(),
  ))
}
#let cam(x, y, color: c-blue) = {
  place(top + left, dx: x - 0.2cm, dy: y - 0.13cm, rect(width: 0.3cm, height: 0.26cm, radius: 1.5pt, fill: color))
  place(top + left, curve(
    fill: color,
    stroke: none,
    curve.move((x + 0.1cm, y)),
    curve.line((x + 0.28cm, y - 0.13cm)),
    curve.line((x + 0.28cm, y + 0.13cm)),
    curve.close(),
  ))
}
#let cross(x, y, s: 0.12cm, stroke: 1.4pt + c-orange) = {
  seg(x - s, y - s, x + s, y + s, stroke: stroke)
  seg(x - s, y + s, x + s, y - s, stroke: stroke)
}

// Grouped bar chart. data: one array per series, one value per category.
#let bars(
  cats,
  series,
  data,
  ymax: 0.6,
  ticks: (0, 0.2, 0.4, 0.6),
  h: 6.2cm,
  w: 15cm,
  refs: (),
  xlabel: none,
  ylabel: none,
) = {
  let lm = 1.3cm
  let n = cats.len()
  let m = series.len()
  let gw = w / n
  let bw = gw * 0.78 / m
  let y(v) = h - h * v / ymax
  let rm = if refs.len() > 0 { 2.7cm } else { 0cm }
  block(width: lm + w + rm, height: h + 1.2cm, {
    for t in ticks {
      place(top + left, dx: lm, dy: y(t), line(length: w, stroke: 0.6pt + rule))
      place(top + left, dx: 0cm, dy: y(t) - 0.45em, box(width: lm - 0.25cm, align(right, text(
        size: 11pt,
        fill: muted,
        fmt(t, d: 1),
      ))))
    }
    for (j, c) in cats.enumerate() {
      for (i, s) in series.enumerate() {
        let v = data.at(i).at(j)
        let x0 = lm + gw * j + gw * 0.11 + bw * i
        place(top + left, dx: x0, dy: y(calc.min(v, ymax)), rect(
          width: bw - 2pt,
          height: h * calc.min(v, ymax) / ymax,
          fill: s.color,
          radius: (top-left: 3pt, top-right: 3pt),
        ))
        place(top + left, dx: x0 - 0.3cm, dy: y(calc.min(v, ymax)) - 0.5cm, box(width: bw - 2pt + 0.6cm, align(
          center,
          text(size: 9.5pt, fill: ink2, fmt(v)),
        )))
      }
      place(top + left, dx: lm + gw * j, dy: h + 0.18cm, box(width: gw, align(center, text(size: 13pt, c))))
    }
    for r in refs {
      place(top + left, dx: lm, dy: y(r.at(0)), line(length: w, stroke: (paint: ink2, thickness: 1pt, dash: "dashed")))
      place(top + left, dx: lm + w + 0.15cm, dy: y(r.at(0)) - 0.5em, box(width: rm - 0.15cm, text(
        size: 10pt,
        fill: ink2,
        weight: "semibold",
        r.at(1),
      )))
    }
    place(top + left, dx: lm, dy: h, line(length: w, stroke: 0.8pt + ink2))
    if xlabel != none {
      place(top + left, dx: lm, dy: h + 0.72cm, box(width: w, align(center, text(size: 11pt, fill: muted, xlabel))))
    }
  })
}
#let legend(series) = {
  set text(size: 12.5pt)
  series
    .map(s => box[#box(width: 0.8em, height: 0.8em, radius: 2pt, fill: s.color, baseline: 0.1em) #h(0.3em)#s.name])
    .join(h(1.1em))
}

// 한 점에서 본 방향별 가림 (1차원 예시): 방향 a~b가 가려짐. 앞 몇 개 주파수로 요약한 근사와 그 계수.
#let occ-a = 2.0
#let occ-b = 3.1
#let occ-coeffs = {
  let a = occ-a
  let b = occ-b
  let cs = (1 - (b - a) / (2 * calc.pi),)
  for k in range(1, 9) {
    cs.push(-(calc.sin(k * b) - calc.sin(k * a)) / (k * calc.pi))
    if k < 8 { cs.push((calc.cos(k * b) - calc.cos(k * a)) / (k * calc.pi)) }
  }
  cs
}
#let coeff-bars(cs, x, mid, hmax, bw: 0.13cm, gap: 0.04cm, color: c-orange) = {
  let vmax = calc.max(..cs.map(calc.abs))
  for (i, v) in cs.enumerate() {
    let hh = hmax * calc.abs(v) / vmax
    place(
      top + left,
      dx: x + i * (bw + gap),
      dy: if v > 0 { mid - hh } else { mid },
      rect(width: bw, height: hh, fill: color, radius: 1pt),
    )
  }
  place(top + left, dx: x, dy: mid, line(length: cs.len() * (bw + gap), stroke: 0.5pt + ink2))
}

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
  v(1fr)
  grid(
    columns: (auto, 1fr),
    column-gutter: 1em,
    row-gutter: 0.5em,
    text(size: 13pt, fill: muted)[결론 미리보기],
    text(
      size: 13pt,
    )[같은 메모리면 wavelet은 지금 방식(SH)보다 낫지 않음. 대신 기존 코드의 몇 가지 수정과 "광원 분리"가 훨씬 효과적.],

    text(size: 13pt, fill: muted)[데모],
    text(size: 13pt)[`demo.html` (압축 방식에 따라 그림자가 어떻게 뭉개지는지 직접 조작)],
  )
  v(0.6cm)
}

// ---------------------------------------------------------------------------
// 2. TranSplat 그림자 계산 단계
// ---------------------------------------------------------------------------
#slide(kicker: "배경", title: "TranSplat의 그림자 구현 방식")[
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
  #let step(n, phase, title, vis, body) = [
    #text(size: 11pt, fill: muted)[#phase]\
    #text(size: 14pt, weight: "bold")[#text(fill: c-blue)[#n] #title]
    #v(0.1em)
    #box(width: 100%, height: 3.2cm, align(center, vis))
    #v(0.2em)
    #set text(size: 11.5pt, fill: ink2)
    #set par(leading: 0.6em)
    #body
  ]
  #let arr = align(center, pad(top: 2.4cm, text(size: 18pt, fill: muted)[→]))
  #v(0.4em)
  #grid(
    columns: (1fr, auto, 1fr, auto, 1fr, auto, 1fr),
    column-gutter: 0.25cm,
    step("①", "미리 계산 (bake)", "방향마다 그림자맵", vis-bake)[
      물체를 둘러싼 방향 *1,200개*(구 위에 고르게)마다, 그 방향에서 물체를 보는 카메라로 *깊이 이미지*(그림자맵)를 그림.
    ],
    arr,
    step("②", "미리 계산 (bake)", "Gaussian마다 가림 판정", vis-test)[
      Gaussian이 그림자맵의 깊이보다 뒤에 있으면 그 방향은 *가려짐(0)*, 아니면 *보임(1)*. 점마다 방향 1,200개짜리 가림 지도가 생김. 판정은 경계를 흐리게 하는 ESM + PCF.
    ],
    arr,
    step("③", "미리 계산 (bake)", "SH로 요약 저장", vis-sh)[
      가림 지도를 SH(구면 위의 저주파 성분, 차수 3까지)로 투영해 점마다 *숫자 16개*만 저장. 날카로운 경계는 이 단계에서 뭉개짐.
    ],
    arr,
    step("④", "다시 조명 (relight)", "새 조명과 곱하기", vis-relight)[
      새 환경맵도 SH 16개로 요약 → 가림과 곱하고(Gaunt) 표면 방향(cosine)으로 적분 → *그림자가 들어간 밝기*(diffuse). 반사광(specular)은 가림을 쓰지 않음.
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
      - ③에서 가림 지도를 숫자 16개로 줄이면, "가려짐 ↔ 보임"이 급하게 바뀌는 경계가 부드럽게 뭉개짐.
      - 광원이 크면 넓은 범위를 평균하므로 티가 덜 남.
      - 광원이 작고 경계 근처에 있으면 "얼마나 가려졌나"를 크게 틀림 → 그림자가 흐려지거나 엉뚱한 곳이 어두워짐.
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
  압축 방식을 SH 대신 *wavelet*으로 바꾸기 (Ng et al. 2003/2004).
  wavelet은 신호를 크기가 다른 *블록 조각*으로 나눠, 중요한 조각만 골라 저장. 경계처럼 급한 변화에 적절할 수 있음.

  #v(0.5em)
  #grid(
    columns: (1fr, 1fr, 1fr),
    column-gutter: 0.8cm,
    callout[
      #tag[A] *믿을 수 있는 정답인지*
      #v(0.2em)
      #note[오차를 재려면 "압축하지 않은 정답"이 필요하다. 이 정답 계산 자체가 맞는지부터.]
    ],
    callout[
      #tag[B] *압축이 원인인지*
      #v(0.2em)
      #note[현재 코드에는 다른 오차원도 있다. 그것들을 고친 뒤에도 남는 오차가 대부분 "16개로 요약"에서 오는지.]
    ],
    callout[
      #tag[C] *wavelet이 확실히 나은가?*
      #v(0.2em)
      #note[같은 저장 공간을 줬을 때 wavelet의 오차가 SH보다 *2배 이상* 작은지.]
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
    columns: (2fr, 1fr),
    column-gutter: 1.2cm,
    [
      #table(
        columns: (auto, 1fr),
        align: (left + top, left + top),
        table.hline(stroke: 0.6pt + rule),
        text(fill: muted)[장면], [lego (Gaussian 97.5만 개 중 표면 점 4만 개 평가)],
        table.hline(stroke: 0.6pt + rule),
        text(fill: muted)[조명],
        [균일한 하늘 + 원판 광원 1개. 크기 2°, 5°, 10°, 30° × 방향 3개\ #note[(참고: 태양은 약 0.5°)]],
        table.hline(stroke: 0.6pt + rule),
        text(fill: muted)[정답], [압축 없이 방향 약 2.5만 개 각각에서 그림자맵을 그려 직접 계산],
        table.hline(stroke: 0.6pt + rule),
        text(fill: muted)[비교], [정답에서 한 요소만 바꿈 
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
#slide(kicker: "방법 · 지표와 비교 대상", title: "실험 설계: 한 번에 한 요소만 바꿔서 비교")[
  #let vis-metric = box(width: 15.5cm, height: 5.4cm, {
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
      #legend(((name: "정답", color: ink), (name: "어떤 방식의 추정", color: c-blue)))
      #vis-metric
      #callout[
        오차 = 반그림자 영역에서의 평균 |추정 − 정답| ÷ 밝은 곳의 평균 밝기
      ]
      #note[0.2 = "그림자 경계에서 평균적으로 밝은 곳 밝기의 20%만큼 틀린다". 작을수록 좋다.]
    ],
    [
      *비교*
      #v(0.2em)
      #set text(size: 13pt)
      #table(
        columns: (1fr, auto),
        align: (left + top, left + top),
        table.hline(stroke: 0.6pt + rule),
        [현재 TranSplat 코드 그대로], tag[B],
        table.hline(stroke: 0.6pt + rule),
        [현재 코드에서 정답 계산과 같은 수정만 적용], tag[B],
        table.hline(stroke: 0.6pt + rule),
        [정답에서 SH 압축만 추가\ #note[(16 → 100 → 256개)]], tag[B C],
        table.hline(stroke: 0.6pt + rule),
        [정답에서 wavelet 압축만 추가\ #note[(8 → 256개)]], tag[C],
        table.hline(stroke: 0.6pt + rule),
        [광원만 따로 그림자맵으로 직접 계산], tag(color: c-aqua)[대안],
        table.hline(stroke: 0.6pt + rule),
      )
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
        - 적은 개수로는 계단처럼 깨짐 (SH는 부드럽게 뭉갬)
        - → 결국 둘 다 비슷한 오차 발생
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

      #v(0.3em)
      #callout(color: c-aqua)[
        #set text(size: 12.5pt)
        *데모로 확인* (`demo.html`): 표면 기울기 0°(경계가 블록 격자와 나란함)에서는 wavelet이 같은 개수 기준 2\~2.7배 나음. 25° 이상 기울이면 이점이 사라짐.
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
        node(color: c-orange)[*작은 광원* #note[(해, 조명)]], node(color: c-aqua)[*나머지* #note[(하늘, 벽 반사)]],
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
        tag[A], [정답 계산의 문제 5개를 찾아 고침 (그중 3개는 기존 TranSplat에도 있음)],
        table.hline(stroke: 0.6pt + rule),
        tag[B], [예. 4가지 수정 후 남는 오차는 대부분 압축],
        table.hline(stroke: 0.6pt + rule),
        tag(color: c-orange)[C], [아니오. 같은 메모리면 wavelet ≈ SH],
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
      *한계 (이 결과를 해석할 때 주의)*
      #set text(size: 13.5pt)
      - 합성 조명(균일한 하늘 + 원판)만 씀. 실제 환경맵은 광원을 떼어낸 나머지도 복잡할 수 있음.
      - 장면이 lego 하나뿐.
      - 2° 광원은 정답 자체의 불확실성(0.09)이 오차와 비슷한 크기라 추세만 봄.
      - 광원 분리 2048px 수치는 같은 해상도 정답과 비교한 것이라 낙관적 (실제로는 0.02\~0.09 더 클 수 있음).
      - wavelet에는 여러 종류(Haar, Daubechies 같은 부드러운 wavelet, 구면 wavelet 등)가 있는데 가장 단순한 Haar만 비교함. 다만 참고한 triple product 방식(Ng 2004)이 Haar 기준이라 실제 후보도 Haar.

      #v(0.3em)
      *의견을 듣고 싶은 것*
      - 판단 기준(같은 메모리에서 2배)이 적절한지
      - 광원 분리 방향에 놓친 함정이 없는지
      - 재검증에 쓸 실제 HDR 환경맵 추천
    ],
  )
]
