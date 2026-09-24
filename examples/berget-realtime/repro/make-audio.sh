#!/usr/bin/env bash
# Regenerates the test clip. macOS only; needs the Swedish voice Alva
# (System Settings > Accessibility > Spoken Content > System Voice).
# The committed counting-sv.wav was produced by exactly this command.
set -euo pipefail
cd "$(dirname "$0")"
say -v Alva -r 170 --data-format=LEI16@16000 --file-format=WAVE -o counting-sv.wav \
  "Ett. Stockholm är Sveriges huvudstad. Två. Göteborg ligger på västkusten. Tre. Malmö ligger i Skåne. Fyra. Uppsala har ett gammalt universitet."
echo "wrote counting-sv.wav"
