#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
for binary in python3 ffmpeg ffprobe; do
  command -v "$binary" >/dev/null || { echo "Required: $binary" >&2; exit 1; }
done
python3 -c 'import sys; assert sys.version_info >= (3, 11), "Python >=3.11 is required"'
if [ ! -x .venv/bin/python ]; then python3 -m venv .venv; fi
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip check
.venv/bin/python -c 'from reels.render import font_path; print("Font:", font_path())'
