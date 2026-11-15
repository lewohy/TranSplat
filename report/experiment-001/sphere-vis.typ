// 한 Gaussian의 방향별 가림: 구 껍질 그림과 그 단면 그래프. report.typ의 "문제" 슬라이드가 import해서 쓴다.
// 데이터(투영·정렬까지 끝난 2D 다각형, 단면 값)는 fig/make_sphere_vis.py로 생성.
#import "@preview/cetz:0.4.2"
#import "theme.typ": *

#let sphere-data = json("fig/sphere_vis.json")
#let c-sun = rgb("#f5b83d")

// 값 0(가려짐) → 1(빛이 들어옴)
#let val-color(v) = color.mix((ink, 100% - calc.clamp(v, 0, 1) * 100%), (rgb("#f6f1e6"), calc.clamp(v, 0, 1) * 100%))

// 1/8은 껍질(반지름·색 = 값, 가려진 쪽이 안으로 들어감), 나머지는 와이어프레임. 파란 선 = 단면.
#let shell(name, label, len: 2.3cm) = cetz.canvas(length: len, {
  import cetz.draw: *
  let d = sphere-data
  let pan = d.panels.at(name)
  line(..d.outline, stroke: 0.6pt + rule)
  for seg in d.wire.filter(s => not s.front) {
    line(..seg.p, stroke: (paint: rule, thickness: 0.4pt, dash: "dotted"))
  }
  for seg in d.wire.filter(s => s.front) {
    line(..seg.p, stroke: 0.45pt + muted.lighten(30%))
  }
  for seg in d.great.filter(s => not s.front) {
    line(..seg.p, stroke: (paint: c-blue.lighten(30%), thickness: 0.8pt, dash: "dotted"))
  }
  for seg in d.great.filter(s => s.front) {
    line(..seg.p, stroke: 1.2pt + c-blue)
  }
  for q in pan.quads {
    let c = val-color(q.v).darken((1 - q.s) * 70%)
    line(..q.p, close: true, fill: c.transparentize(15%), stroke: 0.3pt + c.transparentize(15%))
  }
  line(..pan.slice, stroke: 1.6pt + c-blue)
  for (k, p) in d.axes.pairs() {
    line((0, 0), p, stroke: 0.6pt + ink2, mark: (end: ">", fill: ink2, scale: 0.6))
    content(p, anchor: "south-west", padding: 0.04, text(size: 8pt, fill: ink2, k))
  }
  circle((0, 0), radius: 0.035, fill: c-lego, stroke: 0.5pt + c-lego.darken(30%))
  content((0, -1.25), text(size: 11.5pt, weight: "semibold", label))
})

// 파란 선(구를 지나는 원)을 따라 읽은 값: ② 판정값과 ③ SH 16개 복원값
#let cut-graph(W, H) = {
  let c = sphere-data.cut
  let px(t) = W * t / 360
  let py(y) = H * (1.15 - y) / 1.4
  let path(vals, stroke) = {
    let pts = c.t.zip(vals).map(((t, v)) => (px(t), py(v)))
    pts.push((W, py(vals.at(0))))
    curve(stroke: stroke, curve.move(pts.at(0)), ..pts.slice(1).map(p => curve.line(p)))
  }
  box(width: W, height: H + 1.0cm, {
    place(top + left, dy: py(0), line(length: W, stroke: 0.6pt + rule))
    place(top + left, dy: py(1), line(length: W, stroke: 0.6pt + rule))
    place(top + left, dx: -0.45cm, dy: py(1) - 0.22cm, text(size: 10pt, fill: muted)[1])
    place(top + left, dx: -0.45cm, dy: py(0) - 0.22cm, text(size: 10pt, fill: muted)[0])
    place(top + left, path(c.judge, 2.5pt + ink))
    // 방향마다 계산한 값 (실제는 1,200방향, 여기서는 일부만 점으로)
    for i in range(0, c.t.len(), step: 8) {
      place(top + left, dx: px(c.t.at(i)) - 0.06cm, dy: py(c.judge.at(i)) - 0.06cm, circle(radius: 0.06cm, fill: white, stroke: 0.9pt + ink))
    }
    place(top + left, path(c.sh16, 2pt + c-orange))
    let lt = c.light_t
    place(top + left, dx: px(lt) - 0.17cm, dy: py(1) - 0.75cm, circle(radius: 0.17cm, fill: c-sun))
    place(top + left, dx: px(lt) + 0.3cm, dy: py(1) - 0.8cm, text(size: 11pt, fill: ink2)[작은 광원])
    place(top + left, dx: px(65) + 0.2cm, dy: py(0.12), text(size: 11pt, fill: ink2)[← 가려진 구간])
    for (t, lab) in ((0, "0°"), (90, "90°"), (180, "180°"), (270, "270°"), (360, "360°")) {
      place(top + left, dx: px(t), dy: py(-0.12), place(center + top, text(size: 10pt, fill: muted, lab)))
    }
    place(top + left, dx: W / 2 - 3.6cm, dy: H + 0.45cm, text(size: 11pt, fill: muted)[파란 선을 따라 z축(0°)부터 한 바퀴 돈 각도])
  })
}
