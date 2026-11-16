#!/bin/bash
# End-to-end test: synthetic 90s video + fake chat log -> spike -> 30s vertical clip.
#
# Adapted Nov 2026 for the installed `clipsdaily` package. The old
# flat-script version ran `python3 cutter.py ...` inside the live dir
# and wrote its log there. This version runs the installed package
# against a SCRATCH runtime home ($CLIPSDAILY_HOME = a temp dir), so
# it never touches the live dir. The log goes to stdout only.
#
# Requires: the package installed (make install), ffmpeg, network
# (streamlink live-check). Run from the repo root.
set -x
cd "$(dirname "$0")"
python3 -c "import clipsdaily" || { echo "clipsdaily not installed — run: make install" >&2; exit 1; }
export CLIPSDAILY_HOME="$(mktemp -d /tmp/clipsdaily-e2e.XXXXXX)"
trap 'rm -rf "$CLIPSDAILY_HOME"' EXIT
mkdir -p "$CLIPSDAILY_HOME"/{queue,ig-outbox,clips,vod,recordings,logs,campaign_work,submit-outbox,.auth}
cp examples/config.yaml "$CLIPSDAILY_HOME/config.yaml"

echo "=== 1. spike detector (fake chat counts) ==="
python3 -c "
from clipsdaily.chat import detect_spikes
counts=[5,6,5,7,6,5,6,80,7,6,5]
print('spikes at windows:', detect_spikes(counts))
assert detect_spikes(counts)==[7]
assert detect_spikes([5,6,5,7,6,5,6,7,6])==[]
print('spike detector OK')"

echo "=== 2. synthetic 90s test video ==="
ffmpeg -y -f lavfi -i testsrc2=size=1280x720:rate=30:duration=90 \
  -f lavfi -i "sine=frequency=440:duration=90" \
  -c:v libx264 -preset veryfast -crf 23 -c:a aac -shortest \
  "$CLIPSDAILY_HOME/recordings/test_90s.mp4"

echo "=== 3. recorder live-check (xqc, expect False unless live) ==="
timeout 60 python3 -m clipsdaily.recorder xqc "$CLIPSDAILY_HOME/recordings/test_livecheck.ts" || echo "live-check exit: $?"

echo "=== 4. cutter: 30s clip around 45s spike ==="
time python3 -m clipsdaily.cutter "$CLIPSDAILY_HOME/recordings/test_90s.mp4" 45 teststreamer

echo "=== 5. verify clip ==="
ffprobe -v error -show_entries stream=width,height,duration,codec_name \
  -of default=noprint_wrappers=1 "$CLIPSDAILY_HOME/clips/teststreamer_45s.mp4"
ls -la "$CLIPSDAILY_HOME/clips/teststreamer_45s.mp4" "$CLIPSDAILY_HOME/clips/teststreamer_45s.srt"

echo "=== 6. config + poster (all platforms OFF) ==="
python3 -c "
import yaml
from clipsdaily.poster import post_all
cfg=yaml.safe_load(open('$CLIPSDAILY_HOME/config.yaml'))
print('streamers:', cfg['streamers'])
print('platforms:', cfg['platforms'])
print('posted:', post_all('$CLIPSDAILY_HOME/clips/teststreamer_45s.mp4','teststreamer',cfg))"

echo "=== 7. runner imports + STOP kill switch ==="
touch "$CLIPSDAILY_HOME/STOP"
python3 -c "
from clipsdaily.runner import stop_requested
assert stop_requested() is True
print('STOP kill switch OK')"
rm "$CLIPSDAILY_HOME/STOP"
python3 -c "
from clipsdaily.runner import stop_requested
assert stop_requested() is False
print('STOP removed, resume OK')"

echo "=== 8. CLI smoke test ==="
clipsdaily --help >/dev/null
clipsdaily queue status
clipsdaily earnings --summary || true

echo "=== TEST DONE ==="
