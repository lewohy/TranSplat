#!/usr/bin/env bash
# 논문 그림을 report/paper/figure/에 PNG로 내보냄. teaser 데이터는 make_teaser_data.py로 먼저 만듦.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
out="$here/../paper/figure"
mkdir -p "$out"
for f in "$here"/fig-*.typ; do
  name=$(basename "$f" .typ)
  typst compile --ppi 300 "$f" "$out/${name#fig-}.png"
  echo "wrote $out/${name#fig-}.png"
done
