// Figure 1: 벽 뒤 바닥의 그림자. 실제(0/1 판정)는 경계가 또렷하고, visibility를 16개 숫자로 요약하는
// TranSplat 방식은 경계가 넓게 번짐. Ours(광원 분리: 태양만 shadow map)는 실제와 거의 같음.
// 위: 옆에서 본 장면, 가운데: 위에서 본 바닥, 아래: 바닥 밝기 그래프.
// 데이터: make_teaser_data.py -> teaser.json (세 그림 모두 같은 x 좌표)
#import "style.typ": *
#show: setup

#let d = json("teaser.json")
#let x1 = 3.0
#let w = 6.6
#let X = lin(0, x1, w)

#cetz.canvas(length: 1cm, {
  import cetz.draw: *
  let ex = X(d.edge_x)

  // 위: 옆에서 본 장면 (벽, 태양, 빛)
  let ys = 4.82 // 바닥 높이
  let wh = 1.05 // 벽 높이
  let top = (0, ys + wh)
  let dir = (top.at(0) - ex, top.at(1) - ys) // 경계에서 벽 꼭대기 쪽
  let n = calc.sqrt(dir.at(0) * dir.at(0) + dir.at(1) * dir.at(1))
  let u = (dir.at(0) / n, dir.at(1) / n)
  let sun = (top.at(0) + u.at(0) * 1.3, top.at(1) + u.at(1) * 1.3)
  line(sun, (ex, ys), stroke: 0.6pt + c-sun.darken(10%))
  content((ex * 0.5 + 0.2, ys + wh * 0.62), anchor: "west", text(size: 6pt, fill: c-sun.darken(30%))[벽 꼭대기를 스친 빛])
  circle(sun, radius: 0.16, fill: c-sun, stroke: none)
  content((sun.at(0) + 0.25, sun.at(1) + 0.05), anchor: "west", text(size: 6.5pt)[광원 (태양)])
  line((-0.9, ys), (w, ys), stroke: 0.6pt + ink)
  rect((-0.16, ys), (0, ys + wh), fill: gray, stroke: none)
  content((-0.24, ys + wh / 2), anchor: "east", text(size: 6.5pt)[벽])
  rect((0, ys - 0.03), (ex, ys), fill: ink, stroke: none)
  content((w, ys + 0.12), anchor: "south-east", text(size: 6.5pt, fill: gray)[옆에서 본 모습])

  // 가운데: 위에서 본 바닥 두 줄
  let strip(y, key, label) = {
    let xs = d.x
    for i in range(xs.len() - 1) {
      let v = calc.clamp(d.at(key).at(i), 0, 1)
      rect((if i == 0 { 0 } else { X(xs.at(i)) }, y), (X(xs.at(i + 1)) + 0.01, y + 0.42), fill: luma(int(45 + 205 * v)), stroke: none)
    }
    rect((0, y), (w, y + 0.42), stroke: 0.4pt + gray)
    rect((-0.16, y), (0, y + 0.42), fill: gray, stroke: none)
    content((-0.24, y + 0.21), anchor: "east", text(size: 6.5pt, label))
  }
  strip(4.02, "exact", [실제])
  strip(3.45, "sh16", [TranSplat])
  strip(2.88, "ours", [Ours])
  content((w, 2.82), anchor: "north-east", text(size: 6.5pt, fill: gray)[위에서 본 바닥])

  // 아래: 바닥 밝기 그래프
  let h = 1.75
  let Y = lin(0, 1, h)
  axes(w, h, X, Y, (0, 1, 2, 3), (0, 0.5, 1),
    xlabel: [벽에서 떨어진 거리], ylabel: [바닥 밝기], xfmt: v => [#v])
  line((ex, 0), (ex, 4.52), stroke: (paint: gray, thickness: 0.5pt, dash: "dashed"))
  content((ex + 0.05, h + 0.02), anchor: "south-west", text(size: 6pt, fill: gray)[그림자 경계])
  let pts(key) = d.x.zip(d.at(key)).map(((x, v)) => (X(x), Y(calc.clamp(v, 0, 1.05))))
  line(..pts("sh16"), stroke: 1.1pt + c-b)
  line(..pts("exact"), stroke: 1.1pt + ink)
  line(..pts("ours"), stroke: (paint: c-c, thickness: 1.1pt, dash: (2.2pt, 1.6pt)))
  content((X(0.08), Y(0.86)), anchor: "north-west", text(size: 6pt, fill: ink)[실제, Ours: 경계에서 \ 갑자기 밝아짐])
  content((X(1.6), Y(0.62)), anchor: "north-west", text(size: 6pt, fill: c-b.darken(10%))[TranSplat: 넓은 범위에 걸쳐 \ 천천히 밝아짐 → 그림자가 번짐])
})
#v(-0.1cm)
#align(center)[
  #legend-item(ink, [실제 그림자 (방향마다 0/1로 계산)]) #h(0.35cm)
  #legend-item(c-b, [TranSplat 방식]) #h(0.35cm)
  #legend-item(c-c, [Ours], dash: (2.2pt, 1.6pt))
]
