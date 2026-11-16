import sys
from .cutter import _caption_and_burn
from pathlib import Path
out = _caption_and_burn(
    Path("/home/abel/clipsdaily/clips/framing-test.mp4"),
    "motion-test", "ishowspeed", "small",
    Path("/home/abel/clipsdaily/clips"),
    hook="SPEED GAVE HIM A TRIP!")
print("burned", out)
