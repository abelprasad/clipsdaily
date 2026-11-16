#!/bin/bash
# End-to-end test: synthetic 90s video + fake chat log -> spike -> 30s vertical captioned clip
set -x
cd /home/abel/clipsdaily
LOG=logs/test-e2e.log
exec > >(tee -a "$LOG") 2>&1

echo "=== 1. spike detector (fake chat counts) ==="
python3 -c "
from chat import detect_spikes
counts=[5,6,5,7,6,5,6,80,7,6,5]
print('spikes at windows:', detect_spikes(counts))
assert detect_spikes(counts)==[7]
assert detect_spikes([5,6,5,7,6,5,6,7,6])==[]
print('spike detector OK')"

echo "=== 2. synthetic 90s test video ==="
ffmpeg -y -f lavfi -i testsrc2=size=1280x720:rate=30:duration=90 \
  -f lavfi -i "sine=frequency=440:duration=90" \
  -c:v libx264 -preset veryfast -crf 23 -c:a aac -shortest \
  recordings/test_90s.mp4

echo "=== 3. recorder live-check (xqc, expect False unless live) ==="
timeout 60 python3 recorder.py xqc recordings/test_livecheck.ts || echo "live-check exit: $?"

echo "=== 4. cutter: 30s clip around 45s spike ==="
time python3 cutter.py recordings/test_90s.mp4 45 teststreamer

echo "=== 5. verify clip ==="
ffprobe -v error -show_entries stream=width,height,duration,codec_name \
  -of default=noprint_wrappers=1 clips/teststreamer_45s.mp4
ls -la clips/teststreamer_45s.mp4 clips/teststreamer_45s.srt

echo "=== 6. config + poster (all platforms OFF) ==="
python3 -c "
import yaml
from poster import post_all
cfg=yaml.safe_load(open('config.yaml'))
print('streamers:', cfg['streamers'])
print('platforms:', cfg['platforms'])
print('posted:', post_all('clips/teststreamer_45s.mp4','teststreamer',cfg))"

echo "=== 7. runner imports + STOP kill switch ==="
touch STOP
python3 -c "
from runner import stop_requested
assert stop_requested() is True
print('STOP kill switch OK')"
rm STOP
python3 -c "
from runner import stop_requested
assert stop_requested() is False
print('STOP removed, resume OK')"

echo "=== TEST DONE ==="
