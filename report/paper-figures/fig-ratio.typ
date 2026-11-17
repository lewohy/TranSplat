// Figure 3: SH 오차 / Haar wavelet 오차 (lego_rgba study, C_V 행, penumbra nMAE의 3방향 평균).
#import "style.typ": *
#show: setup

#let sizes = ("2", "5", "10", "30")
#let same-k = (1.33, 1.70, 1.86, 0.91)
#let same-mem = (1.03, 1.16, 1.16, 0.63)

#cetz.canvas(length: 1cm, {
  import cetz.draw: *
  let w = 6.6
  let h = 2.6
  let X = lin(-0.4, 3.4, w)
  let Y = lin(0, 2.2, h)
  axes(w, h, X, Y, (0, 1, 2, 3), (0, 0.5, 1, 1.5, 2),
    xlabel: [광원 각지름], ylabel: [SH 오차 $div$ wavelet 오차],
    xfmt: i => [#sizes.at(i)$degree$], yfmt: v => [#v])
  for (v, lab) in ((1, [같음]),) {
    line((0, Y(v)), (w, Y(v)), stroke: (paint: gray, thickness: 0.7pt, dash: "dashed"))
    content((w + 0.06, Y(v)), anchor: "west", text(size: 6.5pt, fill: gray, lab))
  }
  for (vals, col) in ((same-k, c-a), (same-mem, c-b)) {
    line(..vals.enumerate().map(((i, v)) => (X(i), Y(v))), stroke: 1.1pt + col)
    for (i, v) in vals.enumerate() {
      circle((X(i), Y(v)), radius: 0.05, fill: col, stroke: none)
      content((X(i) + 0.08, Y(v)), anchor: "west",
        box(fill: white, inset: 0.8pt, text(size: 6pt, fill: col.darken(15%), str(calc.round(v, digits: 2)).replace(regex("^(\\d\\.\\d)$"), m => m.text + "0"))))
    }
  }
})
#v(-0.1cm)
#align(center)[
  #legend-item(c-a, [같은 개수 (SH 256 vs Haar 256)], marker: true) #h(0.35cm)
  #legend-item(c-b, [같은 메모리 (SH 256 vs Haar 128)], marker: true)
]
