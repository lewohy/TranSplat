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
    (5.25, [방향별 0/1 판정 $V$ \ (24,576 + 64방향)]),
    (7.35, [*기준값* $E$ \ (Eq. 1)]),
  )
  for (i, (x, body)) in top.enumerate() {
    node((x, y0), if i == 2 { 2.2 } else { 1.65 }, 0.72, body, bg: if i == 3 { c-a.lighten(85%) } else { white })
  }
  arr((1.8, y0), (2.15, y0))
  arr((3.85, y0), (4.12, y0))
  arr((6.38, y0), (6.5, y0))
  // 아래: 비교 대상. (i)(ii)는 TranSplat 계산 순서, (iii)~(v)는 기준값에서 한 요소만 바꾼 것
  let y1 = 1.4
  let yb = 2.1
  let bottom = (
    [(i) TranSplat],
    [(ii) TranSplat \ + 기본 오류 수정],
    [(iii) $V$, 조명 \ $arrow.r$ SH $K$개],
    [(iv) $V$ \ $arrow.r$ Haar $K$개],
    [(v) 광원만 \ shadow map],
  )
  let xs = range(5).map(i => 0.85 + i * 1.65)
  for (i, body) in bottom.enumerate() {
    let x = xs.at(i)
    node((x, y1), 1.58, 0.72, body)
    line((x, yb), (x, y1 + 0.36), stroke: 0.5pt + gray, mark: (end: ">", fill: gray, scale: 0.45))
    line((x, y1 - 0.36), (x, 0.62), stroke: 0.5pt + ink, mark: (end: ">", fill: ink, scale: 0.45))
  }
  // 왼쪽 묶음: 학습된 2DGS에서 바로
  line((0.95, y0 - 0.36), (0.95, yb), stroke: 0.5pt + gray)
  line((xs.at(0), yb), (xs.at(1), yb), stroke: 0.5pt + gray)
  content(((xs.at(0) + xs.at(1)) / 2, yb + 0.14), anchor: "south", text(size: 6pt, fill: gray)[TranSplat 계산 순서])
  // 오른쪽 묶음: 기준값에서 한 요소만 바꿈
  line((7.35, y0 - 0.36), (7.35, yb), stroke: 0.5pt + gray)
  line((xs.at(2), yb), (7.35, yb), stroke: 0.5pt + gray)
  content(((xs.at(2) + xs.at(4)) / 2, yb + 0.14), anchor: "south", text(size: 6pt, fill: gray)[기준값에서 한 요소만 바꿈])
  // 오차
  node((4.15, 0.32), 8.0, 0.55, [그림자 경계 오차 $e$ (Eq. 2): 기준값과 비교, 광원 크기 2, 5, 10, 30$degree$], bg: c-b.lighten(88%))
})
