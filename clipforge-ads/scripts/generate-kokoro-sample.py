# One-off Kokoro sample generator for ClipForge ad voice selection.
# Free, local, offline after first model download (Kokoro-82M, MIT).
import sys
import soundfile as sf
from kokoro import KPipeline

TEXT = "Stop paying forty-nine dollars a month for clips that die in two days."
VOICE = sys.argv[1] if len(sys.argv) > 1 else "af_heart"
SPEED = float(sys.argv[2]) if len(sys.argv) > 2 else 0.95
OUT = sys.argv[3] if len(sys.argv) > 3 else "/home/abel/clipforge-ads/out/voice-samples/sample-kokoro-heart.wav"

pipeline = KPipeline(lang_code="a")
chunks = list(pipeline(TEXT, voice=VOICE, speed=SPEED))
assert chunks, "no audio generated"
_, _, audio = chunks[0]
sf.write(OUT, audio, 24000)
print(f"wrote {OUT} voice={VOICE} speed={SPEED} chunks={len(chunks)}")
