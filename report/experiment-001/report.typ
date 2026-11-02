// 실험 001: 고주파 그림자 개선 방향 검토 (wavelet 진행 여부)
// 컴파일: typst compile report.typ  (한글 폰트: Pretendard 권장, 없으면 아래 목록 순서로 대체)

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
      grid(columns: (1fr, auto), [실험 001 · 고주파 그림자 개선 방향 검토], [#n])
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
  if kicker != none { text(size: 12pt, fill: c-blue, weight: "semibold", kicker); v(0.15em) }
  if title != none { text(size: 23pt, weight: "bold", title); v(0.45em) }
  body
}
#let note(body) = text(size: 11.5pt, fill: ink2, body)
#let callout(body, color: c-blue) = block(
  width: 100%, breakable: false, inset: (x: 0.9em, y: 0.7em), radius: 6pt,
  fill: color.lighten(90%), stroke: (left: 3pt + color), body,
)
#let tag(body, color: c-blue) = box(
  inset: (x: 0.45em, y: 0.2em), radius: 4pt, fill: color.lighten(85%),
  text(size: 12pt, weight: "semibold", fill: color.darken(25%), body),
)

#let fmt(v, d: 2) = {
  let s = str(calc.round(v, digits: d))
  let p = s.split(".")
  if p.len() == 1 { s + "." + "0" * d } else { s + "0" * (d - p.at(1).len()) }
}

// Grouped bar chart. data: one array per series, one value per category.
#let bars(cats, series, data, ymax: 0.6, ticks: (0, 0.2, 0.4, 0.6), h: 6.2cm, w: 15cm,
  refs: (), xlabel: none, ylabel: none) = {
  let lm = 1.3cm
  let n = cats.len()
  let m = series.len()
  let gw = w / n
  let bw = gw * 0.78 / m
  let y(v) = h - h * v / ymax
  let rm = if refs.len() > 0 { 2.7cm } else { 0cm }
  box(width: lm + w + rm, height: h + 1.2cm, {
    for t in ticks {
      place(top + left, dx: lm, dy: y(t), line(length: w, stroke: 0.6pt + rule))
      place(top + left, dx: 0cm, dy: y(t) - 0.45em,
        box(width: lm - 0.25cm, align(right, text(size: 11pt, fill: muted, fmt(t, d: 1)))))
    }
    for (j, c) in cats.enumerate() {
      for (i, s) in series.enumerate() {
        let v = data.at(i).at(j)
        let x0 = lm + gw * j + gw * 0.11 + bw * i
        place(top + left, dx: x0, dy: y(calc.min(v, ymax)),
          rect(width: bw - 2pt, height: h * calc.min(v, ymax) / ymax, fill: s.color,
            radius: (top-left: 3pt, top-right: 3pt)))
        place(top + left, dx: x0 - 0.3cm, dy: y(calc.min(v, ymax)) - 0.5cm,
          box(width: bw - 2pt + 0.6cm, align(center, text(size: 9.5pt, fill: ink2, fmt(v)))))
      }
      place(top + left, dx: lm + gw * j, dy: h + 0.18cm,
        box(width: gw, align(center, text(size: 13pt, c))))
    }
    for r in refs {
      place(top + left, dx: lm, dy: y(r.at(0)),
        line(length: w, stroke: (paint: ink2, thickness: 1pt, dash: "dashed")))
      place(top + left, dx: lm + w + 0.15cm, dy: y(r.at(0)) - 0.5em,
        box(width: rm - 0.15cm, text(size: 10pt, fill: ink2, weight: "semibold", r.at(1))))
    }
    place(top + left, dx: lm, dy: h, line(length: w, stroke: 0.8pt + ink2))
    if xlabel != none {
      place(top + left, dx: lm, dy: h + 0.72cm, box(width: w, align(center, text(size: 11pt, fill: muted, xlabel))))
    }
  })
}
#let legend(series) = {
  set text(size: 12.5pt)
  series.map(s => box[#box(width: 0.8em, height: 0.8em, radius: 2pt, fill: s.color, baseline: 0.1em) #h(0.3em)#s.name]).join(h(1.1em))
}

// ---------------------------------------------------------------------------
// 1. 표지
// ---------------------------------------------------------------------------
#{
  set page(footer: none)
  v(2.2cm)
  text(size: 13pt, fill: c-blue, weight: "semibold")[실험 001 · 2026-11-02]
  v(0.3em)
  text(size: 38pt, weight: "bold")[날카로운 그림자,\ wavelet이 답일까?]
  v(0.6em)
  text(size: 18pt, fill: ink2)[TranSplat 그림자 개선 방향을 정하기 위한 측정 결과]
  v(1fr)
  grid(columns: (auto, 1fr), column-gutter: 1em, row-gutter: 0.5em,
    text(size: 13pt, fill: muted)[결론 미리보기],
    text(size: 13pt)[같은 저장 공간이면 wavelet은 지금 방식(SH)보다 낫지 않았다. 대신 간단한 수정과 "광원 분리"가 훨씬 효과적이다.],
    text(size: 13pt, fill: muted)[데모],
    text(size: 13pt)[`demo.html` (압축 방식에 따라 그림자가 어떻게 뭉개지는지 직접 조작)],
  )
  v(0.6cm)
}

// ---------------------------------------------------------------------------
// 2. 배경
// ---------------------------------------------------------------------------
#slide(kicker: "배경", title: "TranSplat은 그림자를 어떻게 다시 계산하나")[
  #grid(columns: (1.05fr, 1fr), column-gutter: 1.2cm,
    [
      3D Gaussian으로 복원한 물체에 *새 조명*을 입히는 방법.

      + *미리 계산:* 각 Gaussian(점)마다 "하늘의 어느 방향이 물체에 가려져 있나"를 구한다.
      + *요약 저장:* 이 가림 정보를 점마다 *숫자 16개*(SH, 구면 위의 저주파 성분)로 줄여 저장한다.
      + *다시 조명:* 새 조명도 같은 방식으로 요약한 뒤 둘을 곱해 밝기를 계산한다.

      #v(0.4em)
      #callout(color: c-orange)[
        *문제:* 해나 스포트라이트처럼 *작고 강한 광원*의 그림자가 흐리고 옅어진다.
        숫자 16개로는 "가려짐 ↔ 보임"이 급하게 바뀌는 경계를 담을 수 없기 때문.
      ]
    ],
    [
      #let W = 12.5cm
      #let H = 3.4cm
      #let a = 2.0
      #let b = 3.1
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
        place(top + left, curve(stroke: 2.5pt + ink,
          curve.move((0pt, py(1))), curve.line((px(a), py(1))), curve.line((px(a), py(0))),
          curve.line((px(b), py(0))), curve.line((px(b), py(1))), curve.line((W, py(1)))))
        place(top + left, curve(stroke: 2pt + c-orange,
          curve.move((0pt, py(f(0)))), ..pts.slice(1).map(x => curve.line((px(x), py(f(x)))))))
        place(top + left, dx: px(a) + 0.15cm, dy: py(0) + 0.15cm, text(size: 11pt, fill: ink2)[가림막 방향])
        place(top + left, dy: H + 0.25cm, text(size: 11pt, fill: muted)[방향 →])
      })
      #legend(((name: "실제 가림", color: ink), (name: "숫자 몇 개로 요약 (경계가 뭉개짐)", color: c-orange)))
      #v(0.6em)
      #note[작은 광원이 경계 근처에 있으면, 요약본으로는 "얼마나 가려졌나"를 크게 틀린다. 그림자가 흐려지거나 엉뚱한 곳이 어두워진다.]
    ],
  )
]

// ---------------------------------------------------------------------------
// 3. 질문
// ---------------------------------------------------------------------------
#slide(kicker: "질문", title: "wavelet으로 바꾸기 전에 확인할 것 세 가지")[
  후보 해결책: 요약 방식을 SH 대신 *wavelet*으로 바꾸기 (Ng et al. 2003/2004).
  wavelet은 신호를 크기가 다른 *블록 조각*으로 나눠, 중요한 조각만 골라 저장한다. 경계처럼 급한 변화에 강하다고 알려져 있다.

  #v(0.5em)
  #grid(columns: (1fr, 1fr, 1fr), column-gutter: 0.8cm,
    callout[
      #tag[A] *정답을 믿을 수 있나?*
      #v(0.2em)
      #note[오차를 재려면 "압축하지 않은 정답"이 필요하다. 이 정답 계산 자체가 맞는지부터.]
    ],
    callout[
      #tag[B] *주범이 정말 압축인가?*
      #v(0.2em)
      #note[현재 코드에는 다른 오차원도 있다. 쉬운 것들을 고친 뒤에도 남는 오차가 대부분 "16개로 요약"에서 오는지.]
    ],
    callout[
      #tag[C] *wavelet이 확실히 나은가?*
      #v(0.2em)
      #note[같은 저장 공간을 줬을 때 wavelet의 오차가 SH보다 *2배 이상* 작은지.]
    ],
  )
  #v(0.7em)
  #callout(color: c-aqua)[
    *판단 규칙:* B와 C가 모두 "예"일 때만 wavelet 구현으로 간다. 하나라도 "아니오"면 방향을 바꾼다.
  ]
]

// ---------------------------------------------------------------------------
// 4. 실험 설계
// ---------------------------------------------------------------------------
#slide(kicker: "방법", title: "실험 설계: 한 번에 한 요소만 바꿔서 비교")[
  #grid(columns: (1fr, 1fr), column-gutter: 1.2cm,
    [
      #table(columns: (auto, 1fr), align: (left + top, left + top),
        table.hline(stroke: 0.6pt + rule),
        text(fill: muted)[장면], [lego (Gaussian 97.5만 개 중 표면 점 4만 개 평가)],
        table.hline(stroke: 0.6pt + rule),
        text(fill: muted)[조명], [균일한 하늘 + 원판 광원 1개.\ 크기 2°, 5°, 10°, 30° × 방향 3개\ #note[(참고: 해는 약 0.5°)]],
        table.hline(stroke: 0.6pt + rule),
        text(fill: muted)[정답], [압축 없이 방향 약 2.5만 개 각각에서\ 그림자맵을 그려 직접 계산],
        table.hline(stroke: 0.6pt + rule),
        text(fill: muted)[비교], [정답에서 한 요소만 바꿈\ → 그 요소가 만드는 오차만 분리],
        table.hline(stroke: 0.6pt + rule),
      )
    ],
    [
      *지표: 그림자 경계 오차*
      #v(0.2em)
      #callout[
        경계(반쯤 가려진 영역)에서의 평균 밝기 오차 ÷ 밝은 곳의 평균 밝기
      ]
      #note[0.2 = "그림자 경계에서 평균적으로 밝은 곳 밝기의 20%만큼 틀린다". 작을수록 좋다.]

      #v(0.6em)
      *비교한 것*
      - 현재 TranSplat 코드 그대로
      - 쉬운 수정만 적용한 버전
      - SH 개수만 바꾼 버전 (16 → 100 → 256개)
      - wavelet 개수만 바꾼 버전 (8 → 256개)
      - 광원만 따로 그림자맵으로 처리한 버전
    ],
  )
]

// ---------------------------------------------------------------------------
// 5. A: 정답 검증
// ---------------------------------------------------------------------------
#slide(kicker: "결과 A · 정답 검증", title: "처음엔 정답 계산부터 틀려 있었다")[
  #grid(columns: (1.35fr, 1fr), column-gutter: 1cm,
    [
      #set text(size: 13pt)
      #table(columns: (1fr, 1fr), align: left + top,
        table.header(text(fill: muted)[발견한 문제], text(fill: muted)[고친 방법]),
        table.hline(stroke: 0.6pt + rule),
        [멀리 떠 있는 잡티 때문에 장면 크기를 9배 크게 잡음 → 그림자맵이 너무 거칠다], [잡티를 뺀 99.5% 범위로 크기 계산],
        table.hline(stroke: 0.6pt + rule),
        [표면의 앞/뒤 방향이 절반쯤 뒤집혀 있음], [학습 카메라가 본 쪽을 앞으로],
        table.hline(stroke: 0.6pt + rule),
        [표면 아래 겹겹이 쌓인 점들이 "가려짐"으로 판정], [카메라에 실제로 보이는 표면 점만 평가],
        table.hline(stroke: 0.6pt + rule),
        [점이 자기 자신을 그림자로 착각], [표면에서 살짝 띄워서 판정],
        table.hline(stroke: 0.6pt + rule),
        [잡티가 카메라 앞을 막아 *한 방향 전체가 검게* 나옴], [그림자 계산에서 잡티 제외],
        table.hline(stroke: 0.6pt + rule),
      )
      #note[검증: 정답을 아는 단순 장면(평면 위 구)에서 판정 오류 2\~3%. 그림자맵 해상도를 2배로 올렸을 때 결과가 바뀌는 정도: 2° 광원 0.09, 10° 이상 0.04 이하.]
    ],
    [
      *점이 하늘을 얼마나 보나* #note[(0\~1, 정상적인 바깥 표면이면 0.3보다 훨씬 큼)]
      #v(0.3em)
      #bars(("처음", "4개 수정", "잡티까지"), ((name: "중앙값", color: c-blue),),
        ((0.079, 0.395, 0.655),), ymax: 0.8, ticks: (0, 0.2, 0.4, 0.6, 0.8), h: 3.8cm, w: 9cm)
      #callout(color: c-orange)[
        중간 결과에서 wavelet이 *최대 2.9배* 좋아 보였는데, 마지막 문제(검게 막힌 방향) 때문이었다. 고치자 사라졌다.
      ]
    ],
  )
]

// ---------------------------------------------------------------------------
// 6. B: 오차 분해
// ---------------------------------------------------------------------------
#slide(kicker: "결과 B · 오차는 어디서 오나", title: "쉬운 수정으로 절반, 남은 오차는 압축 때문")[
  #let series = (
    (name: "현재 코드", color: c-base),
    (name: "쉬운 수정 후", color: c-blue),
    (name: "SH 16개 압축만", color: c-orange),
    (name: "SH 100개 압축만", color: c-aqua),
  )
  #grid(columns: (1.5fr, 1fr), column-gutter: 0.9cm,
    [
      #legend(series)
      #v(0.2em)
      #bars(("2°", "5°", "10°", "30°"), series,
        (
          (0.459, 0.537, 0.346, 0.260),
          (0.216, 0.213, 0.199, 0.153),
          (0.176, 0.177, 0.165, 0.114),
          (0.134, 0.126, 0.099, 0.028),
        ), ymax: 0.6, h: 5.6cm, w: 13cm, xlabel: [광원 크기 · 세로축: 그림자 경계 오차 (낮을수록 좋음)])
    ],
    [
      #callout[
        *쉬운 수정*으로 오차가 *2\~2.5배* 줄어든다.
        #note[잡티 제외, 장면 크기 보정, 조명 요약을 정확히, 흐린 판정 대신 0/1 판정]
      ]
      #callout(color: c-orange)[
        그 뒤 남는 오차는 대부분 *SH 16개 압축* 몫이다 (주황 ≈ 파랑). → B: *예*
      ]
      #callout(color: c-aqua)[
        숫자를 6배(100개)로 늘려도 작은 광원 오차는 *25%만* 준다. SH를 늘리는 건 비효율적.
      ]
    ],
  )
]

// ---------------------------------------------------------------------------
// 7. C: wavelet vs SH
// ---------------------------------------------------------------------------
#slide(kicker: "결과 C · wavelet vs SH", title: "같은 메모리면 wavelet은 SH와 비슷하다")[
  #let series = (
    (name: "같은 개수 (둘 다 256개)", color: c-blue),
    (name: "같은 메모리 (wavelet 128개 vs SH 256개)", color: c-orange),
  )
  #grid(columns: (1.5fr, 1fr), column-gutter: 0.9cm,
    [
      #legend(series)
      #v(0.2em)
      #bars(("2°", "5°", "10°", "30°"), series,
        ((1.12, 1.59, 1.72, 0.81), (0.94, 1.05, 1.01, 0.60)),
        ymax: 2.4, ticks: (0, 0.5, 1.0, 1.5, 2.0), h: 5.6cm,
        refs: ((1.0, "1 = 둘이 같음"), (2.0, "2 = 진행 기준")), w: 11cm,
        xlabel: [광원 크기 · 세로축: SH 오차 ÷ wavelet 오차 (1보다 크면 wavelet이 나음)])
    ],
    [
      #callout[
        wavelet은 "어느 조각인지" 위치도 저장해야 해서, 같은 메모리면 *개수가 절반*이다.
      ]
      #callout(color: c-orange)[
        같은 메모리 기준 *0.6\~1.05배*. 같은 개수로 봐도 최대 1.7배로 *2배 기준에 못 미친다*. → C: *아니오*
      ]
      #note[16개, 64개에서도 0.9\~1.4배. 방향 해상도를 2배로 올려 다시 재도 비율 변화 ±0.1 이내 (해상도 탓이 아님).]
    ],
  )
]

// ---------------------------------------------------------------------------
// 8. 해석
// ---------------------------------------------------------------------------
#slide(kicker: "해석", title: "왜 wavelet이 이기지 못했나")[
  #grid(columns: (1fr, auto), column-gutter: 1.2cm,
    [
      *1. 경계가 곡선이면 블록이 많이 든다* \
      #note[wavelet은 정사각형 블록으로 그림을 그린다. 가림 경계(지평선, 둥근 가림막)가 기울거나 휘어 있으면, 경계가 지나가는 칸마다 조각이 필요하다. 적은 개수로는 계단처럼 깨지고, SH는 부드럽게 뭉갠다. 결국 둘 다 비슷하게 틀린다.]

      #v(0.4em)
      *2. 우리는 점마다 저장 예산이 아주 작다* \
      #note[Gaussian 약 100만 개 × 수십 개 숫자. wavelet이 강했던 원 논문은 꼭짓점 수만 개에 점마다 훨씬 많은 계수를 쓰고, 주로 *조명 쪽*을 골라 압축했다. 우리 상황은 점 쪽을 적은 개수로 압축해야 한다.]

      #v(0.4em)
      *3. 큰 광원(30°)에서는 SH가 오히려 낫다* \
      #note[부드러운 그림자는 SH가 원래 잘 담는다.]

      #v(0.5em)
      #callout(color: c-aqua)[
        *데모로 확인* (`demo.html`): 표면 기울기 0°(경계가 블록 격자와 나란함)에서는 wavelet이 같은 개수 기준 2\~2.7배 낫다. 25° 이상 기울이면 이점이 사라진다.
      ]
    ],
    [
      #let n = 16
      #let s = 0.42cm
      #let cx = 8.3
      #let cy = 7.6
      #let r = 5.4
      #let inside(x, y) = calc.pow(x - cx, 2) + calc.pow(y - cy, 2) < r * r
      #let cells = ()
      #let edge = 0
      #for j in range(n) {
        for i in range(n) {
          let k = (inside(i, j), inside(i + 1, j), inside(i, j + 1), inside(i + 1, j + 1)).filter(v => v).len()
          if k > 0 and k < 4 { edge += 1 }
        }
      }
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
        #box(width: 0.8em, height: 0.8em, fill: c-orange.lighten(35%), baseline: 0.1em) 경계가 지나는 칸 #edge 개. 이 칸마다 조각이 필요하다.
      ])
    ],
  )
]

// ---------------------------------------------------------------------------
// 9. 대안
// ---------------------------------------------------------------------------
#slide(kicker: "대안", title: "작은 광원만 따로 처리하기 (광원 분리)")[
  #grid(columns: (1fr, 1.15fr), column-gutter: 1cm,
    [
      #set text(size: 13pt)
      #let node(body, color: c-blue) = box(width: 100%, inset: (x: 0.6em, y: 0.5em), radius: 5pt,
        fill: color.lighten(88%), stroke: 0.8pt + color.lighten(40%), body)
      #node(color: c-base)[*새 환경맵*]
      #align(center, text(fill: muted)[↓ 밝고 작은 부분을 떼어냄])
      #grid(columns: (1fr, 1fr), column-gutter: 0.4cm, row-gutter: 0.3cm,
        node(color: c-orange)[*작은 광원*\ #note[해, 조명]],
        node(color: c-aqua)[*나머지*\ #note[하늘, 벽 반사]],
        node(color: c-orange)[다시 조명할 때 그림자맵으로 *직접* 계산],
        node(color: c-aqua)[기존 SH 16개 그대로\ #note[부드러운 빛이라 뭉개져도 티가 덜 남]],
      )
      #align(center, text(fill: muted)[↓ 더함])
      #node(color: c-base)[*최종 밝기*]
    ],
    [
      #set text(size: 12.5pt)
      #let hl(body) = text(weight: "bold", fill: c-blue.darken(10%), body)
      #table(columns: (1fr, auto, auto, auto, auto), align: (left, right, right, right, right),
        table.header(text(fill: muted)[그림자 경계 오차], text(fill: muted)[2°], text(fill: muted)[5°], text(fill: muted)[10°], text(fill: muted)[30°]),
        table.hline(stroke: 0.6pt + rule),
        [현재 코드], [0.46], [0.54], [0.35], [0.26],
        [쉬운 수정 후], [0.22], [0.21], [0.20], [0.15],
        [SH 100개 (압축만)], [0.13], [0.13], [0.10], [0.03],
        table.hline(stroke: 0.6pt + rule),
        [광원 분리 · 1024px, 샘플 16], [0.13], [0.10], [0.07], [0.05],
        [광원 분리 · 2048px, 샘플 16], hl[0.04], hl[0.04], hl[0.03], hl[0.03],
        table.hline(stroke: 0.6pt + rule),
      )
      #v(0.3em)
      #note[px = 광원 방향 그림자맵 해상도, 샘플 = 광원 안에서 쏘는 방향 수. 샘플 1개(딱딱한 그림자)는 0.20\~0.27로 오히려 나쁘다 → 부드러운 그림자용 샘플이 필요.]
      #v(0.3em)
      #callout[
        작은 광원(2\~10°)에서 2048px 광원 분리는 SH 100개보다 *약 3배*, 쉬운 수정 후보다 *약 5배* 정확하다. 30°에서는 비슷하다.
      ]
    ],
  )
]

// ---------------------------------------------------------------------------
// 10. 결론
// ---------------------------------------------------------------------------
#slide(kicker: "정리", title: "결론과 다음 단계")[
  #grid(columns: (1fr, 1fr), column-gutter: 1cm,
    [
      *결론*
      #table(columns: (auto, 1fr), align: (left + top, left + top),
        table.hline(stroke: 0.6pt + rule),
        tag[A], [정답 계산을 검증하고 고침 (문제 5개 발견)],
        table.hline(stroke: 0.6pt + rule),
        tag[B], [예. 쉬운 수정 후 남는 오차는 대부분 압축],
        table.hline(stroke: 0.6pt + rule),
        tag(color: c-orange)[C], [아니오. 같은 메모리면 wavelet ≈ SH],
        table.hline(stroke: 0.6pt + rule),
      )
      #callout(color: c-orange)[
        *wavelet 구현은 보류.* 대신 *쉬운 수정 + 광원 분리*로 방향을 바꾸는 것을 제안.
      ]
      *다음 단계*
      + 쉬운 수정을 본 코드에 반영
      + 환경맵에서 광원 추출 + 그림자맵 직접 계산 구현
      + 실제 HDR 환경맵(실내, 해가 있는 야외)으로 재검증
    ],
    [
      *한계 (이 결과를 해석할 때 주의)*
      - 합성 조명(균일한 하늘 + 원판)만 썼다. 실제 환경맵은 광원을 떼어낸 나머지도 복잡할 수 있다.
      - 장면이 lego 하나뿐이다.
      - 2° 광원은 정답 자체의 불확실성(0.09)이 오차와 비슷한 크기라 추세만 본다.
      - 광원 분리 2048px 수치는 같은 해상도 정답과 비교한 것이라 낙관적이다 (실제로는 0.02\~0.09 더 클 수 있음).
      - wavelet은 가장 단순한 Haar로만 비교했다.

      #v(0.4em)
      #callout(color: c-aqua)[*의견을 듣고 싶은 것:* 판단 기준(2배)이 적절한지, 광원 분리 방향에 놓친 함정이 없는지.]
    ],
  )
]

// ---------------------------------------------------------------------------
// 부록
// ---------------------------------------------------------------------------
#slide(kicker: "부록", title: "용어와 재현 방법")[
  #set text(size: 12.5pt)
  #grid(columns: (1fr, 1fr), column-gutter: 1cm,
    [
      *용어*
      #table(columns: (auto, 1fr), align: (left + top, left + top),
        table.hline(stroke: 0.6pt + rule),
        [SH], [구면 조화 함수. 구면 위 함수의 "저주파 성분". 숫자 16개 = 차수 3까지],
        [wavelet (Haar)], [크기가 다른 사각 블록의 합으로 표현. 큰 값의 조각만 골라 저장],
        [그림자맵], [광원 쪽에서 본 깊이 이미지. 더 멀리 있으면 가려진 것],
        [반그림자], [광원 일부만 가려져 반쯤 어두운 경계 영역],
        [잡티 (floater)], [학습 중 허공에 생긴 Gaussian],
        table.hline(stroke: 0.6pt + rule),
      )
    ],
    [
      *재현* #note[(브랜치 `claude/shadow-wavelet-study`, RTX 5080에서 약 45분)]
      #v(0.2em)
      #set text(size: 11pt)
      ```sh
      python scripts/shadow_frequency_study.py \
        --ply sample/outputs/lego/point_cloud/iteration_30000/point_cloud.ply \
        --output-dir .../shadow_frequency_study_v3 --num-eval-points 40000
      python scripts/shadow_frequency_study.py --ply ... \
        --output-dir .../shadow_frequency_study_c128 \
        --num-eval-points 20000 --cube-res 128 --only-compact --chunk 512
      python scripts/shadow_hybrid_check.py --ply ... \
        --study-dir .../shadow_frequency_study_v3
      ```
      #set text(size: 13pt)
      결과: `sample/outputs/lego/point_cloud/iteration_30000/` 아래 `shadow_frequency_study_v3/results.md`, `shadow_frequency_study_c128/results.md`, `shadow_frequency_study_v3/hybrid_check.md`
    ],
  )
]
