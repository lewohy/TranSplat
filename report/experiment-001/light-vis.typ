// 실험 조명 설명 그림: 광원 크기(각지름), 정답 계산의 방향 샘플(하늘 / 원판 64개), 하늘 부분 밝기와 AO. report.typ가 import해서 쓴다.
#import "@preview/cetz:0.4.2"
#import "theme.typ": *

#let c-sun = rgb("#f5b83d")

// 한 점에서 본 원판 광원의 크기 = 원판 양 끝으로 그은 두 선 사이의 각
#let disc-angle = cetz.canvas(length: 1cm, {
  import cetz.draw: *
  let el = 52deg
  let dist = 5.6
  let rs = 0.75
  let half = calc.asin(rs / dist)
  let at(a, r) = (r * calc.cos(a), r * calc.sin(a))
  let c = at(el, dist)
  // 원뿔 (점 → 원판)
  line((0, 0), at(el - half, dist * calc.cos(half)), at(el + half, dist * calc.cos(half)), close: true,
    fill: c-sun.lighten(70%), stroke: none)
  line((0, 0), at(el - half, dist * calc.cos(half)), stroke: 0.8pt + c-sun.darken(25%))
  line((0, 0), at(el + half, dist * calc.cos(half)), stroke: 0.8pt + c-sun.darken(25%))
  circle(c, radius: rs, fill: c-sun, stroke: none)
  content((c.at(0) + rs + 0.15, c.at(1) + 0.2), anchor: "west", text(size: 11pt)[원판 광원])
  content((c.at(0) + rs + 0.15, c.at(1) - 0.35), anchor: "west", text(size: 9.5pt, fill: muted)[아주 멀리 (환경맵의 일부)])
  // 각 표시
  arc((0, 0), start: el - half, stop: el + half, radius: 1.9, anchor: "origin", stroke: 1.4pt + c-orange)
  line(at(el + half, 1.9), at(el + half + 18deg, 2.7), stroke: 0.6pt + c-orange)
  content(at(el + half + 18deg, 2.75), anchor: "south-east", text(size: 11pt, fill: c-orange.darken(15%))[*광원 크기* = 이 각])
  // 고도
  line((0, 0), (2.4, 0), stroke: (paint: muted, thickness: 0.6pt, dash: "dashed"))
  arc((0, 0), start: 0deg, stop: el, radius: 1.0, anchor: "origin", stroke: 0.7pt + muted)
  content(at(el / 2, 1.3), text(size: 9.5pt, fill: muted)[고도])
  // 표면과 점
  rect((-1.6, -0.35), (3.6, 0), fill: c-plate, stroke: 0.4pt + c-plate.darken(30%))
  circle((0, 0), radius: 0.11, fill: c-lego, stroke: 0.6pt + c-lego.darken(30%))
  content((0, -0.7), text(size: 10pt, fill: ink2)[평가하는 점 (Gaussian)])
})

// 원판 안 방향 64개 (실험의 cap_directions와 같은 나선 배치를 위에서 본 모습)
#let disc-dots(n: 64, R: 1.0, cut: none, dot: 0.055, label: none) = cetz.canvas(length: 1cm, {
  import cetz.draw: *
  circle((0, 0), radius: R, fill: c-sun.lighten(75%), stroke: 0.8pt + c-sun.darken(10%))
  let golden = calc.pi * (3 - calc.sqrt(5))
  for i in range(n) {
    let r = R * 0.94 * calc.sqrt((i + 0.5) / n)
    let p = (r * calc.cos(golden * i * 1rad), r * calc.sin(golden * i * 1rad))
    let hidden = cut != none and p.at(0) > cut * R
    circle(p, radius: dot, fill: if hidden { ink } else { c-sun.darken(20%) }, stroke: none)
  }
  if cut != none {
    // 가림막: 원판 오른쪽을 덮음
    rect((calc.max(cut, -1.08) * R, -R * 1.08), (R * 1.08, R * 1.08), fill: luma(120).transparentize(55%), stroke: none)
    if cut > -1 { line((cut * R, -R * 1.08), (cut * R, R * 1.08), stroke: 1.2pt + ink2) }
  }
  if label != none { content((0, -R - 0.35), label) }
})

#let visible-count(n, cut) = {
  if cut == none { return n }
  let golden = calc.pi * (3 - calc.sqrt(5))
  range(n).filter(i => calc.sqrt((i + 0.5) / n) * 0.94 * calc.cos(golden * i * 1rad) <= cut).len()
}

#let sampling-slide = [
#slide(kicker: "방법 · 정답 계산", id: "sampling", title: "정답 밝기: 빛이 오는 방향을 잘게 나눠 하나씩 판정")[
  #grid(
    columns: (1fr, 1.05fr),
    column-gutter: 1.1cm,
    [
      #set text(size: 13pt)
      한 점의 밝기 = 들어오는 빛을 *방향별로 더한 것*. 정답 계산은 방향을 잘게 나눠, 방향마다 그림자맵(2048px)으로 *보임 1 / 가림 0*을 판정해서 더함.
      #v(0.4em)
      #table(
        columns: (auto, 1fr),
        align: (left, left),
        table.hline(stroke: 0.6pt + rule),
        text(fill: muted)[빛], text(fill: muted)[나눈 방향],
        table.hline(stroke: 0.6pt + rule),
        [균일한 하늘], [약 2.5만 개 (cube map 64×64×6면)],
        [원판 광원], [*원판 안에 64개* (오른쪽 그림의 점)],
        table.hline(stroke: 0.6pt + rule),
      )
      #v(0.3em)
      $ E_"광원" = "광원 세기" times "원판 넓이" times 1/64 sum_(k=1)^64 "보임"_k times cos theta_k $
      #note[$theta_k$: 표면 방향(normal)과 $k$번째 방향 사이의 각. 하늘 부분도 같은 방식으로 2.5만 방향을 더함 (#pref("ao-def")). $E$ = 하늘 + 광원.]
      #note[64방향은 원판 넓이를 64등분하도록 나선형으로 배치. 가림 판정은 ②와 달리 흐리게(ESM+PCF) 하지 않은 0/1 (기준은 #pref("judge")).]
    ],
    [
      #align(center)[
        #disc-dots(R: 1.9, cut: 0.25, dot: 0.07)
        #v(-0.2em)
        #text(size: 12pt)[점에서 광원 쪽을 올려다본 모습 (#pref("conditions") 원뿔의 단면) \ 64방향 중 #text(fill: c-sun.darken(30%))[*#visible-count(64, 0.25)개 보임*], 나머지는 가림막(회색)에 가림]
      ]
      #v(0.5em)
      #text(size: 12.5pt)[*보이는 개수로 점의 영역을 나눔* (점마다 따로 판정)]
      #v(0.2em)
      #grid(
        columns: (1fr, 1fr, 1fr),
        align: center,
        disc-dots(R: 0.75, dot: 0.035),
        disc-dots(R: 0.75, cut: 0.25, dot: 0.035),
        disc-dots(R: 0.75, cut: -1.0, dot: 0.035),
        [#text(size: 11.5pt)[*밝은 곳 L*] \ #text(size: 10.5pt, fill: muted)[63\~64개 보임]],
        [#text(size: 11.5pt, fill: c-orange.darken(15%))[*반그림자 P*] \ #text(size: 10.5pt, fill: muted)[2\~62개 보임]],
        [#text(size: 11.5pt)[*그림자*] \ #text(size: 10.5pt, fill: muted)[0\~1개 보임]],
      )
      #note[1개 차이(1/64 ≈ 1.6%)는 잡음으로 보고 경계를 2%, 98%로 둠.]
    ],
  )
]
]

// 하늘 부분 밝기와 AO: 점 위 반구의 방향마다 보임 × cos를 더함 (단면 개념도)
#let ao-fan = cetz.canvas(length: 1cm, {
  import cetz.draw: *
  let R = 3.0
  let ox = 1.2 // 가림막 왼쪽 면
  let oh = 2.0
  arc((0, 0), start: 0deg, stop: 180deg, radius: R, anchor: "origin", stroke: (paint: rule, thickness: 0.8pt, dash: "dashed"))
  for i in range(17) {
    let t = -80deg + i * 10deg // normal(위)에서 잰 각, 오른쪽이 +
    let d = (calc.sin(t), calc.cos(t))
    if t > 0deg and calc.tan(t) > ox / oh {
      // 가림막에 부딪힘
      line((0, 0), (ox, ox / calc.tan(t)), stroke: (paint: c-base.darken(10%), thickness: 0.9pt, dash: "dotted"))
    } else {
      line((0, 0), (d.at(0) * R, d.at(1) * R), stroke: (0.4pt + 3.2pt * calc.cos(t)) + c-blue)
    }
  }
  rect((ox, 0), (ox + 0.35, oh), fill: c-base, stroke: none, radius: 2pt)
  content((ox + 0.5, oh - 0.3), anchor: "west", text(size: 10pt, fill: muted)[가림막])
  // normal
  line((0, 0), (0, R + 0.4), stroke: (paint: ink2, thickness: 0.8pt, dash: "dashed"), mark: (end: ">", fill: ink2))
  content((0.15, R + 0.55), anchor: "west", text(size: 10.5pt, fill: ink2)[normal $n$ ($theta = 0$)])
  rect((-3.4, -0.3), (3.4, 0), fill: c-plate, stroke: 0.4pt + c-plate.darken(30%))
  circle((0, 0), radius: 0.12, fill: c-lego, stroke: 0.6pt + c-lego.darken(30%))
  content((0, -0.65), text(size: 10pt, fill: ink2)[평가하는 점 (Gaussian)])
})

#let sky-slide = [
#slide(kicker: "부록 · 정답 계산", id: "ao-def", title: "하늘 부분 밝기와 AO (가려지지 않은 정도)")[
  #grid(
    columns: (1.15fr, 1fr),
    column-gutter: 1cm,
    [
      #set text(size: 13pt)
      하늘 2.5만 방향(cube map 칸)을 모두 더함:
      $ E_"하늘" = 0.2 times sum_(j=1)^(24576) w_j times "보임"_j times max(cos theta_j, 0) $
      #v(-0.2em)
      #set text(size: 12pt)
      - $0.2$: 하늘 밝기 (모든 방향 같음)
      - $w_j$: 칸 $j$가 하늘에서 차지하는 넓이. cube map 칸은 면 가운데가 모서리보다 약 5배 넓어서 보정. 다 더하면 $4 pi$ (구 전체, 계산은 #pref("cube-weight"))
      - $max(cos theta_j, 0)$: 정면에서 오는 빛은 크게, 비스듬하면 작게, 표면 뒤쪽은 0
      #v(0.3em)
      #callout[
        #set text(size: 12.5pt)
        하나도 안 가려지면 $sum w_j max(cos theta_j, 0) = pi$. 이것으로 나눈 값이 *AO*:
        $ "AO" = 1/pi sum_j w_j times "보임"_j times max(cos theta_j, 0) quad -> quad E_"하늘" = 0.2 times pi times "AO" $
        #v(-0.3em)
        0 = 완전히 가려짐, 1 = 하늘이 다 보임. *Gaussian마다 하나*씩 계산.
      ]
    ],
    [
      #align(center, ao-fan)
      #v(0.2em)
      #set text(size: 12pt)
      #grid(
        columns: (auto, 1fr),
        column-gutter: 0.5em,
        row-gutter: 0.4em,
        text(fill: c-blue)[*━*], [보이는 방향. 굵기 = $cos theta$ (정면일수록 크게 침)],
        text(fill: c-base.darken(10%))[*┅*], [가려진 방향 → 더하지 않음],
      )
      #v(0.2em)
      #note[AO = 보이는 방향의 $cos theta$ 합 ÷ 전부 보일 때의 합 (그림은 단면 개념도, 실제는 반구 전체). 조명과 무관하고 점 주변의 모양만으로 정해짐. 판정은 정답과 같은 0/1.]
    ],
  )
]
]

// cube map 칸의 넓이 w_j: 면 위 같은 간격의 칸을 구에 투영하면 가운데 칸이 넓고 가장자리 칸이 좁다 (단면)
#let cube-cross = cetz.canvas(length: 1cm, {
  import cetz.draw: *
  let S = 3.5
  let n = 8
  let P(x, y) = (x * S, y * S)
  let ang(x) = calc.atan2(x, 1.0) // +x축에서 잰 각 (cetz atan2(x, y) = atan(y/x))
  // 강조할 칸: 가운데, 가장자리
  let cells = ((0.0, 0.25, c-blue), (0.75, 1.0, c-orange))
  for (x0, x1, col) in cells {
    line((0, 0), P(x0, 1), P(x1, 1), close: true, fill: col.lighten(82%), stroke: none)
  }
  // 정육면체 단면 (위쪽 절반) + 단위 원
  line(P(-1, 0), P(-1, 1), P(1, 1), P(1, 0), stroke: 0.8pt + ink2)
  arc((0, 0), start: 0deg, stop: 180deg, radius: S, anchor: "origin", stroke: 0.8pt + muted)
  // 면 위 같은 간격 칸 경계와 중심에서의 선
  for i in range(n + 1) {
    let x = -1 + 2 * i / n
    line(P(x, 1), P(x, 1.06), stroke: 0.6pt + ink2)
    line((0, 0), P(x, 1), stroke: 0.3pt + rule.darken(15%))
  }
  for (x0, x1, col) in cells {
    line(P(x0, 1), P(x1, 1), stroke: 2.4pt + col)
    arc((0, 0), start: ang(x1), stop: ang(x0), radius: S, anchor: "origin", stroke: 2.4pt + col)
  }
  // 가장자리 칸: 거리와 기울기
  let xc = 0.875
  let dl = calc.sqrt(xc * xc + 1)
  line((0, 0), P(xc, 1), stroke: (paint: c-orange.darken(20%), thickness: 0.7pt, dash: "dashed"))
  content(P(xc * 0.55 + 0.1, 0.55), anchor: "west", text(size: 10pt, fill: c-orange.darken(25%))[거리 $|d|$])
  line(P(xc, 1), P(xc, 0.72), stroke: 0.6pt + ink2)
  arc(P(xc, 1), start: 270deg, stop: 270deg - calc.atan(xc), radius: 0.7, anchor: "origin", stroke: 0.6pt + ink2)
  content(P(xc - 0.13, 0.72), text(size: 9.5pt, fill: ink2)[$theta$])
  // 라벨
  content(P(0.125, 1.15), text(size: 10pt, fill: c-blue.darken(15%))[가운데 칸])
  content(P(0.875, 1.15), text(size: 10pt, fill: c-orange.darken(15%))[가장자리 칸])
  content(P(-1.06, 1), anchor: "east", text(size: 10pt, fill: ink2)[cube 면 \ (같은 간격)])
  content(P(-0.72, 0.42), text(size: 10pt, fill: muted)[단위 구])
  circle((0, 0), radius: 0.09, fill: c-lego, stroke: 0.6pt + c-lego.darken(30%))
  content((0, -0.35), text(size: 10pt, fill: ink2)[점 (cube의 중심)])
})

// 면 하나의 w_j (8×8로 줄여 그림, 가운데를 1로)
#let cube-face-w(n: 8, size: 3.0) = cetz.canvas(length: 1cm, {
  import cetz.draw: *
  let h = size / n
  for r in range(n) {
    for c in range(n) {
      let x = -1 + (c + 0.5) * 2 / n
      let y = -1 + (r + 0.5) * 2 / n
      let w = calc.pow(x * x + y * y + 1, -1.5)
      let wmax = calc.pow(2 / (n * n) + 1, -1.5)
      rect((c * h, r * h), ((c + 1) * h, (r + 1) * h), fill: c-blue.lighten(100% - 85% * w / wmax), stroke: 0.4pt + white)
    }
  }
  content((size / 2, -0.3), text(size: 10pt, fill: ink2)[cube 면 하나 (진할수록 $w_j$ 큼)])
})

#let cube-weight-slide = [
#slide(kicker: "부록 · 정답 계산", id: "cube-weight", title: [cube map 칸의 넓이 $w_j$])[
  #grid(
    columns: (1.05fr, 1fr),
    column-gutter: 0.9cm,
    [
      #align(center, cube-cross)
      #v(0.1em)
      #note[단면 그림. 면 위에서는 칸 너비가 같지만, 점에서 보면 가장자리 칸은 멀고(거리 $|d|$) 비스듬해서(각 $theta$) 구 위에서 *좁은 호*가 됨.]
      #v(0.3em)
      #grid(
        columns: (auto, 1fr),
        column-gutter: 0.5cm,
        align: horizon,
        cube-face-w(size: 2.6),
        note[같은 계산을 면 전체에 한 결과 (실제는 64×64). 가운데가 가장 넓고 꼭짓점이 가장 좁음.],
      )
    ],
    [
      #set text(size: 12.5pt)
      점을 중심으로 한 변 2짜리 정육면체를 두고, 각 면을 64×64칸으로 *같은 간격* 분할.
      - 칸 중심 $d = (x, y, 1)$ ($x, y$: −1\~1), 방향 $omega_j = d "/" |d|$
      - $w_j$ = 그 칸을 *단위 구에 투영한 넓이* (입체각)
      #v(0.2em)
      $ w_j approx underbrace((2/64)^2, "면 위 칸 넓이") times underbrace(1/(|d|^2), "멀수록 작게") times underbrace(cos theta = 1/(|d|), "비스듬할수록 작게") = (2\/64)^2 / (|d|^3) $
      #v(-0.2em)
      - 6면을 모두 더해 정확히 $4 pi$ (구 전체)가 되도록 맞춤
      #v(0.2em)
      #callout[
        #set text(size: 12pt)
        면 가운데 $|d| = 1$ → 가장 넓음. 꼭짓점 $|d| approx sqrt(3)$ → 약 *1/5*. \
        사각형의 정확한 입체각 식과 비교하면 차이 최대 0.02% (64칸이 충분히 작음).
      ]
      #note[원판 광원처럼 같은 넓이로 나누지 않은 이유: wavelet 압축(#pref("result-c"))이 cube 면별 정사각형 격자 위에서 계산되므로 격자를 유지하고 넓이만 보정함. 코드: `cube_directions`.]
    ],
  )
]
]
