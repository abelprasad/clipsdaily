from pathlib import Path
p = Path("/home/abel/clipsdaily/cutter.py")
s = p.read_text()
old = """        filters.append(
            "drawtext=textfile='%s':fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
            "fontcolor=white:fontsize=84:borderw=4:bordercolor=black:"
            "box=1:boxcolor=black@0.55:boxborderw=30:"
            "x=(w-text_w)/2:y=150:enable='between(t,0,3)'" % hook_file)"""
new = """        # Motion (motion-design skill, LottieFiles — Energetic archetype):
        # entrance 250ms ease-out-expo on position + opacity (slide down
        # 40px into place while fading in), hold, 170ms ease-in fade out.
        # Entrance > exit; decelerate in, accelerate out. Box removed so
        # the fade applies to the whole hook, not just the letters.
        filters.append(
            "drawtext=textfile='%s':fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
            "fontcolor=white:fontsize=84:borderw=4:bordercolor=black:"
            "x=(w-text_w)/2:"
            "y='150-40*pow(2,-10*min(t/0.25,1))':"
            "alpha='(1-pow(2,-10*min(t/0.25,1)))*(1-pow(max(0,(t-2.83)/0.17),2))':"
            "enable='between(t,0,3)'" % hook_file)"""
assert old in s, "hook drawtext block not found"
s = s.replace(old, new, 1)
p.write_text(s)
print("cutter.py patched: motion hook entrance")
