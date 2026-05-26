#!/usr/bin/env bash
# Otimiza os MP4 do dataset_videos para versoes leves (~480p, ~600kbps)
# para que cabe no git. Reduz ~15MB/video -> ~3MB/video.
#
# Uso:
#   bash scripts/optimize_videos.sh [SRC_DIR]
#
# Default SRC_DIR = ~/Downloads/dataset_videos
# Output: apps/api/videos_storage/<folder>/video.mp4
set -euo pipefail

SRC_DIR="${1:-$HOME/Downloads/dataset_videos}"
DEST_DIR="apps/api/videos_storage"

if [[ ! -d "$SRC_DIR" ]]; then
  echo "ERRO: pasta $SRC_DIR nao existe."
  exit 1
fi
if ! command -v ffmpeg >/dev/null; then
  echo "ERRO: ffmpeg nao instalado. brew install ffmpeg"
  exit 1
fi

mkdir -p "$DEST_DIR"

count=0
total=$(find "$SRC_DIR" -name "video.mp4" -mindepth 2 -maxdepth 2 | wc -l | tr -d ' ')
echo "[optimize] $total videos a processar"

for src in "$SRC_DIR"/*/video.mp4; do
  [[ -f "$src" ]] || continue
  folder=$(basename "$(dirname "$src")")
  out_dir="$DEST_DIR/$folder"
  out_file="$out_dir/video.mp4"
  mkdir -p "$out_dir"

  count=$((count + 1))
  if [[ -f "$out_file" ]]; then
    echo "[$count/$total] $folder — skip (ja existe)"
    continue
  fi

  echo "[$count/$total] $folder ..."
  # Corta para 90s e otimiza para demo (cabe no git, <100MB por arquivo)
  ffmpeg -nostdin -y -hide_banner -loglevel error \
    -ss 0 -t 90 \
    -i "$src" \
    -vf "scale=-2:360" \
    -c:v libx264 -preset veryfast -crf 30 \
    -c:a aac -b:a 48k -ac 1 \
    -movflags +faststart \
    "$out_file" || { echo "falhou em $folder, continuando"; rm -f "$out_file"; }
done

echo
echo "[optimize] tamanho final:"
du -sh "$DEST_DIR"
echo "[optimize] arquivos: $(find "$DEST_DIR" -name video.mp4 | wc -l | tr -d ' ')"
