# Install

Three ways in, pick one. The plugin is the recommended path for
Claude Code users; the CLI is the path for running the pipeline.

## Option A: Claude Code plugin (recommended)

Inside a Claude Code session:

```
/plugin marketplace add abelprasad/clipsdaily
/plugin install clipsdaily@abelprasad
```

Or in one command (Claude Code 2.1.275+):

```
/plugin install clipsdaily --marketplace abelprasad/clipsdaily
```

This installs the 7 slash commands (`/clipsdaily:run`, `:post`, `:queue`, `:campaign`, `:submit`, `:earnings`, `:status`) and the clipsdaily skill. The plugin needs the repo pushed to GitHub first — until then, use Option B.

## Option B: Copy-install (any harness)

Clone the repo and run the installer. It copies the skill + commands into your harness's home directory. Idempotent — re-run it to update.

```bash
git clone https://github.com/abelprasad/clipsdaily.git
cd clipsdaily
bash scripts/install.sh            # Claude Code only
bash scripts/install.sh --all      # + every other detected harness
```

On Windows (PowerShell):

```powershell
.\scripts\install.ps1        # Claude Code only
.\scripts\install.ps1 -All   # + every other detected harness
```

`--all` / `-All` copies the **skill** to each detected harness:

| Harness | Skill path |
|---|---|
| Claude Code | `~/.claude/skills` |
| OpenCode / Codex | `~/.agents/skills` |
| Hermes | `~/.hermes/skills` |
| Gemini | `~/.gemini/config/skills` |

A harness counts as detected when its binary is on PATH or its home directory already exists. **Slash commands stay Claude-Code-only by design** — other harnesses don't share the command format, so only the skill is copied there. Restart your harness after installing.

## Option C: CLI via pipx (run the pipeline)

```bash
pipx install git+https://github.com/abelprasad/clipsdaily
```

Or from a clone: `bash install.sh` (pipx from the git URL) or `bash install.sh --local` (editable install from the checkout). Then the system deps:

```bash
bash setup.sh
```

Full detail: [docs/installation.md](docs/installation.md).

## After installing

```bash
clipsdaily --help
clipsdaily auth check        # read-only, posts nothing
```

Auth is per-operator and never committed: [docs/AUTH.md](docs/AUTH.md) (YouTube OAuth, TikTok cookies, Instagram via the operator CLI). All platforms start OFF — nothing posts until you flip one on and auth it.

## Verify

```bash
bash test_e2e.sh            # full smoke test (needs network)
ls ~/.claude/skills/        # skill present (copy-install)
```
