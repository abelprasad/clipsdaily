from pathlib import Path
p = Path("/home/abel/clipsdaily/cutter.py")
s = p.read_text()

old_comment = '''# Framing (changed Nov 15, 2026, per Abel: "a little more zoomed out").
# A 9:16 center crop of a 16:9 frame can only ever show 31.6% of its
# width, so widening by cropping alone is geometrically impossible.
# Instead the foreground is a WIDER center crop (3/4 of the frame
# height -> 42% of the width, ~33% wider than the old 607px slice),
# scaled to 1080x1440 and centered on a blurred, darkened full-frame
# background. Faces stay large and readable; more room/phone/context
# is visible. Output is still 1080x1920, captions unchanged.
ZOOM_OUT = 0.75  # foreground crop width = ih*9/16 / ZOOM_OUT


def _cut_segment(recording, start, length, out_path):
    """ffmpeg: cut one vertical 1080x1920 segment, no captions yet."""
    fg_w = "ih*9/16/%.2f" % (1.0 / ZOOM_OUT)  # = ih*3/4 at ZOOM_OUT=0.75
    fc = (
        "[0:v]split=2[bg][fg];"
        "[bg]scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,gblur=sigma=30,eq=brightness=-0.25[bg2];"
        "[fg]crop=%s:ih,scale=1080:1440[fg2];"
        "[bg2][fg2]overlay=(W-w)/2:(H-h)/2[out]" % fg_w
    )'''
new_comment = '''# Framing (Nov 15, 2026, per Abel: "why's it getting cropped, it
# should be the full clip" — NO CROPPING AT ALL). The whole 16:9
# source frame is scaled to fit the 1080 width (1080x608) and centered
# on a blurred, darkened copy of the same video filling the 1080x1920
# canvas. Nothing from the source frame is cut off — the standard
# full-frame vertical look. This supersedes the zoomed-out center
# crop; there is no crop region anymore.


def _cut_segment(recording, start, length, out_path):
    """ffmpeg: cut one vertical 1080x1920 segment, no captions yet.
    Full frame: the entire source frame is visible."""
    fc = (
        "[0:v]split=2[bg][fg];"
        "[bg]scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,gblur=sigma=30,eq=brightness=-0.25[bg2];"
        "[fg]scale=1080:-2[fg2];"
        "[bg2][fg2]overlay=(W-w)/2:(H-h)/2[out]"
    )'''
assert old_comment in s, "framing block not found"
s = s.replace(old_comment, new_comment, 1)
p.write_text(s)
print("cutter.py patched: full frame, no cropping")
