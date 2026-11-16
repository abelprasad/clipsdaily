# clipsdaily plugin

Claude Code plugin for the clipsdaily pipeline. Slash commands for the main flows, backed by the `clipsdaily` CLI.

## Install

**Plugin (recommended).** Inside a Claude Code session:

```
/plugin marketplace add abelprasad/clipsdaily
/plugin install clipsdaily@abelprasad
```

Or in one command (Claude Code 2.1.275+):

```
/plugin install clipsdaily --marketplace abelprasad/clipsdaily
```

The marketplace manifest is `.claude-plugin/marketplace.json` at the repo root (marketplace name `abelprasad`). The plugin needs the repo pushed to GitHub first — until then, use the copy-install below.

**Copy-install.** From a clone:

```bash
bash scripts/install.sh            # Claude Code only
bash scripts/install.sh --all      # + every other detected harness
```

Or on Windows (PowerShell): `.\scripts\install.ps1` / `.\scripts\install.ps1 -All`. This copies the skill to `~/.claude/skills/clipsdaily` and the commands to `~/.claude/commands/clipsdaily` (invoked as `/clipsdaily:run`, etc.). `--all` also copies the skill to OpenCode/Codex (`~/.agents/skills`), Hermes (`~/.hermes/skills`), and Gemini (`~/.gemini/config/skills`) when detected. Slash commands stay Claude-Code-only by design.

**Skill only.** Copy the skill alongside either install:

```bash
cp -r clipsdaily/skills/clipsdaily ~/.claude/skills/
```

| Command | What it does |
|---|---|
| `/clipsdaily:run` | Run / check the live runner |
| `/clipsdaily:post` | Post now / one clip / hourly poster |
| `/clipsdaily:queue` | Queue status / maintainer / seed |
| `/clipsdaily:campaign` | Watch for campaigns / cut campaign clips |
| `/clipsdaily:submit` | Auto-submit outbox (scan / list / mark) |
| `/clipsdaily:earnings` | Earnings summary / update |
| `/clipsdaily:status` | Whole-pipeline health check |

## Skill

The standing rules live in `skills/clipsdaily/SKILL.md` (full frame, one-line captions, strict gate, TikTok blocked, never submit without the gate / twice / past 30 min). The plugin commands reference it; the plugin install and the copy-install both include it.

## Codex / Cursor

- **Codex:** the skill is plain Markdown — drop `skills/clipsdaily/SKILL.md` into your Codex skills directory (or reference the CLI in `AGENTS.md`). The CLI commands are identical; there is no Codex-specific plugin yet.
- **Cursor:** `.cursor/rules/clipsdaily.mdc` carries the standing rules as a project rule. Copy it into `.cursor/rules/` in any checkout.
