#!/usr/bin/env bash
# Render + volume a -14 LUFS (loudnorm in due passaggi, con limiter prima per non clippare).
set -e
cd "$(dirname "$0")/.."
BROWSER=${REMOTION_BROWSER:+--browser-executable=$REMOTION_BROWSER}
npx remotion render GiroFacileCarburante out/render.mp4 --crf=16 $BROWSER
mkdir -p output
PRE="alimiter=limit=0.708:level=false"
J=$(ffmpeg -hide_banner -i out/render.mp4 -af "$PRE,loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json" -f null - 2>&1 | sed -n '/^{/,/^}/p')
M=$(echo "$J" | python3 -c "import json,sys;d=json.load(sys.stdin);print(f\"measured_I={d['input_i']}:measured_TP={d['input_tp']}:measured_LRA={d['input_lra']}:measured_thresh={d['input_thresh']}:offset={d['target_offset']}\")")
ffmpeg -v error -y -i out/render.mp4 -c:v copy -af "$PRE,loudnorm=I=-14:TP=-1.5:LRA=11:$M:linear=true" -ar 48000 -c:a aac -b:a 192k -movflags +faststart output/GiroFacile_carburante_remotion.mp4
ffmpeg -i output/GiroFacile_carburante_remotion.mp4 -af ebur128=peak=true -f null - 2>&1 | grep -A14 Summary | grep -E " I:|Peak:"
