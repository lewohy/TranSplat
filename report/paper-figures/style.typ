// 논문 그림 공용 스타일: 2단 원고의 한 단 폭(약 8.3cm)에 맞춘 작은 글자, 흰 배경, 색은 3~4개만.
#import "@preview/cetz:0.4.2"

#let col-w = 8.3cm
#let ink = rgb("#1a1a1a")
#let gray = rgb("#8a8a8a")
#let light-gray = rgb("#d9d9d9")
#let c-a = rgb("#0072b2") // 파랑
#let c-b = rgb("#d55e00") // 주황
#let c-c = rgb("#009e73") // 초록
#let c-sun = rgb("#e6a700")

#let setup(body) = {
  set page(width: auto, height: auto, margin: 3pt, fill: white)
  // HCIK 2027 서식은 나눔 글꼴만 허용: 원고 본문과 같은 나눔명조만 씀 (수식 글꼴을 피하려고 그림에 $...$를 쓰지 않음)
  set text(font: "NanumMyeongjo", size: 7pt, fill: ink)
  body
}

// 데이터 값 v를 [a, b] 범위에서 길이 len의 그림 좌표로
#let lin(a, b, len) = v => (v - a) / (b - a) * len

// 축과 눈금. X, Y는 lin()으로 만든 좌표 변환. cetz canvas 안에서 씀.
#let axes(w, h, X, Y, xticks, yticks, xlabel: none, ylabel: none, xfmt: v => str(v), yfmt: v => str(v)) = {
  import cetz.draw: *
  for v in yticks {
    line((0, Y(v)), (w, Y(v)), stroke: 0.3pt + light-gray)
    content((-0.08, Y(v)), anchor: "east", text(size: 6.5pt, yfmt(v)))
  }
  for v in xticks {
    line((X(v), 0), (X(v), -0.06), stroke: 0.5pt + ink)
    content((X(v), -0.1), anchor: "north", text(size: 6.5pt, xfmt(v)))
  }
  line((0, 0), (w, 0), stroke: 0.5pt + ink)
  line((0, 0), (0, h), stroke: 0.5pt + ink)
  if xlabel != none { content((w / 2, -0.42), anchor: "north", xlabel) }
  if ylabel != none { content((-0.62, h / 2), angle: 90deg, ylabel) }
}

#let legend-item(color, label, dash: none, marker: false) = box(baseline: 30%, {
  box(width: 0.55cm, height: 0.2cm, {
    place(horizon + left, line(length: 0.55cm, stroke: (paint: color, thickness: 1pt, dash: dash)))
    if marker { place(center + horizon, circle(radius: 1.4pt, fill: color, stroke: none)) }
  })
  h(0.12cm)
  label
})
