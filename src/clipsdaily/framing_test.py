import sys
from .cutter import _cut_segment
from pathlib import Path
_cut_segment(
    Path("/home/abel/clipsdaily/vod/2921253522_expedia_tail.mp4"),
    151, 10, Path("/home/abel/clipsdaily/clips/framing-test.mp4"))
print("cut done")
