# Generates the AI voiceover for the Receipt Reel with Kokoro TTS.
# Free, local, offline after first model download (Kokoro-82M, MIT).
# Voice: af_heart (Abel's pick), speed from script.json's voice block.
#
# Loudness-normalizes every beat to the target mean volume
# (script.json voice.targetMeanDb - v1's Piper level, -17 dB), because
# Kokoro renders quieter than Piper. Applies the full gain to reach the
# target mean, then a lookahead limiter holds peaks at -1.0 dB: capping
# the gain instead left quiet beats 2-5 dB under target (Kokoro's speech
# has a high crest factor). Runs inside .venv-kokoro.
#
# Usage (called by `npm run voiceover`):
#   .venv-kokoro/bin/python scripts/generate-kokoro-voiceover.py
# Prints one JSON object per beat:
#   {"id": ..., "duration": ..., "mean_db": ..., "max_db": ..., "gain_db": ...}
import json
import os
import re
import subprocess
import tempfile

import numpy as np
import soundfile as sf
from kokoro import KPipeline

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT_PATH = os.path.join(ROOT, "src", "script.json")
OUT_DIR = os.path.join(ROOT, "public", "voiceover")
SAMPLE_RATE = 24000
# -1.0 dB peak ceiling, as a linear value for ffmpeg's alimiter.
PEAK_LIMIT_LINEAR = 0.891


def volumedetect(path):
    out = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", path,
         "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True, check=True,
    ).stderr
    mean = float(re.search(r"mean_volume:\s*(-?[\d.]+) dB", out).group(1))
    maxv = float(re.search(r"max_volume:\s*(-?[\d.]+) dB", out).group(1))
    return mean, maxv


def main():
    with open(SCRIPT_PATH) as f:
        script = json.load(f)
    voice_cfg = script.get("voice", {})
    voice = voice_cfg.get("model", "af_heart")
    speed = float(voice_cfg.get("speed", 0.95))
    target_mean = float(voice_cfg.get("targetMeanDb", -17))

    os.makedirs(OUT_DIR, exist_ok=True)
    pipeline = KPipeline(lang_code="a")

    for beat in script["beats"]:
        out_path = os.path.join(OUT_DIR, f"{beat['id']}.wav")
        chunks = list(pipeline(beat["voice"], voice=voice, speed=speed))
        assert chunks, f"no audio generated for beat {beat['id']}"
        parts = [c[2] for c in chunks]
        audio = np.concatenate(parts) if len(parts) > 1 else parts[0]
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            raw_path = tmp.name
        sf.write(raw_path, audio, SAMPLE_RATE)
        mean, maxv = volumedetect(raw_path)
        gain = target_mean - mean
        # Full gain to the target mean, then a lookahead limiter holds any
        # peak at -1.0 dB (0.891 linear). Capping the gain instead left
        # beats 2-5 dB under target.
        filt = (
            f"volume={gain:.2f}dB,"
            f"alimiter=limit={PEAK_LIMIT_LINEAR}:level=false:attack=5:release=50"
        )
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
             "-i", raw_path, "-af", filt, out_path],
            check=True,
        )
        os.unlink(raw_path)
        final_mean, final_max = volumedetect(out_path)
        duration = sf.info(out_path).duration
        print(json.dumps({
            "id": beat["id"],
            "duration": round(duration, 2),
            "mean_db": round(final_mean, 1),
            "max_db": round(final_max, 1),
            "gain_db": round(gain, 2),
        }), flush=True)


if __name__ == "__main__":
    main()
