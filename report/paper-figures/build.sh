#!/usr/bin/env bash
# 논문 그림을 report/paper/figure/에 벡터 PDF로 내보냄 (pdfLaTeX가 그대로 넣어 확대해도 선명함). teaser 데이터는 make_teaser_data.py로 먼저 만듦.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
out="$here/../paper/figure"
mkdir -p "$out"
# 글꼴이 없으면 typst가 경고만 내고 다른 글꼴로 그리므로 먼저 확인 (style.typ, flake.nix의 nanum)
if ! typst fonts | grep -qx NanumMyeongjo; then
  echo "NanumMyeongjo 글꼴이 없음: TYPST_FONT_PATHS에 나눔명조 TTF 폴더를 추가" >&2
  exit 1
fi
for f in "$here"/fig-*.typ; do
  name=$(basename "$f" .typ)
  typst compile "$f" "$out/${name#fig-}.pdf"
  echo "wrote $out/${name#fig-}.pdf"
done
