// Generates the AI voiceover for the Receipt Reel from src/script.json.
// Free, local, offline: Kokoro TTS (Kokoro-82M, MIT) with the af_heart
// voice (Abel's pick), run in .venv-kokoro. No paid service, no recordings.
//
// What it does:
//  1. Calls scripts/generate-kokoro-voiceover.py, which renders one WAV
//     per beat into public/voiceover/<beat-id>.wav and loudness-normalizes
//     each to script.json's voice.targetMeanDb (v1's Piper level, -17 dB),
//     capped so the peak never exceeds -1.0 dB.
//  2. Measures each WAV with ffprobe and writes per-beat seconds into
//     script.json under `timings` (beat length = max(minSeconds,
//     audioSeconds + 0.4s tail)). The composition reads `timings` to size
//     each beat, so narration and visuals stay in sync.
//
// Usage:
//   npm run voiceover
// Re-run after editing any `voice` line in src/script.json, or after
// changing the voice in script.json's `voice` block.
import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const scriptPath = join(root, "src", "script.json");
const script = JSON.parse(readFileSync(scriptPath, "utf-8"));

const venvPython = join(root, ".venv-kokoro", "bin", "python");
const generator = join(root, "scripts", "generate-kokoro-voiceover.py");

console.log(
  `Generating voiceover with Kokoro (${script.voice.model}, speed ${script.voice.speed ?? 0.95})...`,
);
execFileSync(venvPython, [generator], { stdio: "inherit" });

const timings = {};
for (const beat of script.beats) {
  const out = join(root, "public", "voiceover", `${beat.id}.wav`);
  const dur = parseFloat(
    execFileSync(
      "ffprobe",
      [
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "csv=p=0",
        out,
      ],
      { encoding: "utf-8" },
    ).trim(),
  );
  const seconds = Math.max(beat.minSeconds, dur + 0.4);
  timings[beat.id] = Number(seconds.toFixed(2));
  console.log(`[${beat.id}] ${dur.toFixed(2)}s audio, beat ${seconds.toFixed(2)}s`);
}

script.timings = timings;
writeFileSync(scriptPath, `${JSON.stringify(script, null, 2)}\n`);
const total = Object.values(timings).reduce((a, b) => a + b, 0);
console.log(`\nDone. Total runtime: ${total.toFixed(1)}s across ${script.beats.length} beats.`);
console.log("Timings written into src/script.json (\"timings\" key).");
