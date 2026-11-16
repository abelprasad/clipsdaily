# Skills

Claude Code skills the pipeline's development actually uses.
The runtime does not import any of these — they are agent
guidance. Only one is vendored; the rest are install pointers
(too large, or for a future phase).

## Vendored

- `motion-design/` — LottieFiles motion-design-skill, MIT.
  Timing/easing/choreography guidance. Used for the hook
  entrance in `cutter.py` (250ms ease-out-expo slide+fade in,
  170ms ease-in fade out). Vendored with attribution; upstream:
  https://github.com/LottieFiles/motion-design-skill

## Install pointers (not vendored)

- **ffmpeg-skill** (kajisho5, MIT, v3.9.3) — agent guidance
  for ffmpeg filter work; the runtime just shells out to the
  ffmpeg binary. 31 MB with demos/assets, so it is not
  vendored. Install:
  `git clone --depth 1 https://github.com/kajisho5/ffmpeg-skill`
  into `~/.claude/skills/ffmpeg-skill`
  (or `npx skills add kajisho5/ffmpeg-skill`).
  Note: the skill needs ffmpeg >= 6.1. The live route is
  conda-forge ffmpeg 9.0.2 via micromamba, symlinked to
  `~/.local/bin/ffmpeg` (see `setup.sh`).
- **video-editing** (Moises Melo, MIT) — only for the future
  YouTube VOD phase (see `docs/youtube-vod-notes.md`). Not
  used by the live pipeline. Download is email-gated via
  blog.moisesmelo.com. Do not install it for live-mode work.

## Not included (unrelated to this pipeline)

- `synced` — a Claude Code sync bucket for other projects.
- `unslop` (CC-BY-4.0) — website audit skill for a different
  project (Bell & Broom). Not pipeline-related.
