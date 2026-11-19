// Figure 2: 분석 방법. 압축 없는 기준값을 만들고, 한 요소만 바꾼 비교 대상의 오차를 같은 지표로 잼.
#import "style.typ": *
#show: setup

#let node(pos, w, h, body, bg: white) = {
  import cetz.draw: *
  let (x, y) = pos
  rect((x - w / 2, y - h / 2), (x + w / 2, y + h / 2), fill: bg, stroke: 0.6pt + ink, radius: 0.06)
  content((x, y), box(width: (w - 0.08) * 1cm, align(center, text(size: 6pt, body))))
}
#let arr(a, b, col: ink) = {
  import cetz.draw: *
  line(a, b, stroke: 0.6pt + col, mark: (end: ">", fill: col, scale: 0.5))
}

#cetz.canvas(length: 1cm, {
  import cetz.draw: *
  // 위: 기준값 만들기
  let y0 = 3.0
  let top = (
    (0.95, [학습된 2DGS \ (lego, 85만 개)]),
    (3.0, [표면 Gaussian \ 20,000개]),
    (5.25, [방향별 0/1 판정 V \ (24,576 + 64방향)]),
    (7.35, [*기준값* E \ (Eq. 1)]),
  )
  for (i, (x, body)) in top.enumerate() {
    node((x, y0), if i == 2 { 2.2 } else { 1.65 }, 0.72, body, bg: if i == 3 { c-a.lighten(85%) } else { white })
  }
  arr((1.8, y0), (2.15, y0))
  arr((3.85, y0), (4.12, y0))
  arr((6.38, y0), (6.5, y0))
  // 아래: 비교 대상. (i)은 TranSplat 그대로, (ii)~(iv)는 기준값에서 한 요소만 바꾼 것
  let y1 = 1.4
  let yb = 2.1
  let bottom = (
    [(i) TranSplat],
    [(ii) V, 조명 \ → SH K개],
    [(iii) V \ → Haar K개],
    [(iv) 광원만 \ shadow map],
  )
  let xs = (0.95, 3.4, 5.375, 7.35)
  for (i, body) in bottom.enumerate() {
    let x = xs.at(i)
    node((x, y1), 1.75, 0.72, body)
    line((x, if i == 0 { y0 - 0.36 } else { yb }), (x, y1 + 0.36), stroke: 0.5pt + gray, mark: (end: ">", fill: gray, scale: 0.45))
    line((x, y1 - 0.36), (x, 0.62), stroke: 0.5pt + ink, mark: (end: ">", fill: ink, scale: 0.45))
  }
  content((xs.at(0) + 0.08, yb), anchor: "west", text(size: 6pt, fill: gray)[그대로])
  // 오른쪽 묶음: 기준값에서 한 요소만 바꿈
  line((7.35, y0 - 0.36), (7.35, yb), stroke: 0.5pt + gray)
  line((xs.at(1), yb), (7.35, yb), stroke: 0.5pt + gray)
  content(((xs.at(1) + xs.at(3)) / 2, yb + 0.14), anchor: "south", text(size: 6pt, fill: gray)[기준값에서 한 요소만 바꿈])
  // 오차
  node((4.15, 0.32), 8.0, 0.55, [그림자 경계 오차 e (Eq. 2): 기준값과 비교, 광원 크기 2, 5, 10, 30°], bg: c-b.lighten(88%))
})
