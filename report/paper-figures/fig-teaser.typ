// Figure 1: 한 점의 visibility를 큰 원을 따라 읽은 값. 0/1 판정 vs SH 16개 / 100개 복원 (합성 가림막).
// 데이터: make_teaser_data.py -> teaser.json
#import "style.typ": *
#show: setup

#let d = json("teaser.json")
#let t0 = 0
#let t1 = 120

#cetz.canvas(length: 1cm, {
  import cetz.draw: *
  let w = 7.2
  let h = 2.6
  let X = lin(t0, t1, w)
  let Y = lin(-0.3, 1.2, h)
  axes(w, h, X, Y, range(0, 121, step: 20), (0, 0.5, 1),
    xlabel: [방향 (큰 원 위 각도, $degree$)], ylabel: [visibility], xfmt: v => [#v])
  let series(key) = d.t.zip(d.at(key)).filter(((t, v)) => t >= t0 and t <= t1).map(((t, v)) => (X(t), Y(calc.clamp(v, -0.3, 1.2))))
  // 2° 광원 위치
  let lt = d.light_t
  rect((X(lt - 1), 0), (X(lt + 1), h), fill: c-sun.lighten(55%), stroke: none)
  content((X(lt) + 0.08, Y(1.13)), anchor: "west", text(size: 6.5pt, fill: c-sun.darken(30%))[2$degree$ 광원])
  line(..series("sh100"), stroke: (paint: c-a, thickness: 0.9pt, dash: "dashed"))
  line(..series("sh16"), stroke: 1.1pt + c-b)
  line(..series("vis"), stroke: 1.1pt + ink)
  content((X(48), Y(0.08)), text(size: 6.5pt, fill: gray)[가려진 방향])
})
#v(-0.1cm)
#align(center)[
  #legend-item(ink, [0/1 판정 (기준값)]) #h(0.35cm)
  #legend-item(c-b, [SH 16개 (TranSplat)]) #h(0.35cm)
  #legend-item(c-a, [SH 100개], dash: "dashed")
]
