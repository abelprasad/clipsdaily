// Generates the AI voiceover for the Receipt Reel from src/script.json.
// Free, local, offline: Piper TTS (piper-tts, pip) with the en_US-lessac-medium
// voice model in voices/. No paid service, no recordings.
//
// What it does:
//  1. Reads every beat's `voice` line from src/script.json
//  2. Renders one WAV per beat into public/voiceover/<beat-id>.wav
//  3. Measures each WAV with ffprobe and writes per-beat seconds into
//     script.json under `timings` (beat length = max(minSeconds,
//     audioSeconds + 0.5s tail)). The composition reads `timings` to size
//     each beat, so narration and visuals stay in sync.
//
// Usage:
//   npm run voiceover
// Re-run after editing any `voice` line in src/script.json, or after
// changing the voice model in script.json's `voice` block.
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const scriptPath = join(root, "src", "script.json");
const script = JSON.parse(readFileSync(scriptPath, "utf-8"));

const piper = "/home/abel/.local/bin/piper";
const model = join(root, script.voice.modelPath);
const config = `${model}.json`;
const outDir = join(root, "public", "voiceover");
mkdirSync(outDir, { recursive: true });

if (!existsSync(model) || !existsSync(config)) {
  console.error(`Voice model missing: ${model}`);
  console.error(
    "Download it from https://huggingface.co/rhasspy/piper-voices " +
      "(en/en_US/lessac/medium/en_US-lessac-medium.onnx + .onnx.json) into voices/",
  );
  process.exit(1);
}

const timings = {};
for (const beat of script.beats) {
  const out = join(outDir, `${beat.id}.wav`);
  console.log(`[${beat.id}] ${beat.voice}`);
  execFileSync(
    piper,
    [
      "--model",
      model,
      "--config",
      config,
      "--length-scale",
      String(script.voice.lengthScale ?? 1.0),
      "--output_file",
      out,
    ],
    { input: beat.voice, stdio: ["pipe", "ignore", "inherit"] },
  );
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
  const seconds = Math.max(beat.minSeconds, dur + 0.5);
  timings[beat.id] = Number(seconds.toFixed(2));
  console.log(`  -> ${dur.toFixed(2)}s audio, beat ${seconds.toFixed(2)}s`);
}

script.timings = timings;
writeFileSync(scriptPath, `${JSON.stringify(script, null, 2)}\n`);
const total = Object.values(timings).reduce((a, b) => a + b, 0);
console.log(`\nDone. Total runtime: ${total.toFixed(1)}s across ${script.beats.length} beats.`);
console.log("Timings written into src/script.json (\"timings\" key).");
