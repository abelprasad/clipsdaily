# clipsdaily — Codex notes

No Codex-specific plugin exists yet; the CLI + skill are agent-agnostic, so Codex can use them as-is.

## Use the skill

Copy `skills/clipsdaily/SKILL.md` into your Codex skills directory, or paste the standing rules into `AGENTS.md` at the repo root. The rules are the same for every agent: full frame, one-line captions, strict gate, TikTok blocked, never submit without the gate / twice / past 30 min.

## Use the CLI

```bash
clipsdaily run            # live runner
clipsdaily post now       # post the next pending clip
clipsdaily queue status   # queue health
clipsdaily campaign watch --check
clipsdaily submit scan
clipsdaily earnings
```

Full reference: `docs/cli-reference.md`.
