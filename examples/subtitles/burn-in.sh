#!/usr/bin/env bash
# Burn an .srt into the picture, so the text survives being posted anywhere.
#
#   ./examples/subtitles/burn-in.sh talk.mp4 talk.srt
#
# Writes talk-subtitled.mp4. Use this for social, where a sidecar subtitle file
# is either ignored or off by default. Keep the .srt for anything that plays it
# properly, since selectable text beats pixels.
set -euo pipefail

# Rendering subtitles needs libass, and the plain Homebrew ffmpeg bottle is
# built without it. Worse, it reports the missing filter as a syntax error in
# the filter string, which sends you looking in the wrong place. So find a
# binary that actually has the filter rather than trusting whichever ffmpeg is
# first on PATH.
# Collected into a variable rather than piped into grep -q: with pipefail set,
# grep exiting early on a match gives ffmpeg a SIGPIPE, and the function then
# reports failure precisely when it found what it was looking for.
has_subtitles() {
  local listing
  listing=$("$1" -hide_banner -filters 2>/dev/null || true)
  case "$listing" in *" subtitles "*) return 0 ;; *) return 1 ;; esac
}

ffmpeg_bin=""
for candidate in "${FFMPEG:-}" "$(command -v ffmpeg || true)" /opt/homebrew/opt/ffmpeg-full/bin/ffmpeg; do
  [ -n "$candidate" ] && [ -x "$candidate" ] || continue
  if has_subtitles "$candidate"; then ffmpeg_bin=$candidate; break; fi
done

if [ -z "$ffmpeg_bin" ]; then
  echo "No ffmpeg on this machine has the subtitles filter, so it was built without libass." >&2
  echo "On macOS: brew install ffmpeg-full" >&2
  echo "The .srt is still valid, and most players and social platforms take it as is." >&2
  exit 1
fi

video=${1:?usage: burn-in.sh <video> <srt>}
srt=${2:?usage: burn-in.sh <video> <srt>}
out="${video%.*}-subtitled.mp4"

# force_style is what stops the result looking like a fansub. White on a hard
# black outline stays readable over any footage, which a background box does
# not, and the bottom margin clears most player controls.
style="FontName=Helvetica,Fontsize=22,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=0,MarginV=28"

"$ffmpeg_bin" -v error -y -i "$video" \
  -vf "subtitles=${srt}:force_style='${style}'" \
  -c:a copy "$out"

echo "wrote $out"
