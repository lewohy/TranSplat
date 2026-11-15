// report.typ에 들어가는 슬라이드: ①의 깊이 이미지 예시(depth-example).
// 그림: fig/make_depth_figs.py
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
      *lego 예시* (장면 반지름 $r = 1.57$)
      #table(
        columns: (auto, 1fr),
        table.hline(stroke: 0.6pt + rule),
        [카메라 위치], [물체 중심에서 $5r = 7.84$],
        [기록 범위], [5.49 \~ 10.19 (중심 $plus.minus 1.5r$)],
        table.hline(stroke: 0.6pt + rule),
        text(fill: c-blue)[버킷], [7.20 #note[(가장 가까움)]],
        text(fill: c-aqua.darken(20%))[판], [7.62],
        text(fill: c-orange.darken(15%))[운전석 지붕], [8.07],
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
    (450, 285, [운전석 8.07], c-orange),
    (590, 440, [버킷 7.20], c-blue),
    (640, 700, [판 7.62], c-aqua),
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
        #grid(columns: (1fr, 1fr), text(size: 10pt)[6.9 가까움], align(right, text(size: 10pt)[8.7 멂]))
      ]
    ],
    [
      #set text(size: 12.5pt)
      - 물체 형태가 그대로 보임 (카메라 쪽으로 나온 버킷이 가장 밝고, 판·운전석 순으로 멀어짐).
      - 물체 밖은 기록 없음(회색) → 그 방향 빛은 막히지 않음.
      #v(0.3em)
      #callout(color: c-orange)[
        #set text(size: 12pt)
        깊이 이미지는 색을 안 봄. 검은 Gaussian도 불투명하면 *벽처럼* 깊이에 찍힘.
      ]
    ],
  )
]

]
