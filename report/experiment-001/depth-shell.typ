// report.typ에 들어가는 슬라이드: ①의 깊이 이미지 예시(depth-example), lego의 "검은 막"(black-shell).
// 그림: fig/make_depth_figs.py, fig/make_shell_figs.py
#import "@preview/cetz:0.4.2"
#import "theme.typ": *

// 사진 위 위치 표시. (x, y)는 원본 픽셀 좌표, size는 원본 해상도.
#let marked(path, w, size, marks) = box(width: w, {
  image(path, width: w)
  for (x, y, label, color) in marks {
    let px = w * x / size
    let py = w * y / size
    place(top + left, dx: px - 0.14cm, dy: py - 0.14cm, circle(radius: 0.14cm, fill: color, stroke: 1.2pt + white))
    place(top + left, dx: px + 0.22cm, dy: py - 0.3cm, box(
      fill: white.transparentize(15%),
      inset: (x: 0.2em, y: 0.1em),
      radius: 2pt,
      text(size: 10pt, weight: "semibold", fill: color.darken(15%), label),
    ))
  }
})

// 1장 그림: 카메라에서 쏜 시선이 처음 닿는 표면 (값은 실제 lego 렌더의 깊이).
#let depth-scene = cetz.canvas(length: 2.15cm, {
  import cetz.draw: *
  let add(a, b) = a.zip(b).map(((x, y)) => x + y)
  let sub(a, b) = a.zip(b).map(((x, y)) => x - y)
  let mul(a, s) = a.map(x => x * s)
  let dot(a, b) = a.zip(b).map(((x, y)) => x * y).sum()
  let unit(a) = mul(a, 1 / calc.sqrt(dot(a, a)))
  let cross(a, b) = (
    a.at(1) * b.at(2) - a.at(2) * b.at(1),
    a.at(2) * b.at(0) - a.at(0) * b.at(2),
    a.at(0) * b.at(1) - a.at(1) * b.at(0),
  )
  // ortho(x: 25deg, y: 35deg)에서 보이는 면은 위(y+), 앞(z+), 오른쪽(x+).
  let cube(x0, y0, z0, x1, y1, z1, c) = {
    let s = 0.5pt + c.darken(40%)
    line((x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1), close: true, fill: c.lighten(30%), stroke: s)
    line((x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1), close: true, fill: c.darken(5%), stroke: s)
    line((x1, y0, z0), (x1, y0, z1), (x1, y1, z1), (x1, y1, z0), close: true, fill: c.darken(20%), stroke: s)
  }
  let tag(p, anchor, body, color) = content(p, anchor: anchor, padding: 0.12, box(
    fill: white,
    stroke: 0.6pt + color,
    inset: (x: 0.3em, y: 0.15em),
    radius: 3pt,
    text(size: 10pt, weight: "semibold", fill: color.darken(15%), body),
  ))
  ortho(x: 25deg, y: 35deg, sorted: false, {
    // 물체 (뒤 → 앞 순서로 칠함)
    cube(-2.0, -0.15, -1.2, 2.0, 0, 1.2, c-plate)
    cube(-1.3, 0, -0.85, 0.4, 0.35, -0.6, c-base.darken(30%))
    cube(-1.2, 0.1, -0.6, 0.3, 0.55, 0.6, c-lego)
    cube(-1.0, 0.55, -0.45, -0.2, 1.1, 0.45, c-lego)
    cube(0.3, 0.35, -0.08, 1.0, 0.45, 0.08, c-lego.darken(10%))
    cube(0.9, 0.1, -0.55, 1.6, 0.6, 0.55, c-lego)
    cube(-1.3, 0, 0.6, 0.4, 0.35, 0.85, c-base.darken(30%))

    // 카메라와 깊이 이미지 평면
    let C = (-1.0, 3.5, 3.3)
    let fwd = unit(sub((0, 0.3, 0), C))
    let a = unit(cross(fwd, (0, 1, 0)))
    let b = cross(a, fwd)
    let dist = 1.0
    let pc = add(C, mul(fwd, dist))
    let hw = 0.5
    let corner(i, j) = add(pc, add(mul(a, i * hw), mul(b, j * hw)))
    for (i, j) in ((-1, -1), (1, -1), (1, 1), (-1, 1)) {
      line(C, corner(i, j), stroke: 0.5pt + c-blue.lighten(40%))
    }
    line(corner(-1, -1), corner(1, -1), corner(1, 1), corner(-1, 1), close: true, fill: white.transparentize(20%), stroke: 0.8pt + c-blue)
    for k in range(1, 4) {
      let t = -1 + k / 2
      line(corner(t, -1), corner(t, 1), stroke: 0.3pt + c-blue.lighten(30%))
      line(corner(-1, t), corner(1, t), stroke: 0.3pt + c-blue.lighten(30%))
    }
    // 시선 4개: 닿는 표면 / 빈 공간
    let rays = (
      ((-0.6, 1.1, 0.3), c-orange, [운전석 8.50], "south-east"),
      ((1.3, 0.6, 0.0), c-blue, [버킷 9.41], "south-west"),
      ((0.65, 0.0, 1.0), c-aqua, [판 8.95], "west"),
    )
    for (p, col, lab, anc) in rays {
      let d = sub(p, C)
      let q = add(C, mul(d, dist / dot(d, fwd)))
      line(C, p, stroke: 1.3pt + col)
      circle(q, radius: 0.045, fill: col, stroke: none)
      circle(p, radius: 0.07, fill: col, stroke: 1pt + white)
      tag(p, anc, lab, col)
    }
    let m = (-3.2, -0.5, 2.0)
    line(C, m, stroke: (paint: muted, thickness: 1.1pt, dash: "dashed"))
    tag(m, "north", [빈 공간 0], muted)
    // 카메라 몸체
    circle(C, radius: 0.15, fill: c-blue, stroke: 1pt + white)
    content(C, anchor: "east", padding: 0.3, text(size: 10.5pt, weight: "semibold", fill: c-blue)[카메라 (방향 $i$ 쪽)])
    content(corner(1, 1), anchor: "west", padding: 0.12, text(size: 9.5pt, fill: c-blue)[깊이 이미지\ (칸 하나 = 시선 하나)])
  })
})


#let depth-example = [
// ---------------------------------------------------------------------------
// 1. 깊이 이미지 개념
// ---------------------------------------------------------------------------
#slide(kicker: "배경 · 1단계 bake · ① 예시", title: "깊이 이미지 = 카메라에서 처음 닿는 표면까지의 거리")[
  #flow-nav("①")
  #grid(
    columns: (1.25fr, 1fr),
    column-gutter: 0.8cm,
    align(center + horizon, depth-scene),
    [
      #set text(size: 13pt)
      픽셀 하나 = 카메라에서 쏜 시선 하나. \
      그 시선이 *처음 닿는 표면까지의 거리*를 픽셀 값으로 적음.
      #v(0.3em)
      *lego 예시* (장면 반지름을 고친 경우, $r = 1.92$)
      #table(
        columns: (auto, 1fr),
        table.hline(stroke: 0.6pt + rule),
        [카메라 위치], [물체 중심에서 $5r = 9.59$],
        [기록 범위], [6.71 \~ 12.47 (중심 $plus.minus 1.5r$)],
        table.hline(stroke: 0.6pt + rule),
        text(fill: c-orange.darken(15%))[운전석 지붕], [8.50 #note[(가장 가까움)]],
        text(fill: c-aqua.darken(20%))[판], [8.95],
        [버킷], [9.41],
        text(fill: muted)[빈 공간], [0 #note[(기록 없음 → ②에서 "보임")]],
        table.hline(stroke: 0.6pt + rule),
      )
      #note[숫자는 실제 렌더 값 (`fig/depth_meta.json`, 다음 장 이미지의 표시 지점).]
    ],
  )
]

// ---------------------------------------------------------------------------
// 2. 실제 깊이 이미지
// ---------------------------------------------------------------------------
#slide(kicker: "배경 · 1단계 bake · ① 예시", title: "lego를 한 방향에서 렌더한 실제 깊이 이미지")[
  #flow-nav("①")
  #let marks = (
    (610, 560, [운전석 8.50], c-orange),
    (450, 340, [버킷 9.41], c-blue),
    (560, 800, [판 8.95], c-aqua),
    (150, 500, [검은 막 10.92], ink),
  )
  #grid(
    columns: (1fr, 1fr, 0.9fr),
    column-gutter: 0.6cm,
    [
      #note[같은 카메라의 컬러 렌더 (흰 배경)]
      #marked("fig/color_fixed.png", 7.6cm, 1024, marks)
    ],
    [
      #note[깊이 이미지 (밝을수록 가까움)]
      #marked("fig/depth_fixed.png", 7.6cm, 1024, marks)
      #v(-0.2em)
      #box(width: 7.6cm)[
        #box(width: 100%, height: 0.3cm, fill: gradient.linear(..color.map.magma.rev()))
        #grid(columns: (1fr, 1fr), text(size: 10pt)[8.1 가까움], align(right, text(size: 10pt)[13.0 멂]))
      ]
    ],
    [
      #set text(size: 12.5pt)
      - 노란 물체 부분은 형태가 그대로 보임 (운전석이 가장 밝고, 버킷·판 순으로 멀어짐).
      - 그런데 물체 *바깥의 넓은 영역*에도 깊이가 찍혀 있음.
      - 컬러 렌더에서 같은 자리를 보면 *검은 덩어리*. 이게 "검은 막".
      #v(0.3em)
      #callout(color: c-orange)[
        #set text(size: 12pt)
        깊이 이미지는 색을 안 봄. 검은 Gaussian도 불투명하면 *벽처럼* 깊이에 찍힘.
      ]
    ],
  )
]

]

#let black-shell = [
// ---------------------------------------------------------------------------
// 3. 검은 막의 정체
// ---------------------------------------------------------------------------
#slide(kicker: "결과 A · 정답 검증 · 검은 막", title: "정체: 학습 배경이 검은색이라 생긴 \"검은 바닥판\"")[
  #grid(
    columns: (1fr, 1fr, 1fr),
    column-gutter: 0.5cm,
    [
      #image("fig/train_photo.png", height: 5.3cm)
      #note[*① 학습 사진* (r_10). 배경이 검은색.]
    ],
    [
      #image("fig/train_view_white.png", height: 5.3cm)
      #note[*② 같은 시점, 학습된 Gaussian을 흰 배경에 렌더.* 배경이 하얘야 하는데 화면 전체가 검게 덮여 있음.]
    ],
    [
      #image("fig/shell_side.png", height: 5.3cm)
      #note[*③ 옆에서 본 모습 (흰 배경).* 판 높이에 넓고 납작한 검은 원판이 깔려 있음.]
    ],
  )
  #v(0.3em)
  #grid(
    columns: (1.2fr, 1fr),
    column-gutter: 0.8cm,
    callout[
      #set text(size: 12.5pt)
      *왜 생겼나:* 학습 사진의 배경이 검은색 (`white_background=False`). 물체 주변을 *검은* Gaussian으로 채워도 사진과 똑같아 보여서 학습에서 벌점이 없음 → 판 주변에 검은 Gaussian이 대량으로 남음. 사진(①)으로는 절대 안 보임.
    ],
    [
      #set text(size: 12pt)
      - 개수: 43,955개 (장면 반지름 안 불투명 점의 7.8%)
      - 색: 거의 검정 (밝기 < 0.03)
      - 위치: 대부분 판 바닥 높이 (높이 중앙값 −0.62, 판 바닥 약 −0.68)
      - 크기: 다른 점의 약 2.8배 (중앙값)
    ],
  )
]

// ---------------------------------------------------------------------------
// 4. 영향
// ---------------------------------------------------------------------------
#slide(kicker: "결과 A · 정답 검증 · 검은 막", title: "검은 막의 영향: 결론은 그대로")[
  #grid(
    columns: (0.8fr, 1.2fr),
    column-gutter: 0.7cm,
    [
      #align(center, cetz.canvas(length: 0.78cm, {
        import cetz.draw: *
        // 옆에서 본 단면: 검은 막, 판, 물체
        rect((-6, -0.55), (6, -0.35), fill: ink, stroke: none)
        rect((-2.6, -0.35), (2.6, 0), fill: c-plate, stroke: 0.4pt + c-plate.darken(30%))
        rect((-1.4, 0), (0.6, 1.0), fill: c-lego, stroke: 0.4pt + c-lego.darken(30%))
        rect((-1.1, 1.0), (-0.1, 1.8), fill: c-lego, stroke: 0.4pt + c-lego.darken(30%))
        content((4.2, -0.9), text(size: 10.5pt)[검은 막])
        // 위에서 오는 빛: 막에 안 닿음
        let p = (1.6, 0)
        for (a, lab) in ((60, "60°"), (30, "30°"), (10, "10°")) {
          let d = (calc.cos(a * 1deg), calc.sin(a * 1deg))
          let q = (p.at(0) + 4.2 * d.at(0), p.at(1) + 4.2 * d.at(1))
          line(q, p, stroke: 1.1pt + c-orange, mark: (end: ">", fill: c-orange))
          content(q, anchor: "south-west", padding: 0.05, text(size: 10pt, fill: c-orange.darken(15%), lab))
        }
        circle(p, radius: 0.08, fill: c-orange, stroke: none)
        // 아래에서 오는 빛: 막(그리고 판)에 막힘
        let b = (-4.5, -2.2)
        line(b, (-3.6, -0.6), stroke: 1.1pt + c-blue, mark: (end: ">", fill: c-blue))
        content(b, anchor: "north", padding: 0.1, text(size: 10pt, fill: c-blue)[아래에서 오는 빛 → 막힘])
      }))
      #v(0.4em)
      #note[광원은 모두 위쪽 (고도 10°, 30°, 60°)이라 막에 거의 안 걸림 (원판 그림자 판정이 바뀐 점 1\~5%). 대신 *아래쪽 ambient를 바닥처럼 가려서* 정답 밝기가 평균 2.2% 어두웠음.]
    ],
    [
      #set text(size: 13pt)
      *막을 지우고 실험 전체 재실행* (같은 평가점 36,826개, 반그림자 오차)
      #{
        set text(size: 11pt)
        let ab(a, b) = [#a → *#b*]
        table(
          columns: (auto, auto, auto, auto, auto),
          column-gutter: 0.1cm,
          align: (left, right, right, right, right),
          table.hline(stroke: 0.6pt + rule),
          text(fill: muted)[광원 크기], text(fill: muted)[2°], text(fill: muted)[5°], text(fill: muted)[10°], text(fill: muted)[30°],
          table.hline(stroke: 0.6pt + rule),
          [현재 TranSplat], ab("0.46", "0.38"), ab("0.54", "0.59"), ab("0.35", "0.36"), ab("0.26", "0.28"),
          [쉬운 수정], ab("0.22", "0.21"), ab("0.22", "0.21"), ab("0.20", "0.20"), ab("0.15", "0.15"),
          [SH 16 (정답 + 압축)], ab("0.18", "0.18"), ab("0.18", "0.18"), ab("0.17", "0.16"), ab("0.11", "0.11"),
          [SH/Haar 비율#super[\*]], ab("0.98", "0.98"), ab("1.04", "1.01"), ab("1.00", "0.95"), ab("0.60", "0.58"),
          table.hline(stroke: 0.6pt + rule),
        )
        text(size: 10pt, fill: muted)[\* 가림 지도 압축, 같은 메모리 (SH 256 / Haar 128). 1보다 크면 Haar가 나음.]
      }
      #v(0.2em)
      → *B·C의 결론은 그대로.* 현재 TranSplat 수치만 ±0.08 흔들림.
      #v(0.3em)
      #callout(color: c-orange)[
        #set text(size: 12pt)
        *현재 TranSplat 코드에는 문제.* ①의 깊이는 alpha 가중평균이라 *옅은 Gaussian만 걸린 픽셀도 깊이가 그대로 찍힘* (깊이가 찍힌 픽셀의 24%가 alpha < 0.5) → 옅은 막도 그림자를 만듦. 실험의 정답은 median depth로 피했음.
      ]
    ],
  )
]
]
