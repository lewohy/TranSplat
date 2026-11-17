// 발표 자료 공통 색·컴포넌트·그림 도우미. report.typ와 나눠 둔 슬라이드 파일이 같이 쓴다.
// set 규칙(페이지, 글꼴 등)은 import로 전달되지 않으므로 report.typ에 둔다.

#let ink = rgb("#0b0b0b")
#let ink2 = rgb("#52514e")
#let muted = rgb("#8a8984")
#let rule = rgb("#e4e3df")
#let soft = rgb("#f4f3f0")
#let c-blue = rgb("#2a78d6")
#let c-orange = rgb("#eb6834")
#let c-aqua = rgb("#1baf7a")
#let c-base = rgb("#a9a8a3")
#let c-lego = rgb("#f2c230")
#let c-plate = rgb("#e6d6b0")

// id: 다른 슬라이드에서 #pref(id)로 이 슬라이드를 가리킬 때 쓰는 이름
// q: 이 슬라이드가 답하는 질문(A/B/C). 오른쪽 위에 질문 슬라이드(id "question")로 가는 링크를 둠
#let slide(title: none, kicker: none, id: none, q: none, body) = {
  pagebreak(weak: true)
  if id != none [#metadata(none)#label(id)]
  if q != none {
    place(top + right, context link(label("question"), text(size: 11pt, fill: muted)[← 질문 #q (#counter(page).at(label("question")).first()장)]))
  }
  if kicker != none {
    text(size: 12pt, fill: c-blue, weight: "semibold", kicker)
    v(0.15em)
  }
  if title != none {
    text(size: 23pt, weight: "bold", title)
    v(0.45em)
  }
  body
}
// id가 붙은 슬라이드를 "N장" 링크로 가리킴 (슬라이드를 넣고 빼도 번호가 따라감)
#let pref(id) = context link(label(id), text(fill: c-blue)[#counter(page).at(label(id)).first()장])
// 글자 자체를 id 슬라이드로 가는 링크로 만듦
#let plink(id, body) = link(label(id), text(fill: c-blue, body))
#let note(body) = text(size: 11.5pt, fill: ink2, body)
#let callout(body, color: c-blue) = block(
  width: 100%,
  breakable: false,
  inset: (x: 0.9em, y: 0.7em),
  radius: 6pt,
  fill: color.lighten(90%),
  stroke: (left: 3pt + color),
  body,
)
#let tag(body, color: c-blue) = box(
  inset: (x: 0.45em, y: 0.2em),
  radius: 4pt,
  fill: color.lighten(85%),
  text(size: 12pt, weight: "semibold", fill: color.darken(25%), body),
)
// 누르면 id 슬라이드로 가는 tag
#let tagl(id, color: c-blue, body) = link(label(id), tag(body, color: color))
// 질문(A/B/C)에 대한 답을 강조하는 박스. 결과 슬라이드마다 같은 모양으로 쓴다.
#let verdict(q, answer, color: c-blue, body) = block(
  width: 100%,
  breakable: false,
  inset: (x: 0.8em, y: 0.65em),
  radius: 6pt,
  fill: color.lighten(88%),
  stroke: 1.5pt + color,
  grid(
    columns: (auto, 1fr),
    column-gutter: 0.8em,
    align: horizon,
    box(inset: (x: 0.6em, y: 0.4em), radius: 5pt, fill: color, text(
      size: 21pt,
      weight: "bold",
      fill: white,
    )[#link(label("question"), underline(offset: 2.5pt, stroke: 1.2pt + white)[#q]): #answer]),
    text(size: 12.5pt, body),
  ),
)
#let placeholder(w, h, body) = rect(
  width: w,
  height: h,
  radius: 6pt,
  fill: soft,
  stroke: (paint: muted, thickness: 1pt, dash: "dashed"),
  align(center + horizon, text(size: 13pt, fill: muted, body)),
)

#let fmt(v, d: 2) = {
  let s = str(calc.round(v, digits: d))
  let p = s.split(".")
  if p.len() == 1 { s + "." + "0" * d } else { s + "0" * (d - p.at(1).len()) }
}

// 그림 도우미. 모두 box 안에서 왼쪽 위 기준 좌표로 쓴다.
#let dotc(x, y, r: 0.06cm, fill: ink2) = place(top + left, dx: x - r, dy: y - r, circle(
  radius: r,
  fill: fill,
  stroke: none,
))
#let lbl(x, y, body, size: 10pt, fill: ink2) = place(top + left, dx: x, dy: y, text(size: size, fill: fill, body))
#let seg(x0, y0, x1, y1, stroke: 1pt + ink2) = place(top + left, curve(stroke: stroke, curve.move((x0, y0)), curve.line(
  (x1, y1),
)))
#let arrow(x0, y0, x1, y1, paint: ink2, th: 1pt, head: 0.18cm) = {
  let dx = (x1 - x0) / 1cm
  let dy = (y1 - y0) / 1cm
  let l = calc.sqrt(dx * dx + dy * dy)
  let ux = dx / l
  let uy = dy / l
  let bx = x1 - ux * head
  let by = y1 - uy * head
  seg(x0, y0, bx, by, stroke: th + paint)
  place(top + left, curve(
    fill: paint,
    stroke: none,
    curve.move((x1, y1)),
    curve.line((bx - uy * head * 0.55, by + ux * head * 0.55)),
    curve.line((bx + uy * head * 0.55, by - ux * head * 0.55)),
    curve.close(),
  ))
}
#let cam(x, y, color: c-blue) = {
  place(top + left, dx: x - 0.2cm, dy: y - 0.13cm, rect(width: 0.3cm, height: 0.26cm, radius: 1.5pt, fill: color))
  place(top + left, curve(
    fill: color,
    stroke: none,
    curve.move((x + 0.1cm, y)),
    curve.line((x + 0.28cm, y - 0.13cm)),
    curve.line((x + 0.28cm, y + 0.13cm)),
    curve.close(),
  ))
}
#let cross(x, y, s: 0.12cm, stroke: 1.4pt + c-orange) = {
  seg(x - s, y - s, x + s, y + s, stroke: stroke)
  seg(x - s, y + s, x + s, y - s, stroke: stroke)
}

// Grouped bar chart. data: one array per series, one value per category.
#let bars(
  cats,
  series,
  data,
  ymax: 0.6,
  ticks: (0, 0.2, 0.4, 0.6),
  h: 6.2cm,
  w: 15cm,
  refs: (),
  xlabel: none,
  ylabel: none,
) = {
  let lm = 1.3cm
  let n = cats.len()
  let m = series.len()
  let gw = w / n
  let bw = gw * 0.78 / m
  let y(v) = h - h * v / ymax
  let rm = if refs.len() > 0 { 2.7cm } else { 0cm }
  block(width: lm + w + rm, height: h + 1.2cm, {
    for t in ticks {
      place(top + left, dx: lm, dy: y(t), line(length: w, stroke: 0.6pt + rule))
      place(top + left, dx: 0cm, dy: y(t) - 0.45em, box(width: lm - 0.25cm, align(right, text(
        size: 11pt,
        fill: muted,
        fmt(t, d: 1),
      ))))
    }
    for (j, c) in cats.enumerate() {
      for (i, s) in series.enumerate() {
        let v = data.at(i).at(j)
        let x0 = lm + gw * j + gw * 0.11 + bw * i
        place(top + left, dx: x0, dy: y(calc.min(v, ymax)), rect(
          width: bw - 2pt,
          height: h * calc.min(v, ymax) / ymax,
          fill: s.color,
          radius: (top-left: 3pt, top-right: 3pt),
        ))
        place(top + left, dx: x0 - 0.3cm, dy: y(calc.min(v, ymax)) - 0.5cm, box(width: bw - 2pt + 0.6cm, align(
          center,
          text(size: 9.5pt, fill: ink2, fmt(v)),
        )))
      }
      place(top + left, dx: lm + gw * j, dy: h + 0.18cm, box(width: gw, align(center, text(size: 13pt, c))))
    }
    for r in refs {
      place(top + left, dx: lm, dy: y(r.at(0)), line(length: w, stroke: (paint: ink2, thickness: 1pt, dash: "dashed")))
      place(top + left, dx: lm + w + 0.15cm, dy: y(r.at(0)) - 0.5em, box(width: rm - 0.15cm, text(
        size: 10pt,
        fill: ink2,
        weight: "semibold",
        r.at(1),
      )))
    }
    place(top + left, dx: lm, dy: h, line(length: w, stroke: 0.8pt + ink2))
    if xlabel != none {
      place(top + left, dx: lm, dy: h + 0.72cm, box(width: w, align(center, text(size: 11pt, fill: muted, xlabel))))
    }
  })
}
#let legend(series) = {
  set text(size: 12.5pt)
  series
    .map(s => box[#box(width: 0.8em, height: 0.8em, radius: 2pt, fill: s.color, baseline: 0.1em) #h(0.3em)#s.name])
    .join(h(1.1em))
}

// 한 점에서 본 방향별 가림 (1차원 예시): 방향 a~b가 가려짐. 앞 몇 개 주파수로 요약한 근사와 그 계수.
#let occ-a = 2.0
#let occ-b = 3.1
#let occ-coeffs = {
  let a = occ-a
  let b = occ-b
  let cs = (1 - (b - a) / (2 * calc.pi),)
  for k in range(1, 9) {
    cs.push(-(calc.sin(k * b) - calc.sin(k * a)) / (k * calc.pi))
    if k < 8 { cs.push((calc.cos(k * b) - calc.cos(k * a)) / (k * calc.pi)) }
  }
  cs
}
#let coeff-bars(cs, x, mid, hmax, bw: 0.13cm, gap: 0.04cm, color: c-orange) = {
  let vmax = calc.max(..cs.map(calc.abs))
  for (i, v) in cs.enumerate() {
    let hh = hmax * calc.abs(v) / vmax
    place(
      top + left,
      dx: x + i * (bw + gap),
      dy: if v > 0 { mid - hh } else { mid },
      rect(width: bw, height: hh, fill: color, radius: 1pt),
    )
  }
  place(top + left, dx: x, dy: mid, line(length: cs.len() * (bw + gap), stroke: 0.5pt + ink2))
}

// 단계 위치 표시 (오른쪽 위). cur: "①" ~ "④", none이면 표시 안 함.
#let flow-nav(cur) = {
  let chip(n) = box(
    inset: (x: 0.35em, y: 0.15em),
    radius: 3pt,
    fill: if n == cur { c-blue } else { soft },
    text(size: 10.5pt, weight: "semibold", fill: if n == cur { white } else { muted }, n),
  )
  place(top + right, dy: -1.75cm, text(size: 10.5pt, fill: muted)[
    1단계 bake #chip("①")#h(1pt)#chip("②")#h(1pt)#chip("③") #h(0.3em)→#h(0.3em) 2단계 relight #chip("④")
  ])
}
